"""HITL API contract schemas."""

import uuid
from pydantic import Field
from src.uservice.base.models.api.base import BaseModel


class HitlDecideRequest(BaseModel):
    decision: str = Field(description="'approved' or 'rejected'")
    rationale: str | None = Field(default=None)


class HitlDecideResponse(BaseModel):
    decision_id: uuid.UUID
    decision: str
    command_status: str
    decided_at: str
