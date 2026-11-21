"""Atomic ORM persistence operations and Corridor Intelligence Report compiler (`FR-012`, `FR-014`, `FR-020`)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any
import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.operations.minio_store import MinioStore, validate_object_key
from src.uservice.base.errors import ISCError, ResourceDoesNotExist
from src.uservice.corridor.models.contract.schemas import (
    CorridorDecisionItem,
    CorridorFindingItem,
    CorridorIntelligenceReport,
    CorridorSnapshotSummary,
    CorridorSurveyListItem,
)
from src.uservice.corridor.models.storage.survey import (
    CorridorFinding,
    CorridorSnapshot,
    CorridorSurvey,
    CorridorTrajectoryDecision,
)
from src.uservice.operation.audit import ActorType, AuditEvent, AuditEventType
from src.uservice.swarm.models.storage.instance import SwarmInstance
from src.uservice.telemetry.models.contract.events import (
    CORRIDOR_SURVEY_PHASES,
    CorridorOverridePayload,
    CorridorPhasePayload,
    CorridorReportPayload,
    CorridorSnapshotPayload,
    CorridorTrajectoryPayload,
    SURVEY_STAGING_HOLD_STATUS,
    SwarmTelemetryEvent,
    parse_corridor_survey_payload,
)

logger = logging.getLogger(__name__)

_TERMINAL_SURVEY_PHASES = frozenset(
    {
        "completed",
        "completed_holding",
        "emergency_hold",
        "impassable_start",
        "return_blocked_hold",
    }
)
_MAX_CORRIDOR_SNAPSHOT_BYTES = 5 * 1024 * 1024
_JPEG_MAGIC = b"\xff\xd8\xff"
_COMPLETION_TO_PHASE = {
    "impassable_start": "impassable_start",
    "far_end_hold": "completed_holding",
    "operator_emergency_abort": "emergency_hold",
    "return_blocked": "return_blocked_hold",
}


class CorridorEdgeUnavailableError(ISCError):
    """Raised when forwarding a corridor override command to the edge node fails."""


def parse_and_validate_corridor_s3_uri(
    uri: str,
    *,
    expected_bucket: str,
    project_id: str,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
) -> tuple[str, str]:
    """Parse an s3:// corridor snapshot URI and enforce bucket, key safety, and survey ownership prefix."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Unsupported snapshot URI scheme: {uri!r}")
    rest = uri[len("s3://") :]
    if "/" not in rest:
        raise ValueError(f"Malformed snapshot S3 URI: {uri!r}")
    bucket, key = rest.split("/", 1)
    validate_object_key(key)
    if bucket != expected_bucket:
        raise ResourceDoesNotExist("Unauthorized snapshot bucket reference")
    expected_prefix = (
        f"projects/{project_id}/swarms/{swarm_id}/corridor-surveys/{survey_id}/"
    )
    if not key.startswith(expected_prefix):
        raise ResourceDoesNotExist("Snapshot key does not match survey scope")
    return bucket, key


async def fetch_verified_snapshot_bytes(
    minio_store: MinioStore,
    *,
    survey: CorridorSurvey,
    uri: str,
) -> bytes:
    """Fetch a persisted corridor snapshot from MinIO after validating URI scope, size limit, and JPEG header."""
    bucket, key = parse_and_validate_corridor_s3_uri(
        uri,
        expected_bucket=minio_store.SNAPSHOT_BUCKET,
        project_id=survey.project_id,
        swarm_id=survey.swarm_instance_id,
        survey_id=survey.id,
    )
    data = await minio_store.get_object(bucket, key)
    if not data or len(data) > _MAX_CORRIDOR_SNAPSHOT_BYTES:
        raise ValueError(f"Stored snapshot payload size out of bounds: {len(data)} bytes")
    if not data.startswith(_JPEG_MAGIC):
        raise ValueError("Stored snapshot payload failed JPEG magic-byte verification")
    return data


async def resolve_swarm_edge_endpoint(session: AsyncSession, swarm_id: uuid.UUID) -> str | None:
    """Resolve the HTTP endpoint URL for a swarm's edge controller."""
    return await get_swarm_edge_endpoint(session, swarm_id) or os.getenv("SWARM_DEFAULT_ENDPOINT")


async def forward_override_to_edge(
    *,
    edge_endpoint: str | None,
    survey_id: uuid.UUID,
    override_type: str,
    commander_id: str,
    rationale: str | None,
) -> None:
    """Forward a Tier-1 recall or Tier-2 emergency abort command to the edge node."""
    if not edge_endpoint:
        return
    edge_path = "recall" if override_type == "recall" else "emergency-abort"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{edge_endpoint.rstrip('/')}/corridor-survey/{survey_id}/{edge_path}",
                json={"rationale": rationale, "commander_id": commander_id},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CorridorEdgeUnavailableError(f"Edge override forwarding failed: {exc}") from exc


def _phase_to_lifecycle_status(phase: str, current_status: str) -> str:
    if phase == "impassable_start":
        return "impassable_start"
    if phase in ("emergency_hold", "return_blocked_hold"):
        return "aborted"
    if phase in ("completed", "completed_holding"):
        return current_status if current_status == "aborted" else "completed"
    return current_status if current_status == "aborted" else "active"


def _merge_unique_str_list(existing: list[Any], incoming: list[str]) -> list[str]:
    merged = [str(item) for item in (existing or [])]
    seen = set(merged)
    for tag in incoming:
        s = str(tag).strip()
        if s and s not in seen:
            seen.add(s)
            merged.append(s)
    return merged


async def _ingest_snapshot_event(
    session: AsyncSession,
    survey: CorridorSurvey,
    event: SwarmTelemetryEvent,
    payload: CorridorSnapshotPayload,
) -> None:
    snap_uuid = uuid.UUID(str(payload.snapshot_id))
    snap_uri = event.snapshot_uri or (
        f"s3://{MinioStore.SNAPSHOT_BUCKET}/projects/{survey.project_id}/swarms/{survey.swarm_instance_id}/"
        f"corridor-surveys/{survey.id}/drones/{event.drone_id}/{snap_uuid}.jpg"
    )
    try:
        parse_and_validate_corridor_s3_uri(
            snap_uri,
            expected_bucket=MinioStore.SNAPSHOT_BUCKET,
            project_id=survey.project_id,
            swarm_id=survey.swarm_instance_id,
            survey_id=survey.id,
        )
    except (ValueError, ResourceDoesNotExist) as exc:
        logger.warning(
            "Dropping snapshot event %s for survey %s due to invalid snapshot_uri %r: %s",
            snap_uuid,
            survey.id,
            snap_uri,
            exc,
        )
        return

    existing = await session.get(CorridorSnapshot, snap_uuid)
    if existing is None:
        session.add(
            CorridorSnapshot(
                id=snap_uuid,
                survey_id=survey.id,
                drone_id=event.drone_id,
                sequence_num=payload.sequence_num,
                phase=payload.phase,
                captured_at=event.timestamp,
                rel_x_m=payload.rel_x_m,
                rel_y_m=payload.rel_y_m,
                rel_z_m=payload.rel_z_m,
                heading_deg=event.heading_deg,
                cumulative_distance_m=payload.cumulative_distance_m,
                visual_confidence=payload.visual_confidence,
                corridor_open=payload.corridor_open,
                estimated_width_m=payload.estimated_width_m,
                estimated_height_m=payload.estimated_height_m,
                analysis_latency_ms=payload.analysis_latency_ms,
                snapshot_uri=snap_uri,
                byte_size=payload.byte_size,
                structural_tags=list(payload.structural_tags),
            )
        )

    survey.structural_features = _merge_unique_str_list(survey.structural_features, payload.structural_tags)
    survey.surveyed_distance_m = max(float(survey.surveyed_distance_m or 0.0), float(payload.cumulative_distance_m))
    if payload.phase in CORRIDOR_SURVEY_PHASES and survey.phase not in _TERMINAL_SURVEY_PHASES:
        survey.phase = payload.phase
        survey.status = _phase_to_lifecycle_status(payload.phase, survey.status)

    branches = list(survey.unexplored_branches or [])
    for f_raw in payload.findings:
        raw_fid = f_raw.get("finding_id")
        try:
            f_uuid = uuid.UUID(str(raw_fid)) if raw_fid else uuid.uuid4()
        except ValueError:
            f_uuid = uuid.uuid4()
        if await session.get(CorridorFinding, f_uuid) is not None:
            continue
        f_type = str(f_raw.get("finding_type", "structural_feature"))
        session.add(
            CorridorFinding(
                id=f_uuid,
                survey_id=survey.id,
                finding_type=f_type,
                label=str(f_raw.get("label", "unknown"))[:128],
                confidence=max(0.0, min(1.0, float(f_raw.get("confidence", 0.5)))),
                matches_mission_interest=bool(f_raw.get("matches_mission_interest", False)),
                rel_x_m=float(f_raw.get("rel_x_m", payload.rel_x_m)),
                rel_y_m=float(f_raw.get("rel_y_m", payload.rel_y_m)),
                rel_z_m=float(f_raw.get("rel_z_m", payload.rel_z_m)),
                heading_deg=float(f_raw.get("heading_deg", event.heading_deg)) % 360.0,
                cumulative_distance_m=max(0.0, float(f_raw.get("cumulative_distance_m", payload.cumulative_distance_m))),
                snapshot_id=snap_uuid,
                details=dict(f_raw.get("details") or {}),
                detected_at=event.timestamp,
            )
        )
        if f_type == "side_branch":
            details = f_raw.get("details") or {}
            branches.append(details if isinstance(details, dict) else {"label": str(f_raw.get("label", "branch"))})
    survey.unexplored_branches = branches


async def _ingest_trajectory_event(
    session: AsyncSession,
    survey: CorridorSurvey,
    event: SwarmTelemetryEvent,
    payload: CorridorTrajectoryPayload,
) -> None:
    dec_uuid = uuid.UUID(str(payload.decision_id))
    should_insert = await session.get(CorridorTrajectoryDecision, dec_uuid) is None
    if should_insert and payload.action == "operator_emergency_abort":
        dup_abort = await session.execute(
            select(CorridorTrajectoryDecision.id).where(
                CorridorTrajectoryDecision.survey_id == survey.id,
                CorridorTrajectoryDecision.action == "operator_emergency_abort",
            )
        )
        if dup_abort.scalar_one_or_none() is not None:
            should_insert = False
    if should_insert:
        session.add(
            CorridorTrajectoryDecision(
                id=dec_uuid,
                survey_id=survey.id,
                sequence_num=payload.sequence_num,
                decision_authority=payload.decision_authority,
                command_source=payload.command_source,
                action=payload.action,
                from_phase=payload.from_phase,
                to_phase=payload.to_phase,
                target_rel_x_m=payload.target_rel_x_m,
                target_rel_y_m=payload.target_rel_y_m,
                target_rel_z_m=payload.target_rel_z_m,
                commanded_heading_deg=payload.commanded_heading_deg,
                cleared_distance_m=payload.cleared_distance_m,
                speed_ms=payload.speed_ms,
                trigger_snapshot_ids=list(payload.trigger_snapshot_ids),
                analysis_latency_ms=payload.analysis_latency_ms,
                rationale=payload.rationale,
                created_at=event.timestamp,
            )
        )

    if isinstance(payload.breadcrumb, dict):
        path = [dict(p) for p in (survey.discovered_path or [])]
        bc_idx = payload.breadcrumb.get("index")
        existing_indices = {p.get("index") for p in path}
        if bc_idx not in existing_indices:
            path.append(dict(payload.breadcrumb))
            path.sort(key=lambda item: int(item.get("index", 0)))
            survey.discovered_path = path

    if payload.to_phase in CORRIDOR_SURVEY_PHASES and survey.phase not in _TERMINAL_SURVEY_PHASES:
        survey.phase = payload.to_phase
        survey.status = _phase_to_lifecycle_status(payload.to_phase, survey.status)


async def _ingest_phase_event(
    survey: CorridorSurvey,
    payload: CorridorPhasePayload,
) -> None:
    if payload.flight_status == SURVEY_STAGING_HOLD_STATUS:
        if payload.staging_hold_drone_ids:
            survey.staging_hold_drone_ids = list(payload.staging_hold_drone_ids)
        return
    if payload.to_phase in CORRIDOR_SURVEY_PHASES and survey.phase not in _TERMINAL_SURVEY_PHASES:
        survey.phase = payload.to_phase
        survey.status = _phase_to_lifecycle_status(payload.to_phase, survey.status)
    survey.surveyed_distance_m = max(float(survey.surveyed_distance_m or 0.0), float(payload.cumulative_distance_m))


async def _ingest_report_event(
    survey: CorridorSurvey,
    event: SwarmTelemetryEvent,
    payload: CorridorReportPayload,
) -> None:
    if survey.phase not in _TERMINAL_SURVEY_PHASES:
        survey.phase = _COMPLETION_TO_PHASE.get(payload.completion_reason, "completed")
    survey.status = payload.status
    survey.completion_reason = payload.completion_reason
    survey.surveyed_distance_m = max(float(survey.surveyed_distance_m or 0.0), float(payload.surveyed_distance_m))
    if payload.discovered_path:
        survey.discovered_path = list(payload.discovered_path)
    if payload.structural_features:
        survey.structural_features = _merge_unique_str_list(
            survey.structural_features,
            [str(item) for item in payload.structural_features],
        )
    if payload.unexplored_branches:
        survey.unexplored_branches = list(payload.unexplored_branches)
    if survey.completed_at is None:
        survey.completed_at = event.timestamp or datetime.now(timezone.utc)


async def _ingest_override_event(
    session: AsyncSession,
    survey: CorridorSurvey,
    event: SwarmTelemetryEvent,
    payload: CorridorOverridePayload,
) -> None:
    if payload.to_phase in CORRIDOR_SURVEY_PHASES:
        survey.phase = payload.to_phase
    survey.status = "aborted"
    survey.completion_reason = (
        "operator_recall" if payload.override_type == "recall" else "operator_emergency_abort"
    )
    if payload.override_type == "emergency_abort" and survey.completed_at is None:
        survey.completed_at = event.timestamp or datetime.now(timezone.utc)


async def ingest_corridor_event(session: AsyncSession, event: SwarmTelemetryEvent) -> bool:
    """Atomically project a canonical Feature 012 MQTT alert into PostgreSQL corridor tables."""
    payload = parse_corridor_survey_payload(event)
    if payload is None:
        return False

    try:
        survey_uuid = uuid.UUID(str(payload.survey_id))
    except ValueError:
        logger.warning("Ignoring corridor event with non-UUID survey_id=%r", getattr(payload, "survey_id", None))
        return False

    survey = await session.get(CorridorSurvey, survey_uuid)
    if survey is None:
        logger.debug("CorridorSurvey %s not found in DB yet; skipping event projection", survey_uuid)
        return False
    if str(survey.swarm_instance_id) != str(event.swarm_id) or survey.project_id != event.project_id:
        logger.warning(
            "Ignoring cross-tenant/swarm corridor event (event swarm=%s project=%s vs survey swarm=%s project=%s)",
            event.swarm_id,
            event.project_id,
            survey.swarm_instance_id,
            survey.project_id,
        )
        return False

    if isinstance(payload, CorridorSnapshotPayload):
        await _ingest_snapshot_event(session, survey, event, payload)
    elif isinstance(payload, CorridorTrajectoryPayload):
        await _ingest_trajectory_event(session, survey, event, payload)
    elif isinstance(payload, CorridorPhasePayload):
        await _ingest_phase_event(survey, payload)
    elif isinstance(payload, CorridorReportPayload):
        await _ingest_report_event(survey, event, payload)
    elif isinstance(payload, CorridorOverridePayload):
        await _ingest_override_event(session, survey, event, payload)

    survey.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return True


async def get_survey_for_swarm(
    session: AsyncSession,
    *,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    project_id: str | None = None,
) -> CorridorSurvey:
    """Fetch a CorridorSurvey enforcing swarm and project ownership (fails closed with 404 on mismatch)."""
    survey = await session.get(CorridorSurvey, survey_id)
    if survey is None or survey.swarm_instance_id != swarm_id:
        raise ResourceDoesNotExist(f"Corridor survey {survey_id} not found for swarm {swarm_id}")
    if project_id is not None and survey.project_id != project_id:
        raise ResourceDoesNotExist(f"Corridor survey {survey_id} not found for project {project_id}")
    return survey


async def get_swarm_edge_endpoint(session: AsyncSession, swarm_id: uuid.UUID) -> str | None:
    """Return SwarmInstance edge HTTP endpoint URL if registered."""
    res = await session.execute(select(SwarmInstance.endpoint_url).where(SwarmInstance.id == swarm_id))
    return res.scalar_one_or_none()


async def apply_operator_override_db(
    session: AsyncSession,
    *,
    survey: CorridorSurvey,
    commander_id: str,
    override_type: str,
    rationale: str | None,
) -> datetime:
    """Persist operator override status and AuditEvent (`ActorType.COMMANDER`)."""
    now = datetime.now(timezone.utc)
    target_phase = "returning" if override_type == "recall" else "emergency_hold"
    from_phase = survey.phase
    survey.phase = target_phase
    survey.status = "aborted"
    survey.completion_reason = (
        "operator_recall" if override_type == "recall" else "operator_emergency_abort"
    )
    if override_type == "emergency_abort":
        survey.completed_at = now
    survey.updated_at = now

    seq_res = await session.execute(
        select(func.coalesce(func.max(CorridorTrajectoryDecision.sequence_num), 0)).where(
            CorridorTrajectoryDecision.survey_id == survey.id
        )
    )
    next_seq = int(seq_res.scalar_one() or 0) + 1
    session.add(
        CorridorTrajectoryDecision(
            id=uuid.uuid4(),
            survey_id=survey.id,
            sequence_num=next_seq,
            decision_authority="commander",
            command_source="operator_corridor_override",
            action=f"operator_{override_type}",
            from_phase=from_phase,
            to_phase=target_phase,
            target_rel_x_m=0.0,
            target_rel_y_m=0.0,
            target_rel_z_m=float(survey.min_altitude_m),
            commanded_heading_deg=0.0,
            cleared_distance_m=0.0,
            speed_ms=0.0,
            trigger_snapshot_ids=[],
            analysis_latency_ms=0.0,
            rationale=rationale or f"Operator {override_type} initiated by {commander_id}",
            created_at=now,
        )
    )
    session.add(
        AuditEvent(
            event_type=AuditEventType.COMMAND_EXECUTED,
            actor_id=commander_id,
            actor_type=ActorType.COMMANDER,
            swarm_instance_id=survey.swarm_instance_id,
            resource_id=str(survey.id),
            details={
                "command_source": "operator_corridor_override",
                "decision_authority": "commander",
                "survey_id": str(survey.id),
                "override_type": override_type,
                "from_phase": from_phase,
                "to_phase": target_phase,
                "rationale": rationale,
                "project_id": survey.project_id,
            },
        )
    )
    await session.flush()
    return now


async def list_swarm_surveys(
    session: AsyncSession,
    *,
    swarm_id: uuid.UUID,
    project_id: str | None = None,
) -> list[CorridorSurveyListItem]:
    """List corridor surveys belonging to a swarm ordered newest first."""
    stmt = select(CorridorSurvey).where(CorridorSurvey.swarm_instance_id == swarm_id)
    if project_id is not None:
        stmt = stmt.where(CorridorSurvey.project_id == project_id)
    stmt = stmt.order_by(CorridorSurvey.created_at.desc())
    surveys = (await session.execute(stmt)).scalars().all()
    if not surveys:
        return []

    survey_ids = [s.id for s in surveys]
    snap_counts = dict(
        (
            await session.execute(
                select(CorridorSnapshot.survey_id, func.count(CorridorSnapshot.id))
                .where(CorridorSnapshot.survey_id.in_(survey_ids))
                .group_by(CorridorSnapshot.survey_id)
            )
        ).all()
    )
    dec_counts = dict(
        (
            await session.execute(
                select(CorridorTrajectoryDecision.survey_id, func.count(CorridorTrajectoryDecision.id))
                .where(CorridorTrajectoryDecision.survey_id.in_(survey_ids))
                .group_by(CorridorTrajectoryDecision.survey_id)
            )
        ).all()
    )
    find_counts = dict(
        (
            await session.execute(
                select(CorridorFinding.survey_id, func.count(CorridorFinding.id))
                .where(CorridorFinding.survey_id.in_(survey_ids))
                .group_by(CorridorFinding.survey_id)
            )
        ).all()
    )

    items: list[CorridorSurveyListItem] = []
    for s in surveys:
        snap_cnt = int(snap_counts.get(s.id, 0) or 0)
        dec_cnt = int(dec_counts.get(s.id, 0) or 0)
        find_cnt = int(find_counts.get(s.id, 0) or 0)
        items.append(
            CorridorSurveyListItem(
                survey_id=s.id,
                swarm_id=s.swarm_instance_id,
                project_id=s.project_id,
                lead_scout_drone_id=s.lead_scout_drone_id,
                staging_hold_drone_ids=list(s.staging_hold_drone_ids or []),
                corridor_descriptor=s.corridor_descriptor,
                requested_distance_m=s.requested_distance_m,
                distance_defaulted=s.distance_defaulted,
                surveyed_distance_m=s.surveyed_distance_m,
                return_to_origin=s.return_to_origin,
                min_altitude_m=s.min_altitude_m,
                max_altitude_m=s.max_altitude_m,
                phase=s.phase,
                status=s.status,
                completion_reason=s.completion_reason,
                snapshot_count=snap_cnt,
                decision_count=dec_cnt,
                finding_count=find_cnt,
                created_at=s.created_at,
                updated_at=s.updated_at,
                completed_at=s.completed_at,
            )
        )
    return items


async def assemble_corridor_report(
    session: AsyncSession,
    *,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    project_id: str | None = None,
) -> CorridorIntelligenceReport:
    """Compile the complete CorridorIntelligenceReport for a survey (`SC-006`)."""
    survey = await get_survey_for_swarm(
        session, swarm_id=swarm_id, survey_id=survey_id, project_id=project_id
    )

    snaps = (
        await session.execute(
            select(CorridorSnapshot)
            .where(CorridorSnapshot.survey_id == survey.id)
            .order_by(CorridorSnapshot.sequence_num.asc())
        )
    ).scalars().all()
    decisions = (
        await session.execute(
            select(CorridorTrajectoryDecision)
            .where(CorridorTrajectoryDecision.survey_id == survey.id)
            .order_by(CorridorTrajectoryDecision.sequence_num.asc())
        )
    ).scalars().all()
    findings = (
        await session.execute(
            select(CorridorFinding)
            .where(CorridorFinding.survey_id == survey.id)
            .order_by(CorridorFinding.detected_at.asc())
        )
    ).scalars().all()

    return CorridorIntelligenceReport(
        survey_id=survey.id,
        swarm_id=survey.swarm_instance_id,
        project_id=survey.project_id,
        smeac_order_id=survey.smeac_order_id,
        command_id=survey.command_id,
        lead_scout_drone_id=survey.lead_scout_drone_id,
        staging_hold_drone_ids=list(survey.staging_hold_drone_ids or []),
        corridor_descriptor=survey.corridor_descriptor,
        requested_distance_m=survey.requested_distance_m,
        distance_defaulted=survey.distance_defaulted,
        surveyed_distance_m=survey.surveyed_distance_m,
        return_to_origin=survey.return_to_origin,
        min_altitude_m=survey.min_altitude_m,
        max_altitude_m=survey.max_altitude_m,
        intelligence_focus=list(survey.intelligence_focus or []),
        phase=survey.phase,
        status=survey.status,
        completion_reason=survey.completion_reason,
        origin_pose=survey.origin_pose,
        discovered_path=list(survey.discovered_path or []),
        structural_features=list(survey.structural_features or []),
        unexplored_branches=list(survey.unexplored_branches or []),
        snapshots=[
            CorridorSnapshotSummary(
                snapshot_id=snap.id,
                sequence_num=snap.sequence_num,
                phase=snap.phase,
                captured_at=snap.captured_at,
                rel_x_m=snap.rel_x_m,
                rel_y_m=snap.rel_y_m,
                rel_z_m=snap.rel_z_m,
                heading_deg=snap.heading_deg,
                cumulative_distance_m=snap.cumulative_distance_m,
                visual_confidence=snap.visual_confidence,
                corridor_open=snap.corridor_open,
                estimated_width_m=snap.estimated_width_m,
                estimated_height_m=snap.estimated_height_m,
                analysis_latency_ms=snap.analysis_latency_ms,
                snapshot_uri=snap.snapshot_uri,
                byte_size=snap.byte_size,
                structural_tags=list(snap.structural_tags or []),
                image_proxy_url=(
                    f"/api/v1/swarms/{survey.swarm_instance_id}/corridor-surveys/{survey.id}"
                    f"/snapshots/{snap.id}/image?project_id={survey.project_id}"
                ),
            )
            for snap in snaps
        ],
        decisions=[
            CorridorDecisionItem(
                decision_id=dec.id,
                sequence_num=dec.sequence_num,
                decision_authority=dec.decision_authority,
                command_source=dec.command_source,
                action=dec.action,
                from_phase=dec.from_phase,
                to_phase=dec.to_phase,
                target_rel_x_m=dec.target_rel_x_m,
                target_rel_y_m=dec.target_rel_y_m,
                target_rel_z_m=dec.target_rel_z_m,
                commanded_heading_deg=dec.commanded_heading_deg,
                cleared_distance_m=dec.cleared_distance_m,
                speed_ms=dec.speed_ms,
                trigger_snapshot_ids=list(dec.trigger_snapshot_ids or []),
                analysis_latency_ms=dec.analysis_latency_ms,
                rationale=dec.rationale,
                created_at=dec.created_at,
            )
            for dec in decisions
        ],
        findings=[
            CorridorFindingItem(
                finding_id=f.id,
                finding_type=f.finding_type,
                label=f.label,
                confidence=f.confidence,
                matches_mission_interest=f.matches_mission_interest,
                rel_x_m=f.rel_x_m,
                rel_y_m=f.rel_y_m,
                rel_z_m=f.rel_z_m,
                heading_deg=f.heading_deg,
                cumulative_distance_m=f.cumulative_distance_m,
                snapshot_id=f.snapshot_id,
                details=dict(f.details or {}),
                detected_at=f.detected_at,
            )
            for f in findings
        ],
        created_at=survey.created_at,
        updated_at=survey.updated_at,
        completed_at=survey.completed_at,
    )


async def get_snapshot_storage_uri(
    session: AsyncSession,
    *,
    swarm_id: uuid.UUID,
    survey_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    project_id: str | None = None,
) -> tuple[CorridorSurvey, str]:
    """Validate ownership chain (project -> swarm -> survey -> snapshot) and return snapshot_uri."""
    survey = await get_survey_for_swarm(
        session, swarm_id=swarm_id, survey_id=survey_id, project_id=project_id
    )
    snap = await session.get(CorridorSnapshot, snapshot_id)
    if snap is None or snap.survey_id != survey.id:
        raise ResourceDoesNotExist(f"Snapshot {snapshot_id} not found for corridor survey {survey_id}")
    return survey, snap.snapshot_uri
