"""Pydantic schemas for SMEAC API request/response payloads."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field
from src.uservice.base.models.api.base import BaseModel


class SmeacOrderCreateRequest(BaseModel):
    """Payload for submitting a new SMEAC order."""

    project_id: str = Field(default="default-theater", min_length=1, max_length=64, description="Theater / project identifier")
    situation: str = Field(min_length=1, description="Situational context")
    mission: str = Field(min_length=1, description="Mission objective statement")
    execution: str = Field(min_length=1, description="Execution plan")
    admin_logistics: str | None = Field(default=None, description="Admin and logistics")
    command_signal: str | None = Field(default=None, description="Command and signal details")
    draft_source_refs: list[str] | None = Field(
        default=None,
        description="Cited source IDs when order originates from a Copilot draft",
    )


class SwarmCommandResponse(BaseModel):
    """Individual command in an order status response."""

    id: uuid.UUID
    mission_type: str
    formation_type: str
    target_area: dict
    target_object_class: str | None
    drone_count: int
    altitude_m: float | None
    is_high_impact: bool
    verification_status: str = "pending"


class SmeacOrderResponse(BaseModel):
    """Response after creating a SMEAC order."""

    order_id: uuid.UUID
    project_id: str = "default-theater"
    status: str
    swarm_instance_id: uuid.UUID
    parsed_fields: dict[str, str]
    created_at: datetime
    commands: list[SwarmCommandResponse] = []
    reasoning: str | None = None
    threat_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    pending_hitl_decision_id: uuid.UUID | None = None
    draft_source_refs: list[str] | None = None


class OrderStatusResponse(BaseModel):
    """Full status of a submitted SMEAC order."""

    order_id: uuid.UUID
    project_id: str = "default-theater"
    status: str
    commands: list[SwarmCommandResponse] = []
    constraint_violations: list = []
    threat_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    pending_hitl_decision_id: uuid.UUID | None = None
    draft_source_refs: list[str] | None = None


class SmeacDraftRequest(BaseModel):
    """Read-only copilot draft request grounded on AAR & Memgraph threat intelligence."""

    project_id: str = Field(default="default-theater", min_length=1, max_length=64)
    commander_intent: str = Field(..., min_length=5, max_length=2000)
    include_aar_context: bool = True
    include_threat_context: bool = True


class SmeacCitation(BaseModel):
    """Verifiable provenance reference cited inside a generated SMEAC draft."""

    source_type: Literal["aar_summary", "threat_zone", "target_entity"]
    source_id: str
    label: str


class SmeacDraftData(BaseModel):
    """Non-executing SMEAC draft returned for commander inspection before order submission."""

    project_id: str
    draft_only: Literal[True] = True
    status: Literal["draft"] = "draft"
    situation: str
    mission: str
    execution: str
    admin_logistics: str
    command_signal: str
    source_citations: list[SmeacCitation] = Field(default_factory=list)
    threat_warning_summary: list[str] = Field(default_factory=list)

