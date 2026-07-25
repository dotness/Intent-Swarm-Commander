"""HITL Decision domain model."""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
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

    swarm_command_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("swarm_commands.id"), nullable=False,
    )
    commander_id: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
