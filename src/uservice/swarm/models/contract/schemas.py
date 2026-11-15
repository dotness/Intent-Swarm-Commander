"""Swarm API contract schemas."""

import uuid
from pydantic import Field
from src.uservice.base.models.api.base import BaseModel


class CreateSwarmRequest(BaseModel):
    name: str = Field(min_length=1, description="Human-readable swarm name")
    drone_count: int = Field(ge=1, description="Number of drones")
    project_id: str = Field(default="default-theater", min_length=1, max_length=64)


class SwarmResponse(BaseModel):
    id: uuid.UUID
    name: str
    project_id: str = "default-theater"
    status: str
    drone_count: int
    endpoint_url: str | None
    created_at: str
    created_by: str
