"""HITL Decision domain model."""

import enum
import uuid

from sqlalchemy import Boolean, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, UUIDMixin, TimestampMixin, PermissionMixin


class DecisionType(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT_AUTO_APPROVED = "timeout_auto_approved"
    TIMEOUT_AUTO_REJECTED = "timeout_auto_rejected"


class HitlDecision(UUIDMixin, TimestampMixin, PermissionMixin, Base):
    """A recorded approval/rejection from a human commander."""

    __tablename__ = "hitl_decisions"

    project_id: Mapped[str] = mapped_column(
        String(128), default="default-theater", nullable=False, index=True,
    )
    swarm_command_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    commander_id: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    action_summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_threat_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    threat_zone_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
