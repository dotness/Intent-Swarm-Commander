"""SQLAlchemy ORM storage models for Corridor Surveys, Snapshots, Decisions, and Findings."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CorridorSurvey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Root aggregate representing a coordinate-free 3D corridor survey and report state."""

    __tablename__ = "corridor_surveys"

    project_id: Mapped[str] = mapped_column(
        String(64), default="default-theater", nullable=False, index=True,
    )
    swarm_instance_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    smeac_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("smeac_orders.id"), nullable=False, index=True,
    )
    command_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    lead_scout_drone_id: Mapped[str] = mapped_column(
        String(64), default="drone-1", nullable=False,
    )
    staging_hold_drone_ids: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False,
    )
    corridor_descriptor: Mapped[str] = mapped_column(String(256), nullable=False)
    requested_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    distance_defaulted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    surveyed_distance_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    return_to_origin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_altitude_m: Mapped[float] = mapped_column(Float, default=1.2, nullable=False)
    max_altitude_m: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    intelligence_focus: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    phase: Mapped[str] = mapped_column(String(48), default="initializing", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="dispatched", nullable=False)
    completion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin_pose: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    discovered_path: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    structural_features: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    unexplored_branches: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CorridorSnapshot(UUIDPrimaryKeyMixin, Base):
    """Persists every captured visual snapshot across all corridor survey phases (`FR-020`)."""

    __tablename__ = "corridor_snapshots"

    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor_surveys.id"), nullable=False, index=True,
    )
    drone_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(48), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    rel_x_m: Mapped[float] = mapped_column(Float, nullable=False)
    rel_y_m: Mapped[float] = mapped_column(Float, nullable=False)
    rel_z_m: Mapped[float] = mapped_column(Float, nullable=False)
    heading_deg: Mapped[float] = mapped_column(Float, nullable=False)
    cumulative_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    visual_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    corridor_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    estimated_width_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_uri: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    structural_tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class CorridorTrajectoryDecision(UUIDPrimaryKeyMixin, Base):
    """Auditable record linking every edge trajectory update or override to triggering snapshots."""

    __tablename__ = "corridor_trajectory_decisions"

    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor_surveys.id"), nullable=False, index=True,
    )
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_authority: Mapped[str] = mapped_column(String(32), nullable=False)
    command_source: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    from_phase: Mapped[str] = mapped_column(String(48), nullable=False)
    to_phase: Mapped[str] = mapped_column(String(48), nullable=False)
    target_rel_x_m: Mapped[float] = mapped_column(Float, nullable=False)
    target_rel_y_m: Mapped[float] = mapped_column(Float, nullable=False)
    target_rel_z_m: Mapped[float] = mapped_column(Float, nullable=False)
    commanded_heading_deg: Mapped[float] = mapped_column(Float, nullable=False)
    cleared_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    speed_ms: Mapped[float] = mapped_column(Float, nullable=False)
    trigger_snapshot_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    analysis_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )


class CorridorFinding(UUIDPrimaryKeyMixin, Base):
    """Structured intelligence observation, side branch, or hazard discovered along the corridor."""

    __tablename__ = "corridor_findings"

    survey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("corridor_surveys.id"), nullable=False, index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    matches_mission_interest: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    rel_x_m: Mapped[float] = mapped_column(Float, nullable=False)
    rel_y_m: Mapped[float] = mapped_column(Float, nullable=False)
    rel_z_m: Mapped[float] = mapped_column(Float, nullable=False)
    heading_deg: Mapped[float] = mapped_column(Float, nullable=False)
    cumulative_distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("corridor_snapshots.id"), nullable=True,
    )
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
