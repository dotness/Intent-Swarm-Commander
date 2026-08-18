"""Temporal operation tracking models."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, UUIDPrimaryKeyMixin


class OperationStatus(str, enum.Enum):
    CREATED = "created"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationInfo(UUIDPrimaryKeyMixin, Base):
    """Tracks the lifecycle of asynchronous Temporal workflows."""

    __tablename__ = "operation_info"

    workflow_id: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[OperationStatus] = mapped_column(
        Enum(OperationStatus), default=OperationStatus.CREATED, nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
