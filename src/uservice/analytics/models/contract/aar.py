"""Pydantic contract schemas for DuckDB / OLAP After-Action Review (AAR) queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from src.uservice.base.models.api.base import BaseModel

AarQueryType = Literal["summary", "trajectory", "battery_decay", "detections"]


class AarQueryRequest(BaseModel):
    project_id: str = Field(default="default-theater", min_length=1, max_length=64)
    query_type: AarQueryType = "summary"
    swarm_id: str | None = None
    drone_id: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None
    limit: int = Field(default=2000, ge=1, le=20000)


class AarQueryResponse(BaseModel):
    project_id: str
    query_type: AarQueryType
    execution_ms: float
    row_count: int
    rows: list[dict[str, Any]] = Field(default_factory=list)
    engine: str = "duckdb"
