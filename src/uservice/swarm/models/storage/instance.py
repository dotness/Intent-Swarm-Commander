"""Swarm Instance domain model."""

import enum
import uuid

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, UUIDMixin, TimestampMixin, PermissionMixin


class SwarmStatus(str, enum.Enum):
    PROVISIONING = "provisioning"
    READY = "ready"
    ACTIVE = "active"
    DRAINING = "draining"
    TERMINATED = "terminated"
    FAILED = "failed"


class SwarmInstance(UUIDMixin, TimestampMixin, PermissionMixin, Base):
    """A registered, running swarm container."""

    __tablename__ = "swarm_instances"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String, default=SwarmStatus.PROVISIONING.value, nullable=False,
    )
    drone_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
