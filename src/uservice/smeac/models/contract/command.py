"""Swarm Command domain model — the atomic unit of execution."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base, UUIDPrimaryKeyMixin


# ── Enums ─────────────────────────────────────────────────────────────────

class MissionType(str, enum.Enum):
    RECON = "recon"
    PATROL = "patrol"
    STRIKE = "strike"
    TRANSPORT = "transport"
    ESCORT = "escort"
    ABORT = "abort"


class FormationType(str, enum.Enum):
    LINE = "line"
    WEDGE = "wedge"
    DIAMOND = "diamond"
    SPREAD = "spread"
    STACK = "stack"


class CommandPriority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


# ── High-impact mission types ────────────────────────────────────────────

HIGH_IMPACT_MISSIONS = frozenset({MissionType.STRIKE, MissionType.ABORT})


# ── ORM Model ────────────────────────────────────────────────────────────

class SwarmCommand(UUIDPrimaryKeyMixin, Base):
    """A coarse-grained operator derived from a SMEAC Order."""

    __tablename__ = "swarm_commands"

    smeac_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("smeac_orders.id"), nullable=False,
    )
    mission_type: Mapped[MissionType] = mapped_column(Enum(MissionType), nullable=False)
    formation_type: Mapped[FormationType] = mapped_column(Enum(FormationType), nullable=False)
    target_area: Mapped[str] = mapped_column(Text, nullable=False, doc="GeoJSON string")
    target_object_class: Mapped[str | None] = mapped_column(
        String(128), nullable=True, doc="YOLO-E class to identify (e.g. 'vehicle')",
    )
    drone_count: Mapped[int] = mapped_column(Integer, nullable=False)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[CommandPriority] = mapped_column(
        Enum(CommandPriority), default=CommandPriority.NORMAL, nullable=False,
    )
    is_high_impact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
