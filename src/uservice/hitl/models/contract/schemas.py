"""HITL API contract schemas with threat-override justification validation."""

import uuid
from typing import Any
from pydantic import Field
from src.uservice.base.models.api.base import BaseModel


class HitlDecideRequest(BaseModel):
    decision: str = Field(description="'approved' or 'rejected'")
    rationale: str | None = Field(default=None)
    override_justification: str | None = Field(default=None)


class HitlDecideResponse(BaseModel):
    decision_id: uuid.UUID
    decision: str
    command_status: str
    decided_at: str
    is_threat_override: bool = False
    override_justification: str | None = None


class HitlPendingItem(BaseModel):
    decision_id: str
    command_id: str
    action_summary: str
    timeout_seconds: int
    status: str
    is_threat_override: bool = False
    requires_override_justification: bool = False
    threat_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    drone_id: str | None = None
    detection_event_id: str | None = None
    snapshot_url: str | None = None
    target_class: str | None = None
    confidence: float | None = None
