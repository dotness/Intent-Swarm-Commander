"""Pydantic contracts for dynamic threat zones, spatial evaluations, and target lineage."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from src.uservice.base.models.api.base import BaseModel

ThreatType = Literal["SAM", "EW", "AA", "RESTRICTED", "WEATHER"]
ThreatSeverity = Literal["critical", "high", "medium", "low"]


class ThreatZoneCreateRequest(BaseModel):
    project_id: str = Field(default="default-theater", min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    threat_type: ThreatType = "RESTRICTED"
    severity: ThreatSeverity = "high"
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    radius_m: float = Field(..., gt=0.0)
    min_alt_m: float = Field(default=0.0, ge=0.0)
    max_alt_m: float = Field(default=500.0, ge=0.0)
    polygon_geojson: dict[str, Any] | None = None
    source: str = Field(default="commander", min_length=1)


class ThreatZoneResponse(BaseModel):
    threat_id: str
    project_id: str
    name: str
    threat_type: str
    severity: str
    lat: float
    lon: float
    radius_m: float
    min_alt_m: float = 0.0
    max_alt_m: float = 500.0
    polygon_geojson: dict[str, Any] | None = None
    active: bool = True
    source: str = "commander"
    created_at: str | None = None
    created_by: str | None = None
    deactivated_at: str | None = None
    deactivated_by: str | None = None
    deactivation_reason: str | None = None


class ThreatListData(BaseModel):
    project_id: str
    threats: list[ThreatZoneResponse] = Field(default_factory=list)


class ThreatDeactivateRequest(BaseModel):
    project_id: str = Field(default="default-theater", min_length=1, max_length=64)
    reason: str = Field(..., min_length=5)

    @field_validator("reason")
    @classmethod
    def _validate_non_blank_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 5:
            raise ValueError("Deactivation reason must contain at least 5 non-whitespace characters")
        return stripped


class ThreatDeactivateResponse(BaseModel):
    threat_id: str
    active: bool
    deactivated_at: str | None = None
    deactivated_by: str | None = None
    deactivation_reason: str | None = None


class ThreatConflictDetail(BaseModel):
    threat_id: str
    name: str
    threat_type: str = "RESTRICTED"
    severity: str = "high"
    distance_m: float = 0.0
    source: str = "memgraph"


class RouteThreatEvaluation(BaseModel):
    conflicts: list[ThreatConflictDetail] = Field(default_factory=list)


class TargetEntitySummary(BaseModel):
    target_id: str
    project_id: str
    canonical_class: str
    status: str = "auto_correlated"
    first_seen_at: str
    last_seen_at: str
    last_lat: float
    last_lon: float
    observation_count: int = 1
    latest_event_id: str | None = None
    latest_snapshot_uri: str | None = None


class TargetListData(BaseModel):
    project_id: str
    items: list[TargetEntitySummary] = Field(default_factory=list)


class TargetObservationItem(BaseModel):
    event_id: str
    drone_id: str
    swarm_id: str
    mission_id: str | None = None
    target_class: str
    confidence: float
    lat: float
    lon: float
    alt_m: float = 0.0
    detected_at: str
    snapshot_uri: str | None = None
    snapshot_proxy_url: str | None = None
    match_method: str = "auto_spatio_temporal"
    distance_m: float = 0.0
    delta_s: float = 0.0
    verified_by_analyst: bool = False


class TargetLineageResponse(BaseModel):
    target_id: str
    project_id: str
    canonical_class: str
    status: str
    observation_count: int
    first_seen_at: str
    last_seen_at: str
    observations: list[TargetObservationItem] = Field(default_factory=list)


class TargetReviewRequest(BaseModel):
    project_id: str = Field(default="default-theater", min_length=1, max_length=64)
    action: Literal["confirm", "split_event", "mark_false_positive"]
    split_event_id: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_split_requires_event(self) -> "TargetReviewRequest":
        if self.action == "split_event" and not (self.split_event_id and self.split_event_id.strip()):
            raise ValueError("split_event action requires a non-empty split_event_id")
        return self
