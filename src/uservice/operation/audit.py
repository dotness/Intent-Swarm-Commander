"""Audit Event domain model and logging helper."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, UUIDPrimaryKeyMixin


class AuditEventType(str, enum.Enum):
    SMEAC_SUBMITTED = "smeac_submitted"
    COMMAND_GENERATED = "command_generated"
    AUTH_GRANTED = "auth_granted"
    AUTH_DENIED = "auth_denied"
    HITL_REQUESTED = "hitl_requested"
    HITL_DECIDED = "hitl_decided"
    CONSTRAINT_PASSED = "constraint_passed"
    CONSTRAINT_VIOLATED = "constraint_violated"
    SWARM_PROVISIONED = "swarm_provisioned"
    SWARM_TERMINATED = "swarm_terminated"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_FAILED = "command_failed"


class ActorType(str, enum.Enum):
    COMMANDER = "commander"
    AGENT = "agent"
    SYSTEM = "system"


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Immutable log entry for significant system actions."""

    __tablename__ = "audit_events"

    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType), nullable=False)
    swarm_instance_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
