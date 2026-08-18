"""SMEAC Order domain model (SQLAlchemy ORM + Pydantic API schemas)."""

import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, TimestampMixin, UUIDMixin, PermissionMixin


# ── ORM Enum ─────────────────────────────────────────────────────────────

class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PARSING = "parsing"
    TRANSLATED = "translated"
    VERIFIED = "verified"
    PENDING_HITL = "pending_hitl"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


# ── ORM Model ────────────────────────────────────────────────────────────

class SmeacOrder(UUIDMixin, TimestampMixin, PermissionMixin, Base):
    """A structured military order representing commander intent."""

    __tablename__ = "smeac_orders"

    commander_id: Mapped[str] = mapped_column(String(255), nullable=False)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    execution: Mapped[str] = mapped_column(Text, nullable=False)
    admin_logistics: Mapped[str | None] = mapped_column(Text, nullable=True)
    command_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    swarm_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("swarm_instances.id"), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String, default=OrderStatus.SUBMITTED.value, nullable=False,
    )
