"""Pydantic v2 contracts for Coordinate-Free Corridor Path Discovery & Survey."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import Field, model_validator

from src.uservice.base.models.api.base import BaseModel


def resolve_entry_altitude(
    altitude_m: float | None,
    min_altitude_m: float,
    max_altitude_m: float,
) -> float:
    """Resolve and fail-closed validate the survey entry/cruise altitude (`FR-021`).

    When ``altitude_m`` is omitted (``None``), returns ``clamp(2.5, min_altitude_m, max_altitude_m)``.
    When explicitly provided, raises ``ValueError`` if outside ``[min_altitude_m, max_altitude_m]``.
    """
    low = float(min_altitude_m)
    high = float(max_altitude_m)
    if low >= high:
        raise ValueError(f"min_altitude_m ({low}) must be strictly less than max_altitude_m ({high})")
    if altitude_m is None:
        return round(max(low, min(high, 2.5)), 4)
    val = float(altitude_m)
    if val < low or val > high:
        raise ValueError(
            f"altitude_m ({val}) must be within [min_altitude_m, max_altitude_m] ([{low}, {high}])"
        )
    return val


class CorridorSurveyParams(BaseModel):
    """Validated coordinate-free corridor survey parameters (`FR-001`, `FR-021`)."""

    target_distance_m: float = Field(
        default=20.0,
        gt=0.0,
        description="Ordered cumulative 3D corridor path distance in meters (no fixed upper cap).",
    )
    distance_defaulted: bool = Field(
        default=False,
        description="True when SMEAC order omitted distance and the 20.0 m default was applied.",
    )
    return_to_origin: bool = Field(
        default=True,
        description="Reverse-path return-to-origin directive (defaults True unless far-end hold ordered).",
    )
    corridor_descriptor: str = Field(
        default="corridor",
        min_length=1,
        max_length=256,
        description="Natural-language corridor or passage context.",
    )
    intelligence_focus: list[str] = Field(
        default_factory=list,
        description="Objects or hazards of mission intelligence interest to capture without HITL blocking.",
    )
    min_altitude_m: float = Field(
        default=1.2,
        ge=0.5,
        description="Configurable lower floor altitude safety bound (m).",
    )
    max_altitude_m: float = Field(
        default=8.0,
        le=120.0,
        description="Configurable upper ceiling altitude safety bound (m).",
    )
    cruise_speed_ms: float = Field(
        default=1.5,
        ge=0.3,
        le=5.0,
        description="Nominal forward rolling flight speed (m/s).",
    )

    @model_validator(mode="after")
    def _validate_envelope(self) -> "CorridorSurveyParams":
        cleaned = self.corridor_descriptor.strip()
        if not cleaned:
            raise ValueError("corridor_descriptor must be a non-empty string")
        self.corridor_descriptor = cleaned
        if self.min_altitude_m >= self.max_altitude_m:
            raise ValueError(
                f"min_altitude_m ({self.min_altitude_m}) must be less than max_altitude_m ({self.max_altitude_m})"
            )
        normalized_focus: list[str] = []
        seen: set[str] = set()
        for item in self.intelligence_focus:
            s = str(item).strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                normalized_focus.append(s)
        self.intelligence_focus = normalized_focus
        return self


class PathBreadcrumb3D(BaseModel):
    """Single verified 3D corridor waypoint breadcrumb in origin-relative ENU coordinates."""

    index: int = Field(ge=1)
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    heading_deg: float = Field(ge=0.0, lt=360.0)
    cumulative_distance_m: float = Field(ge=0.0)
    estimated_width_m: float | None = Field(default=None, ge=0.0)
    estimated_height_m: float | None = Field(default=None, ge=0.0)
    snapshot_id: str = Field(min_length=1)


class CorridorSnapshotSummary(BaseModel):
    """Persisted corridor snapshot metadata with authenticated BFF proxy URL."""

    snapshot_id: uuid.UUID
    sequence_num: int = Field(ge=1)
    phase: str
    captured_at: datetime
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    heading_deg: float
    cumulative_distance_m: float
    visual_confidence: float
    corridor_open: bool
    estimated_width_m: float | None = None
    estimated_height_m: float | None = None
    analysis_latency_ms: float
    snapshot_uri: str
    byte_size: int = Field(gt=0, le=5 * 1024 * 1024)
    structural_tags: list[str] = Field(default_factory=list)
    image_proxy_url: str


class CorridorDecisionItem(BaseModel):
    """Auditable edge trajectory or operator override decision linked to snapshot IDs."""

    decision_id: uuid.UUID
    sequence_num: int = Field(ge=1)
    decision_authority: str
    command_source: str
    action: str
    from_phase: str
    to_phase: str
    target_rel_x_m: float
    target_rel_y_m: float
    target_rel_z_m: float
    commanded_heading_deg: float
    cleared_distance_m: float
    speed_ms: float
    trigger_snapshot_ids: list[str] = Field(default_factory=list)
    analysis_latency_ms: float | None = None
    rationale: str
    created_at: datetime


class CorridorFindingItem(BaseModel):
    """Intelligence finding, side branch, hazard, or structural cue logged during survey."""

    finding_id: uuid.UUID
    finding_type: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    matches_mission_interest: bool = False
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    heading_deg: float
    cumulative_distance_m: float
    snapshot_id: uuid.UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime


class CorridorIntelligenceReport(BaseModel):
    """Complete or live progressive C2 Corridor Intelligence Report (`SC-006`)."""

    survey_id: uuid.UUID
    swarm_id: uuid.UUID
    project_id: str
    smeac_order_id: uuid.UUID
    command_id: uuid.UUID
    lead_scout_drone_id: str
    staging_hold_drone_ids: list[str] = Field(default_factory=list)
    corridor_descriptor: str
    requested_distance_m: float
    distance_defaulted: bool = False
    surveyed_distance_m: float = 0.0
    return_to_origin: bool = True
    min_altitude_m: float
    max_altitude_m: float
    intelligence_focus: list[str] = Field(default_factory=list)
    phase: str
    status: str
    completion_reason: str | None = None
    origin_pose: dict[str, Any] | None = None
    discovered_path: list[dict[str, Any]] = Field(default_factory=list)
    structural_features: list[Any] = Field(default_factory=list)
    unexplored_branches: list[dict[str, Any]] = Field(default_factory=list)
    snapshots: list[CorridorSnapshotSummary] = Field(default_factory=list)
    decisions: list[CorridorDecisionItem] = Field(default_factory=list)
    findings: list[CorridorFindingItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class CorridorSurveyListItem(BaseModel):
    """Compact summary row when listing swarm corridor surveys."""

    survey_id: uuid.UUID
    swarm_id: uuid.UUID
    project_id: str
    lead_scout_drone_id: str
    staging_hold_drone_ids: list[str] = Field(default_factory=list)
    corridor_descriptor: str
    requested_distance_m: float
    distance_defaulted: bool = False
    surveyed_distance_m: float = 0.0
    return_to_origin: bool = True
    min_altitude_m: float
    max_altitude_m: float
    phase: str
    status: str
    completion_reason: str | None = None
    snapshot_count: int = 0
    decision_count: int = 0
    finding_count: int = 0
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class CorridorOverrideRequest(BaseModel):
    """Optional operator rationale supplied with Recall or Emergency Abort overrides."""

    rationale: str | None = Field(default=None, max_length=500)


class CorridorOverrideResponse(BaseModel):
    """Response confirming operator Recall or Emergency Abort override execution."""

    survey_id: uuid.UUID
    override_type: Literal["recall", "emergency_abort"]
    phase: str
    status: str
    message: str
    requested_at: datetime
