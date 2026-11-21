"""Hermetic MQTT contract tests for Feature 012 Corridor Survey envelopes & Feature 011 compatibility."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from src.edge.telemetry.publisher import (
    MAX_CORRIDOR_SNAPSHOT_BYTES,
    build_corridor_snapshot_key,
    validate_corridor_snapshot_bytes,
)
from src.uservice.telemetry.models.contract.events import (
    CORRIDOR_SURVEY_PHASES,
    SURVEY_STAGING_HOLD_STATUS,
    CorridorOverridePayload,
    CorridorPhasePayload,
    CorridorReportPayload,
    CorridorSnapshotPayload,
    CorridorTrajectoryPayload,
    EdgeAvoidanceCommand,
    SwarmTelemetryEvent,
    build_telemetry_topic,
    classify_qos_and_priority,
    corridor_phase_to_flight_status,
    is_corridor_survey_event,
    is_edge_autonomous_alert,
    parse_corridor_survey_payload,
    parse_edge_avoidance_command,
    validate_topic_matches_event,
)


def test_canonical_flight_status_mapping_covers_all_phases():
    """T031 [US4]: Every SurveyPhase maps 1-to-1 to survey_<phase> plus survey_staging_hold."""
    assert len(CORRIDOR_SURVEY_PHASES) == 11
    for phase in CORRIDOR_SURVEY_PHASES:
        mapped = corridor_phase_to_flight_status(phase)
        assert mapped == f"survey_{phase}"
        assert mapped.startswith("survey_")
        assert mapped != "approaching"
    assert SURVEY_STAGING_HOLD_STATUS == "survey_staging_hold"
    with pytest.raises(ValueError):
        corridor_phase_to_flight_status("unknown_phase")


def test_all_five_corridor_mqtt_envelopes_and_qos():
    """T031 [US4]: Validates all 5 Feature 012 QoS 1 MQTT envelopes and preserves Feature 011 isolation."""
    swarm_id = str(uuid.uuid4())
    survey_id = str(uuid.uuid4())
    snap_id = str(uuid.uuid4())
    dec_id = str(uuid.uuid4())
    topic = build_telemetry_topic("default-theater", swarm_id, "drone-1", "alert")

    payloads = [
        (
            "survey_initial_look_around",
            f"s3://tactical-snapshots/{build_corridor_snapshot_key('default-theater', swarm_id, survey_id, 'drone-1', snap_id)}",
            CorridorSnapshotPayload(
                survey_id=survey_id,
                snapshot_id=snap_id,
                sequence_num=1,
                phase="initial_look_around",
                rel_x_m=0.0,
                rel_y_m=0.0,
                rel_z_m=2.5,
                cumulative_distance_m=0.0,
                visual_confidence=0.94,
                corridor_open=True,
                estimated_width_m=3.4,
                estimated_height_m=2.9,
                analysis_latency_ms=34.5,
                byte_size=4096,
                structural_tags=["turn_right"],
                findings=[],
            ),
        ),
        (
            "survey_outbound_discovery",
            None,
            CorridorTrajectoryPayload(
                survey_id=survey_id,
                decision_id=dec_id,
                sequence_num=2,
                action="trajectory_update",
                from_phase="initial_look_around",
                to_phase="outbound_discovery",
                target_rel_x_m=4.0,
                target_rel_y_m=0.0,
                target_rel_z_m=2.1,
                commanded_heading_deg=90.0,
                cleared_distance_m=4.0,
                speed_ms=1.5,
                trigger_snapshot_ids=[snap_id],
                analysis_latency_ms=42.0,
                rationale="Corridor opening cleared East (+90 deg).",
                breadcrumb={
                    "index": 1,
                    "rel_x_m": 0.0,
                    "rel_y_m": 0.0,
                    "rel_z_m": 2.5,
                    "heading_deg": 90.0,
                    "cumulative_distance_m": 0.0,
                    "estimated_width_m": 3.4,
                    "estimated_height_m": 2.9,
                    "snapshot_id": snap_id,
                },
            ),
        ),
        (
            "survey_outbound_discovery",
            None,
            CorridorPhasePayload(
                survey_id=survey_id,
                from_phase="initial_look_around",
                to_phase="outbound_discovery",
                flight_status="survey_outbound_discovery",
                reason="Initial sweep cleared heading 90 deg",
                rel_x_m=0.0,
                rel_y_m=0.0,
                rel_z_m=2.5,
                heading_deg=90.0,
                cumulative_distance_m=0.0,
                staging_hold_drone_ids=["drone-2", "drone-3"],
            ),
        ),
        (
            "survey_completed",
            None,
            CorridorReportPayload(
                survey_id=survey_id,
                status="completed",
                completion_reason="distance_reached",
                surveyed_distance_m=20.1,
                requested_distance_m=20.0,
                distance_defaulted=False,
                discovered_path=[],
                structural_features=["turn_right"],
                unexplored_branches=[],
                snapshot_count=20,
                decision_count=8,
                finding_count=1,
            ),
        ),
        (
            "survey_returning",
            None,
            CorridorOverridePayload(
                survey_id=survey_id,
                override_type="recall",
                commander_id="commander-1",
                from_phase="outbound_discovery",
                to_phase="returning",
                rationale="Mission objective changed.",
                requested_at=datetime.now(timezone.utc),
            ),
        ),
    ]

    for flight_status, snap_uri, payload in payloads:
        evt = SwarmTelemetryEvent(
            project_id="default-theater",
            swarm_id=swarm_id,
            drone_id="drone-1",
            metric_type="alert",
            lat=47.39775,
            lon=8.54561,
            alt_m=502.5,
            heading_deg=90.0,
            flight_status=flight_status,
            snapshot_uri=snap_uri,
            extra=payload.model_dump(mode="json"),
        )
        validate_topic_matches_event(topic, evt)
        assert classify_qos_and_priority(evt) == (1, 1)
        assert is_corridor_survey_event(evt) is True
        assert is_edge_autonomous_alert(evt) is False
        parsed = parse_corridor_survey_payload(evt)
        assert parsed is not None

    # Feature 011 backward compatibility check
    f011_cmd = EdgeAvoidanceCommand(
        action="obstacle_bypass",
        obstacle_class="pole",
        bypass_direction="left",
        previous_heading_deg=0.0,
        commanded_heading_deg=315.0,
        course_delta_deg=-45.0,
    )
    f011_evt = SwarmTelemetryEvent(
        project_id="default-theater",
        swarm_id=swarm_id,
        drone_id="drone-1",
        metric_type="alert",
        lat=47.39775,
        lon=8.54561,
        alt_m=505.0,
        flight_status="bypassing",
        extra=f011_cmd.model_dump(mode="json"),
    )
    assert is_edge_autonomous_alert(f011_evt) is True
    assert is_corridor_survey_event(f011_evt) is False
    assert parse_edge_avoidance_command(f011_evt) is not None


def test_corridor_snapshot_security_validators():
    """T031 [US4]: Enforces JPEG magic bytes, 5 MB limit, UUID validation, and path traversal rejection."""
    sid = str(uuid.uuid4())
    svid = str(uuid.uuid4())
    snid = str(uuid.uuid4())

    valid_jpeg = b"\xff\xd8\xff\xe0" + b"\x11" * 16
    assert validate_corridor_snapshot_bytes(valid_jpeg) == valid_jpeg

    with pytest.raises(ValueError, match="magic"):
        validate_corridor_snapshot_bytes(b"PNG_NOT_JPEG_DATA")

    with pytest.raises(ValueError, match="limit"):
        validate_corridor_snapshot_bytes(b"\xff\xd8\xff" + (b"\x00" * MAX_CORRIDOR_SNAPSHOT_BYTES))

    with pytest.raises(ValueError):
        build_corridor_snapshot_key("default-theater", sid, svid, "../evil", snid)

    with pytest.raises(ValueError):
        build_corridor_snapshot_key("../bad", sid, svid, "drone-1", snid)
