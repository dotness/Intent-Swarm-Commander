"""Live telemetry state projection (ORM + async-safe in-memory LRU deduplicating store)."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import threading
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.uservice.database.base import Base
from src.uservice.telemetry.models.contract.events import (
    DroneTelemetryItem,
    DroneTelemetryPosition,
    SwarmTelemetryEvent,
    is_edge_autonomous_alert,
)


class SwarmLiveState(Base):
    """Latest known per-drone telemetry snapshot persisted for restart resilience."""

    __tablename__ = "swarm_live_states"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default-theater")
    swarm_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    drone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lon: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alt_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    heading_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    speed_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    battery_pct: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    flight_status: Mapped[str] = mapped_column(String(64), nullable=False, default="idle")
    last_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    replayed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class LiveTelemetryStore:
    """In-memory async-safe latest telemetry state + bounded LRU event_id deduplicator."""

    def __init__(self, dedup_capacity: int = 10_000) -> None:
        self.dedup_capacity = dedup_capacity
        self._lock = threading.Lock()
        self._seen_event_ids: OrderedDict[str, None] = OrderedDict()
        # (project_id, swarm_id, drone_id) -> {"event": SwarmTelemetryEvent, "received_at": datetime}
        self._drones: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._total_ingested = 0

    def is_duplicate(self, event_id: str) -> bool:
        """Check whether an event_id was recently processed."""
        with self._lock:
            return event_id in self._seen_event_ids

    def record_event(self, event: SwarmTelemetryEvent) -> bool:
        """Record a validated telemetry event if not already deduplicated.

        Returns True when accepted as new, False when deduplicated.
        """
        eid = str(event.event_id)
        now = datetime.now(timezone.utc)
        with self._lock:
            if eid in self._seen_event_ids:
                self._seen_event_ids.move_to_end(eid)
                return False
            self._seen_event_ids[eid] = None
            while len(self._seen_event_ids) > self.dedup_capacity:
                self._seen_event_ids.popitem(last=False)

            key = (event.project_id, str(event.swarm_id), event.drone_id)
            prev = self._drones.get(key)
            prev_avoidance = prev.get("last_avoidance") if prev else None
            last_avoidance = (
                {**(event.extra or {}), "event_id": eid, "timestamp": event.timestamp.isoformat()}
                if is_edge_autonomous_alert(event)
                else prev_avoidance
            )
            # Only overwrite live projection if incoming event is live or newer than last stored
            if prev is None or (not event.replayed) or event.timestamp >= prev["event"].timestamp:
                self._drones[key] = {
                    "event": event,
                    "received_at": now,
                    "last_avoidance": last_avoidance,
                }
            elif last_avoidance is not None and prev is not None:
                prev["last_avoidance"] = last_avoidance
            self._total_ingested += 1
            return True

    def get_swarm_drones(
        self,
        project_id: str,
        swarm_id: str,
        stale_threshold_s: float = 10.0,
    ) -> tuple[str, datetime | None, list[DroneTelemetryItem]]:
        """Project current drones for a swarm, flagging live vs stale MQTT feeds."""
        now = datetime.now(timezone.utc)
        drones: list[DroneTelemetryItem] = []
        latest_ts: datetime | None = None
        any_fresh = False

        with self._lock:
            matching = [
                entry
                for (pid, sid, _), entry in self._drones.items()
                if pid == project_id and sid == str(swarm_id)
            ]

        for entry in matching:
            ev: SwarmTelemetryEvent = entry["event"]
            recv_at: datetime = entry["received_at"]
            age_s = (now - recv_at).total_seconds()
            is_stale = age_s > stale_threshold_s or ev.flight_status == "offline_lwt"
            if not is_stale:
                any_fresh = True
            if latest_ts is None or recv_at > latest_ts:
                latest_ts = recv_at

            drones.append(
                DroneTelemetryItem(
                    id=f"{swarm_id}-{ev.drone_id}",
                    drone_id=ev.drone_id,
                    status=ev.flight_status,
                    battery_pct=ev.battery_pct,
                    position=DroneTelemetryPosition(lat=ev.lat, lng=ev.lon, alt_m=ev.alt_m),
                    heading=ev.heading_deg,
                    speed=ev.speed_ms,
                    current_mission=ev.flight_status,
                    stale=is_stale,
                    last_avoidance_event=entry.get("last_avoidance"),
                )
            )

        if not drones or not any_fresh:
            return ("mqtt_stale", latest_ts, drones)
        return ("mqtt_live", latest_ts, drones)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._drones)

    def total_events_ingested(self) -> int:
        with self._lock:
            return self._total_ingested
