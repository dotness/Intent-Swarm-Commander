"""SMEAC Domain Facade."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.analytics.facade.analytics import AnalyticsFacade
from src.uservice.base.agent import AgentContext
from src.uservice.base.errors import ResourceDoesNotExist, ValidationError
from src.uservice.base.facade.base import DomainFacade
from src.uservice.corridor.models.contract.schemas import (
    CorridorSurveyParams,
    resolve_entry_altitude,
)
from src.uservice.corridor.models.storage.survey import CorridorSurvey
from src.uservice.hitl.facade.hitl import HitlFacade
import src.uservice.operation.facade as operation_facade
from src.uservice.smeac.models.contract.command import (
    CommandPriority,
    FormationType,
    HIGH_IMPACT_MISSIONS,
    MissionType,
    SwarmCommand,
)
from src.uservice.smeac.models.contract.schemas import (
    SmeacDraftData,
    SmeacDraftRequest,
    SmeacOrderCreateRequest,
)
from src.uservice.smeac.models.storage.smeac import SmeacOrder
from src.uservice.smeac.operations import smeac_agents
from src.uservice.smeac.operations.copilot import SmeacCopilot
from src.uservice.smeac.operations.process import ProcessSmeacInput, ProcessSmeacWorkflow
from src.uservice.swarm.models.storage.instance import SwarmInstance
from src.uservice.threat.facade.threat import ThreatFacade, get_default_graph_client
from src.uservice.threat.operations.graph_client import MemgraphClient

logger = logging.getLogger(__name__)


def _validate_corridor_survey_command(cmd_dto: Any) -> tuple[CorridorSurveyParams, float]:
    """Validate coordinate-free corridor survey params and resolve entry_altitude_m (`FR-001`, `FR-021`)."""
    raw_sp = getattr(cmd_dto, "survey_params", None)
    if raw_sp is None:
        sp_dict: dict[str, Any] = {}
    elif hasattr(raw_sp, "model_dump"):
        sp_dict = raw_sp.model_dump()
    elif isinstance(raw_sp, dict):
        sp_dict = dict(raw_sp)
    else:
        raise ValidationError("survey_params must be a valid object")

    raw_dist = sp_dict.get("target_distance_m")
    if raw_dist is None:
        target_distance_m = 20.0
        distance_defaulted = True
    else:
        target_distance_m = float(raw_dist)
        if target_distance_m <= 0.0:
            raise ValidationError(
                f"target_distance_m must be strictly positive (> 0); received {target_distance_m}"
            )
        distance_defaulted = bool(sp_dict.get("distance_defaulted", False))

    focus = list(sp_dict.get("intelligence_focus") or [])
    if not focus and getattr(cmd_dto, "target_object_class", None):
        focus = [str(cmd_dto.target_object_class)]

    try:
        params = CorridorSurveyParams(
            target_distance_m=target_distance_m,
            distance_defaulted=distance_defaulted,
            return_to_origin=bool(sp_dict.get("return_to_origin", True)),
            corridor_descriptor=str(sp_dict.get("corridor_descriptor") or "corridor"),
            intelligence_focus=focus,
            min_altitude_m=float(sp_dict.get("min_altitude_m", 1.2)),
            max_altitude_m=float(sp_dict.get("max_altitude_m", 8.0)),
            cruise_speed_ms=float(sp_dict.get("cruise_speed_ms", 1.5)),
        )
        resolved_alt = resolve_entry_altitude(
            getattr(cmd_dto, "altitude_m", None),
            params.min_altitude_m,
            params.max_altitude_m,
        )
    except (PydanticValidationError, ValueError) as exc:
        raise ValidationError(str(exc)) from exc

    return params, resolved_alt


class SmeacFacade(DomainFacade):
    """Facade for SMEAC intent ingestion and processing."""

    def __init__(
        self,
        session: AsyncSession,
        user: dict[str, Any],
        graph_client: MemgraphClient | None = None,
    ) -> None:
        super().__init__(session=session, user=user)
        self.graph_client = graph_client or get_default_graph_client()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        user: dict[str, Any],
        graph_client: MemgraphClient | None = None,
    ) -> "SmeacFacade":
        return cls(session=session, user=user, graph_client=graph_client)

    async def submit_smeac_order(self, swarm_id: uuid.UUID, body: SmeacOrderCreateRequest) -> dict[str, Any]:
        """Submit a SMEAC order and launch the Temporal workflow."""
        # 1. Enforce RBAC and verify swarm + project ownership before persisting
        self.require_scope("smeac:create")

        order_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        project_id = getattr(body, "project_id", None) or "default-theater"

        swarm_row = await self.session.get(SwarmInstance, swarm_id)
        if swarm_row is None or swarm_row.project_id != project_id:
            raise ResourceDoesNotExist(f"Swarm {swarm_id} not found for project {project_id}")

        parsed_fields = {
            "situation": "parsed" if body.situation else "missing",
            "mission": "parsed" if body.mission else "missing",
            "execution": "parsed" if body.execution else "missing",
            "admin_logistics": "parsed" if body.admin_logistics else "not_provided",
            "command_signal": "parsed" if body.command_signal else "not_provided",
        }

        draft_source_refs_json = (
            json.dumps(body.draft_source_refs) if body.draft_source_refs is not None else None
        )
        order_record = SmeacOrder(
            id=order_id,
            project_id=project_id,
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=swarm_id,
            situation=body.situation,
            mission=body.mission,
            execution=body.execution,
            admin_logistics=body.admin_logistics,
            command_signal=body.command_signal,
            draft_source_refs=draft_source_refs_json,
        )
        self.session.add(order_record)
        await self.session.flush()

        # 2. Translate SMEAC intent via Gemini LLM agent (no regex fallback)
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required to parse SMEAC orders")

        formatted_cmds: list[dict[str, Any]] = []
        reasoning_out: str | None = None

        ctx = AgentContext(
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=str(swarm_id),
            correlation_id=str(order_id),
        )
        parse_result = await asyncio.wait_for(
            smeac_agents.parse_smeac_order(
                situation=body.situation,
                mission=body.mission,
                execution=body.execution,
                admin_logistics=body.admin_logistics,
                command_signal=body.command_signal,
                context=ctx,
            ),
            timeout=20.0,
        )

        reasoning_out = parse_result.reasoning

        try:
            validated_corridor: dict[int, tuple[CorridorSurveyParams, float]] = {}
            for idx, cmd_dto in enumerate(parse_result.commands):
                m_str = cmd_dto.mission_type.lower()
                if m_str == MissionType.CORRIDOR_SURVEY.value:
                    validated_corridor[idx] = _validate_corridor_survey_command(cmd_dto)
        except ValidationError:
            await self.session.rollback()
            raise

        for idx, cmd_dto in enumerate(parse_result.commands):
            m_str = cmd_dto.mission_type.lower()
            f_str = cmd_dto.formation_type.lower()
            p_str = cmd_dto.priority.lower()

            m_type = MissionType(m_str) if m_str in [m.value for m in MissionType] else MissionType.PATROL
            f_type = FormationType(f_str) if f_str in [f.value for f in FormationType] else FormationType.LINE
            prio = CommandPriority(p_str) if p_str in [p.value for p in CommandPriority] else CommandPriority.NORMAL

            corridor_entry = validated_corridor.get(idx)
            if corridor_entry is not None:
                survey_params_obj, resolved_alt = corridor_entry
                target_geo: dict[str, Any] = {"type": "RelativeCorridor", "coordinates": []}
                survey_params_json: str | None = survey_params_obj.model_dump_json()
                cmd_altitude = resolved_alt
                effective_drones = (
                    max(1, int(swarm_row.drone_count))
                    if swarm_row is not None
                    else max(1, int(cmd_dto.drone_count))
                )
                lead_scout_drone_id: str | None = "drone-1"
                staging_hold_drone_ids: list[str] | None = [
                    f"drone-{n}" for n in range(2, effective_drones + 1)
                ]
                stored_drone_count = effective_drones
            else:
                survey_params_obj = None
                target_geo = (
                    cmd_dto.target_area.model_dump()
                    if hasattr(cmd_dto.target_area, "model_dump")
                    else (
                        cmd_dto.target_area
                        if isinstance(cmd_dto.target_area, dict)
                        else {"raw": cmd_dto.target_area}
                    )
                )
                survey_params_json = None
                cmd_altitude = cmd_dto.altitude_m
                lead_scout_drone_id = None
                staging_hold_drone_ids = None
                stored_drone_count = cmd_dto.drone_count

            cmd_record = SwarmCommand(
                smeac_order_id=order_id,
                mission_type=m_type,
                formation_type=f_type,
                target_area=json.dumps(target_geo),
                target_object_class=cmd_dto.target_object_class,
                drone_count=stored_drone_count,
                altitude_m=cmd_altitude,
                speed_ms=cmd_dto.speed_ms,
                duration_s=cmd_dto.duration_s,
                priority=prio,
                is_high_impact=m_type in HIGH_IMPACT_MISSIONS,
                survey_params=survey_params_json,
            )
            self.session.add(cmd_record)
            await self.session.flush()

            survey_id: uuid.UUID | None = None
            survey_params_dict: dict[str, Any] | None = None
            if survey_params_obj is not None:
                survey_id = uuid.uuid4()
                survey_params_dict = survey_params_obj.model_dump(mode="json")
                self.session.add(
                    CorridorSurvey(
                        id=survey_id,
                        project_id=project_id,
                        swarm_instance_id=swarm_id,
                        smeac_order_id=order_id,
                        command_id=cmd_record.id,
                        lead_scout_drone_id=lead_scout_drone_id or "drone-1",
                        staging_hold_drone_ids=list(staging_hold_drone_ids or []),
                        corridor_descriptor=survey_params_obj.corridor_descriptor,
                        requested_distance_m=survey_params_obj.target_distance_m,
                        distance_defaulted=survey_params_obj.distance_defaulted,
                        return_to_origin=survey_params_obj.return_to_origin,
                        min_altitude_m=survey_params_obj.min_altitude_m,
                        max_altitude_m=survey_params_obj.max_altitude_m,
                        intelligence_focus=list(survey_params_obj.intelligence_focus),
                        phase="initializing",
                        status="dispatched",
                    )
                )
                await self.session.flush()

            formatted_cmds.append({
                "id": cmd_record.id,
                "mission_type": m_type.value,
                "formation_type": f_type.value,
                "target_area": target_geo,
                "target_object_class": cmd_dto.target_object_class,
                "drone_count": stored_drone_count,
                "altitude_m": cmd_altitude,
                "is_high_impact": m_type in HIGH_IMPACT_MISSIONS,
                "verification_status": "verified",
                "survey_id": survey_id,
                "lead_scout_drone_id": lead_scout_drone_id,
                "staging_hold_drone_ids": staging_hold_drone_ids,
                "survey_params": survey_params_dict,
            })

        if not formatted_cmds:
            raise RuntimeError(f"Gemini SMEAC parser returned zero commands for order {order_id}")

        order_record.status = "translated"
        await self.session.flush()
        logger.info("Parsed %d swarm commands via Gemini for order %s", len(parse_result.commands), order_id)

        # 3. Spatial-temporal Threat Gating (Memgraph dynamic threats)
        threat_facade = ThreatFacade(
            session=self.session,
            user=self.user,
            graph_client=self.graph_client,
        )
        all_conflicts: list[dict[str, Any]] = []
        seen_threat_ids: set[str] = set()

        for cmd_dict in formatted_cmds:
            t_area = cmd_dict.get("target_area") or {}
            if t_area.get("type") == "RelativeCorridor" and not t_area.get("coordinates"):
                continue
            eval_res = await threat_facade.evaluate_route_threats(
                project_id=project_id,
                target_area=t_area,
                altitude_m=cmd_dict.get("altitude_m"),
            )
            if eval_res.conflicts:
                cmd_dict["verification_status"] = "threat_conflict_hitl"
                for c in eval_res.conflicts:
                    c_dict = c.model_dump()
                    if c.threat_id not in seen_threat_ids:
                        seen_threat_ids.add(c.threat_id)
                        all_conflicts.append(c_dict)

        pending_hitl_id: uuid.UUID | None = None
        if all_conflicts:
            zone_names = ", ".join(c["name"] for c in all_conflicts[:3])
            hitl_facade = HitlFacade(
                session=self.session,
                user=self.user,
                graph_client=self.graph_client,
            )
            hitl_res = await hitl_facade.create_hitl_request(
                command_id=formatted_cmds[0]["id"],
                action_summary=f"Route intersects active threat zone(s): {zone_names}",
                timeout_seconds=600,
                project_id=project_id,
                workflow_id=f"smeac-{order_id}",
                is_threat_override=True,
                threat_zone_ids=[c["threat_id"] for c in all_conflicts],
            )
            pending_hitl_id = uuid.UUID(str(hitl_res["decision_id"]))
            order_record.status = "pending_hitl"
        elif any(c.get("is_high_impact") for c in formatted_cmds):
            mission_name = str(formatted_cmds[0].get("mission_type", "high_impact")).upper()
            hitl_facade = HitlFacade(
                session=self.session,
                user=self.user,
                graph_client=self.graph_client,
            )
            hitl_res = await hitl_facade.create_hitl_request(
                command_id=formatted_cmds[0]["id"],
                action_summary=f"High-impact {mission_name} mission requires commander approval",
                timeout_seconds=600,
                project_id=project_id,
                workflow_id=f"smeac-{order_id}",
                is_threat_override=False,
            )
            pending_hitl_id = uuid.UUID(str(hitl_res["decision_id"]))
            order_record.status = "pending_hitl"

        await self.session.flush()

        # 4. Schedule workflow via Operation wrapper (no graceful bypass)
        wf_input = ProcessSmeacInput(
            order_id=str(order_id),
            commander_id=self.user.get("sub", "unknown"),
            swarm_instance_id=str(swarm_id),
            situation=body.situation,
            mission=body.mission,
            execution=body.execution,
            admin_logistics=body.admin_logistics,
            command_signal=body.command_signal,
            project_id=project_id,
            commands=[
                {
                    **c,
                    "id": str(c["id"]),
                    "survey_id": str(c["survey_id"]) if c.get("survey_id") else None,
                }
                for c in formatted_cmds
            ],
        )
        await asyncio.wait_for(
            operation_facade.start_workflow(
                ProcessSmeacWorkflow,
                wf_input,
                task_queue=os.getenv("ISC_TASK_QUEUE", "isc-smeac-queue"),
                workflow_id=f"smeac-{order_id}",
            ),
            timeout=5.0,
        )
        logger.info("Launched Temporal workflow smeac-%s for user %s", order_id, self.user.get("sub"))

        return {
            "order_id": order_id,
            "project_id": project_id,
            "status": order_record.status,
            "swarm_instance_id": swarm_id,
            "parsed_fields": parsed_fields,
            "created_at": now,
            "commands": formatted_cmds,
            "reasoning": reasoning_out,
            "threat_conflicts": all_conflicts,
            "pending_hitl_decision_id": pending_hitl_id,
            "draft_source_refs": body.draft_source_refs,
        }

    async def get_order_status(self, swarm_id: uuid.UUID, order_id: uuid.UUID) -> dict[str, Any]:
        """Get the status of a submitted SMEAC order."""
        # 1. Enforce RBAC
        self.require_scope("smeac:read")
        
        # 2. Fetch from DB & enforce swarm ownership
        record = await self.session.get(SmeacOrder, order_id)
        if not record or record.swarm_instance_id != swarm_id:
            raise ResourceDoesNotExist(f"Order {order_id} not found for swarm {swarm_id}")

        formatted_cmds = []
        command_ids: list[uuid.UUID] = []
        cmds_stmt = select(SwarmCommand).where(SwarmCommand.smeac_order_id == order_id)
        cmds_res = await self.session.execute(cmds_stmt)
        commands = cmds_res.scalars().all()

        surveys_stmt = select(CorridorSurvey).where(CorridorSurvey.smeac_order_id == order_id)
        surveys_res = await self.session.execute(surveys_stmt)
        surveys_by_cmd = {s.command_id: s for s in surveys_res.scalars().all()}

        for cmd in commands:
            command_ids.append(cmd.id)
            area = cmd.target_area
            if isinstance(area, str) and (area.startswith("{") or area.startswith("[")):
                area = json.loads(area)
            linked_survey = surveys_by_cmd.get(cmd.id)
            survey_params_obj = (
                json.loads(cmd.survey_params) if getattr(cmd, "survey_params", None) else None
            )
            formatted_cmds.append({
                "id": cmd.id,
                "mission_type": cmd.mission_type.value if hasattr(cmd.mission_type, "value") else str(cmd.mission_type),
                "formation_type": cmd.formation_type.value if hasattr(cmd.formation_type, "value") else str(cmd.formation_type),
                "target_area": area if isinstance(area, dict) else {"raw": area},
                "target_object_class": cmd.target_object_class,
                "drone_count": cmd.drone_count,
                "altitude_m": cmd.altitude_m,
                "is_high_impact": cmd.is_high_impact,
                "verification_status": "verified",
                "survey_id": linked_survey.id if linked_survey is not None else None,
                "lead_scout_drone_id": linked_survey.lead_scout_drone_id if linked_survey is not None else None,
                "staging_hold_drone_ids": list(linked_survey.staging_hold_drone_ids) if linked_survey is not None else None,
                "survey_params": survey_params_obj,
            })

        pending_hitl_id: uuid.UUID | None = None
        threat_conflicts: list[dict[str, Any]] = []
        if command_ids:
            hitl_facade = HitlFacade(
                session=self.session,
                user=self.user,
                graph_client=self.graph_client,
            )
            pending_meta = await hitl_facade.get_pending_for_commands(command_ids)
            if pending_meta is not None:
                pending_hitl_id = pending_meta["decision_id"]
                threat_conflicts = pending_meta["threat_conflicts"]

        draft_source_refs: list[str] | None = None
        if getattr(record, "draft_source_refs", None):
            decoded = json.loads(record.draft_source_refs)
            if isinstance(decoded, list):
                draft_source_refs = [str(item) for item in decoded]

        return {
            "order_id": record.id,
            "project_id": record.project_id,
            "status": record.status,
            "commands": formatted_cmds,
            "constraint_violations": [],
            "threat_conflicts": threat_conflicts,
            "pending_hitl_decision_id": pending_hitl_id,
            "draft_source_refs": draft_source_refs,
        }

    async def generate_smeac_draft(
        self,
        body: SmeacDraftRequest,
        minio_store: Any = None,
    ) -> tuple[SmeacDraftData, dict[str, Any]]:
        """Read-only RAG drafting for commander review (never persists or starts Temporal)."""
        self.require_scope("smeac:create")

        read_user = {
            **self.user,
            "scope": f"{self.user.get('scope', '')} threat:read analytics:read".strip(),
        }
        threats_data = None
        targets_data = None
        aar_summary = None

        if body.include_threat_context:
            t_facade = ThreatFacade(
                session=self.session,
                user=read_user,
                graph_client=self.graph_client,
            )
            threats_data = await t_facade.list_threats(project_id=body.project_id)
            targets_data = await t_facade.list_targets(project_id=body.project_id)

        if body.include_aar_context:
            a_facade = AnalyticsFacade(
                session=self.session,
                user=read_user,
                minio_store=minio_store,
                graph_client=self.graph_client,
            )
            aar_summary = await a_facade.run_aar(project_id=body.project_id, query_type="summary")

        copilot = SmeacCopilot()
        return await copilot.generate_draft(
            body,
            threats_data=threats_data,
            targets_data=targets_data,
            aar_summary=aar_summary,
        )
