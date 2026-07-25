"""Pydantic schemas for SMEAC API request/response payloads."""

import uuid
from datetime import datetime

from pydantic import Field
from src.uservice.base.models.api.base import BaseModel


class SmeacOrderCreateRequest(BaseModel):
    """Payload for submitting a new SMEAC order."""

    situation: str = Field(min_length=1, description="Situational context")
    mission: str = Field(min_length=1, description="Mission objective statement")
    execution: str = Field(min_length=1, description="Execution plan")
    admin_logistics: str | None = Field(default=None, description="Admin and logistics")
    command_signal: str | None = Field(default=None, description="Command and signal details")


class SmeacOrderResponse(BaseModel):
    """Response after creating a SMEAC order."""

    order_id: uuid.UUID
    status: str
    swarm_instance_id: uuid.UUID
    parsed_fields: dict[str, str]
    created_at: datetime


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


class OrderStatusResponse(BaseModel):
    """Full status of a submitted SMEAC order."""

    order_id: uuid.UUID
    status: str
    commands: list[SwarmCommandResponse] = []
    constraint_violations: list = []
