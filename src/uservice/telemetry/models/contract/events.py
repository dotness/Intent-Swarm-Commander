"""Telemetry Pydantic contracts, MQTT topic parsers, QoS classification, and LWT builders."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from src.uservice.base.models.api.base import BaseModel

MetricType = Literal["navigation", "battery", "health", "detection", "alert"]

WILDCARD_TELEMETRY_TOPIC = "telemetry/projects/+/swarms/+/+/+"

PROJECT_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
TELEMETRY_TOPIC_RE = re.compile(
    r"^telemetry/projects/([a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)/"
    r"swarms/([^/]+)/([^/]+)/(navigation|battery|health|detection|alert)$"
)


class SwarmTelemetryEvent(BaseModel):
    """Canonical streaming edge-to-C2 telemetry event."""

    schema_version: str = "1.0"
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: str = Field(default="default-theater", min_length=1, max_length=64)
    swarm_id: str = Field(..., min_length=1)
    drone_id: str = Field(..., min_length=1)
    metric_type: MetricType
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    alt_m: float = 0.0
    heading_deg: float = Field(default=0.0, ge=0.0, lt=360.0)
    speed_ms: float = Field(default=0.0, ge=0.0)
    battery_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    flight_status: str = "active"
    target_class: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bbox: list[int] | None = Field(default=None, min_length=4, max_length=4)
    snapshot_uri: str | None = None
    mission_id: str | None = None
    replayed: bool = False
    extra: dict[str, Any] | None = None

    @field_validator("project_id")
    @classmethod
    def _validate_project_slug(cls, value: str) -> str:
        if not PROJECT_SLUG_RE.match(value):
            raise ValueError(f"Invalid project_id slug: {value!r}")
        return value

    @model_validator(mode="after")
    def _validate_detection_fields(self) -> "SwarmTelemetryEvent":
        if self.metric_type == "detection" and not (self.target_class and self.target_class.strip()):
            raise ValueError("detection telemetry events require a non-empty target_class")
        return self


def build_telemetry_topic(
    project_id: str,
    swarm_id: str,
    drone_id: str,
    metric_type: MetricType,
) -> str:
    """Construct canonical MQTT telemetry topic."""
    if not PROJECT_SLUG_RE.match(project_id):
        raise ValueError(f"Invalid project_id slug: {project_id!r}")
    if not swarm_id or "/" in swarm_id:
        raise ValueError(f"Invalid swarm_id: {swarm_id!r}")
    if not drone_id or "/" in drone_id:
        raise ValueError(f"Invalid drone_id: {drone_id!r}")
    return f"telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/{metric_type}"


def parse_telemetry_topic(topic: str) -> dict[str, str]:
    """Parse canonical MQTT telemetry topic into structural components."""
    match = TELEMETRY_TOPIC_RE.match(topic)
    if not match:
        raise ValueError(f"Malformed telemetry MQTT topic: {topic!r}")
    return {
        "project_id": match.group(1),
        "swarm_id": match.group(2),
        "drone_id": match.group(3),
        "metric_type": match.group(4),
    }


def validate_topic_matches_event(topic: str, event: SwarmTelemetryEvent) -> None:
    """Verify MQTT topic tuple matches the embedded SwarmTelemetryEvent fields."""
    parts = parse_telemetry_topic(topic)
    if parts["project_id"] != event.project_id:
        raise ValueError(
            f"Topic project_id {parts['project_id']!r} != payload project_id {event.project_id!r}"
        )
    if parts["swarm_id"] != str(event.swarm_id):
        raise ValueError(
            f"Topic swarm_id {parts['swarm_id']!r} != payload swarm_id {event.swarm_id!r}"
        )
    if parts["drone_id"] != event.drone_id:
        raise ValueError(
            f"Topic drone_id {parts['drone_id']!r} != payload drone_id {event.drone_id!r}"
        )
    if parts["metric_type"] != event.metric_type:
        raise ValueError(
            f"Topic metric_type {parts['metric_type']!r} != payload metric_type {event.metric_type!r}"
        )


def classify_qos_and_priority(event: SwarmTelemetryEvent) -> tuple[int, int]:
    """Return (mqtt_qos, spool_priority) for a telemetry event."""
    if event.metric_type in ("detection", "alert"):
        return (1, 1)
    if event.metric_type == "battery" and event.battery_pct < 20.0:
        return (1, 1)
    if event.metric_type == "health" and (
        event.flight_status == "offline_lwt" or bool((event.extra or {}).get("lwt"))
    ):
        return (1, 1)
    return (0, 0)


def build_lwt_payload(project_id: str, swarm_id: str, drone_id: str) -> dict[str, Any]:
    """Build canonical MQTT Last Will & Testament JSON payload."""
    return {
        "schema_version": "1.0",
        "event_id": str(uuid.UUID(int=0)),
        "project_id": project_id,
        "swarm_id": swarm_id,
        "drone_id": drone_id,
        "metric_type": "health",
        "lat": 0.0,
        "lon": 0.0,
        "alt_m": 0.0,
        "flight_status": "offline_lwt",
        "extra": {"lwt": True, "reason": "ungraceful_disconnect"},
    }


class EdgeAvoidanceCommand(BaseModel):
    """Provenance payload for an edge-autonomous obstacle avoidance command."""

    command_source: Literal["edge_autonomous"] = "edge_autonomous"
    decision_authority: Literal["edge"] = "edge"
    action: Literal["obstacle_bypass", "resume_route", "obstructed_hold"]
    obstacle_class: str | None = None
    bypass_direction: Literal["left", "right"] | None = None
    previous_heading_deg: float = Field(ge=0.0, lt=360.0)
    commanded_heading_deg: float = Field(ge=0.0, lt=360.0)
    course_delta_deg: float = Field(ge=-180.0, le=180.0)
    trigger_detection_id: str | None = None
    llm_matched_target: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def is_edge_autonomous_alert(event: SwarmTelemetryEvent) -> bool:
    """Return True when a telemetry alert carries edge-autonomous avoidance provenance."""
    return (
        event.metric_type == "alert"
        and isinstance(event.extra, dict)
        and event.extra.get("command_source") == "edge_autonomous"
    )


def parse_edge_avoidance_command(event: SwarmTelemetryEvent) -> EdgeAvoidanceCommand | None:
    """Validate and parse EdgeAvoidanceCommand from an edge-autonomous alert event."""
    if not is_edge_autonomous_alert(event):
        return None
    assert event.extra is not None
    return EdgeAvoidanceCommand.model_validate(event.extra)


CORRIDOR_SURVEY_PHASES: tuple[str, ...] = (
    "initializing",
    "initial_look_around",
    "impassable_start",
    "outbound_discovery",
    "boundary_hold",
    "turn_look_around",
    "returning",
    "return_blocked_hold",
    "emergency_hold",
    "completed",
    "completed_holding",
)

SURVEY_STAGING_HOLD_STATUS = "survey_staging_hold"

CorridorSurveyEventType = Literal[
    "corridor_snapshot",
    "corridor_trajectory",
    "corridor_phase",
    "corridor_report",
    "corridor_override",
]

CORRIDOR_SURVEY_EVENT_TYPES: tuple[str, ...] = (
    "corridor_snapshot",
    "corridor_trajectory",
    "corridor_phase",
    "corridor_report",
    "corridor_override",
)


def corridor_phase_to_flight_status(phase: str) -> str:
    """Map a canonical SurveyPhase to its 1-to-1 telemetry flight_status string (`survey_<phase>`)."""
    norm = str(phase).strip()
    if norm not in CORRIDOR_SURVEY_PHASES:
        raise ValueError(f"Unsupported corridor survey phase: {phase!r}")
    return f"survey_{norm}"


class CorridorSnapshotPayload(BaseModel):
    """Provenance payload in SwarmTelemetryEvent.extra for every captured corridor snapshot."""

    command_source: Literal["edge_corridor_survey"] = "edge_corridor_survey"
    decision_authority: Literal["edge"] = "edge"
    survey_event_type: Literal["corridor_snapshot"] = "corridor_snapshot"
    survey_id: str = Field(..., min_length=1)
    snapshot_id: str = Field(..., min_length=1)
    sequence_num: int = Field(..., ge=1)
    phase: str
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    cumulative_distance_m: float = Field(..., ge=0.0)
    visual_confidence: float = Field(..., ge=0.0, le=1.0)
    corridor_open: bool
    estimated_width_m: float | None = Field(default=None, ge=0.0)
    estimated_height_m: float | None = Field(default=None, ge=0.0)
    analysis_latency_ms: float = Field(..., ge=0.0)
    byte_size: int = Field(..., gt=0, le=5 * 1024 * 1024)
    structural_tags: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class CorridorTrajectoryPayload(BaseModel):
    """Provenance payload in SwarmTelemetryEvent.extra for every edge trajectory decision."""

    command_source: Literal["edge_corridor_survey"] = "edge_corridor_survey"
    decision_authority: Literal["edge"] = "edge"
    survey_event_type: Literal["corridor_trajectory"] = "corridor_trajectory"
    survey_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    sequence_num: int = Field(..., ge=1)
    action: str
    from_phase: str
    to_phase: str
    target_rel_x_m: float
    target_rel_y_m: float
    target_rel_z_m: float
    commanded_heading_deg: float = Field(..., ge=0.0, lt=360.0)
    cleared_distance_m: float = Field(..., ge=0.0)
    speed_ms: float = Field(..., ge=0.0)
    trigger_snapshot_ids: list[str] = Field(default_factory=list)
    analysis_latency_ms: float | None = Field(default=None, ge=0.0)
    rationale: str
    breadcrumb: dict[str, Any] | None = None


class CorridorPhasePayload(BaseModel):
    """Provenance payload in SwarmTelemetryEvent.extra for survey state transitions & staging hold."""

    command_source: Literal["edge_corridor_survey", "operator_corridor_override"] = "edge_corridor_survey"
    decision_authority: Literal["edge", "commander"] = "edge"
    survey_event_type: Literal["corridor_phase"] = "corridor_phase"
    survey_id: str = Field(..., min_length=1)
    from_phase: str
    to_phase: str
    flight_status: str
    reason: str
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    heading_deg: float = Field(..., ge=0.0, lt=360.0)
    cumulative_distance_m: float = Field(..., ge=0.0)
    staging_hold_drone_ids: list[str] = Field(default_factory=list)


class CorridorReportPayload(BaseModel):
    """Provenance payload in SwarmTelemetryEvent.extra emitted upon completion/termination."""

    command_source: Literal["edge_corridor_survey", "operator_corridor_override"] = "edge_corridor_survey"
    decision_authority: Literal["edge", "commander"] = "edge"
    survey_event_type: Literal["corridor_report"] = "corridor_report"
    survey_id: str = Field(..., min_length=1)
    status: str
    completion_reason: str
    surveyed_distance_m: float = Field(..., ge=0.0)
    requested_distance_m: float = Field(..., gt=0.0)
    distance_defaulted: bool = False
    discovered_path: list[dict[str, Any]] = Field(default_factory=list)
    structural_features: list[Any] = Field(default_factory=list)
    unexplored_branches: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_count: int = Field(..., ge=0)
    decision_count: int = Field(..., ge=0)
    finding_count: int = Field(default=0, ge=0)


class CorridorOverridePayload(BaseModel):
    """Provenance payload in SwarmTelemetryEvent.extra for operator Recall / Emergency Abort."""

    command_source: Literal["operator_corridor_override"] = "operator_corridor_override"
    decision_authority: Literal["commander"] = "commander"
    survey_event_type: Literal["corridor_override"] = "corridor_override"
    survey_id: str = Field(..., min_length=1)
    override_type: Literal["recall", "emergency_abort"]
    commander_id: str = Field(..., min_length=1)
    from_phase: str
    to_phase: str
    rationale: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def is_corridor_survey_event(event: SwarmTelemetryEvent) -> bool:
    """Return True when a telemetry alert carries Feature 012 corridor survey provenance."""
    return (
        event.metric_type == "alert"
        and isinstance(event.extra, dict)
        and event.extra.get("command_source") in ("edge_corridor_survey", "operator_corridor_override")
        and event.extra.get("survey_event_type") in CORRIDOR_SURVEY_EVENT_TYPES
    )


def parse_corridor_survey_payload(
    event: SwarmTelemetryEvent,
) -> (
    CorridorSnapshotPayload
    | CorridorTrajectoryPayload
    | CorridorPhasePayload
    | CorridorReportPayload
    | CorridorOverridePayload
    | None
):
    """Validate and parse a typed Feature 012 corridor survey payload from an alert event."""
    if not is_corridor_survey_event(event):
        return None
    assert event.extra is not None
    event_type = event.extra.get("survey_event_type")
    if event_type == "corridor_snapshot":
        return CorridorSnapshotPayload.model_validate(event.extra)
    if event_type == "corridor_trajectory":
        return CorridorTrajectoryPayload.model_validate(event.extra)
    if event_type == "corridor_phase":
        return CorridorPhasePayload.model_validate(event.extra)
    if event_type == "corridor_report":
        return CorridorReportPayload.model_validate(event.extra)
    if event_type == "corridor_override":
        return CorridorOverridePayload.model_validate(event.extra)
    return None


class DroneTelemetryPosition(BaseModel):
    lat: float | None = None
    lng: float | None = None
    alt_m: float | None = None


class DroneTelemetryItem(BaseModel):
    id: str
    drone_id: str
    status: str
    battery_pct: float | None = None
    position: DroneTelemetryPosition
    heading: float = 0.0
    speed: float = 0.0
    current_mission: str = "idle"
    stale: bool = False
    last_avoidance_event: dict[str, Any] | None = None


class TelemetryProjectionResponse(BaseModel):
    swarm_id: str
    project_id: str = "default-theater"
    telemetry_source: Literal["mqtt_live", "mqtt_stale"]
    last_seen_utc: str | None = None
    drones: list[DroneTelemetryItem] = Field(default_factory=list)


class SpoolStatusResponse(BaseModel):
    swarm_id: str
    queued_rows: int
    priority_queued_rows: int
    routine_queued_rows: int
    evicted_routine_count: int
    evicted_critical_count: int
    max_records: int
    oldest_queued_utc: str | None = None
