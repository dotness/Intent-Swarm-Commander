"""Constraint Violation domain model."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, UUIDPrimaryKeyMixin


class ViolationSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConstraintViolation(UUIDPrimaryKeyMixin, Base):
    """A safety check failure record."""

    __tablename__ = "constraint_violations"

    swarm_command_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("swarm_commands.id"), nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[ViolationSeverity] = mapped_column(Enum(ViolationSeverity), nullable=False)
    actual_value: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed_range: Mapped[str] = mapped_column(String(255), nullable=False)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
