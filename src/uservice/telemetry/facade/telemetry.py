"""Telemetry Domain Facade — live MQTT push projection and ingestion diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.uservice.base.errors import ResourceDoesNotExist
from src.uservice.base.facade.base import DomainFacade
from src.uservice.swarm.facade.swarm import SwarmFacade
from src.uservice.telemetry.models.contract.events import (
    DroneTelemetryItem,
    DroneTelemetryPosition,
    TelemetryProjectionResponse,
)
from src.uservice.telemetry.models.storage.live_state import LiveTelemetryStore, SwarmLiveState

logger = logging.getLogger(__name__)

_DEFAULT_LIVE_STORE = LiveTelemetryStore()


def get_default_live_store() -> LiveTelemetryStore:
    """Return process-wide LiveTelemetryStore singleton."""
    return _DEFAULT_LIVE_STORE


class TelemetryFacade(DomainFacade):
    """Facade exposing MQTT-backed swarm telemetry projections without edge HTTP polling."""

    def __init__(
        self,
        session: AsyncSession,
        user: dict[str, Any],
        live_store: LiveTelemetryStore | None = None,
        compactor: Any = None,
    ) -> None:
        super().__init__(session=session, user=user)
        self.live_store = live_store or _DEFAULT_LIVE_STORE
        self.compactor = compactor
        self.stale_threshold_s = float(os.getenv("TELEMETRY_STALE_THRESHOLD_S", "10.0"))

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        user: dict[str, Any],
        live_store: LiveTelemetryStore | None = None,
        compactor: Any = None,
    ) -> "TelemetryFacade":
        return cls(session=session, user=user, live_store=live_store, compactor=compactor)

    async def get_swarm_telemetry_projection(
        self,
        swarm_id: uuid.UUID,
        project_id: str | None = None,
    ) -> TelemetryProjectionResponse:
        """Project latest live or stale pushed MQTT telemetry for a swarm."""
        self.require_scope("swarm:read")

        swarm_facade = await SwarmFacade.create(session=self.session, user=self.user)
        try:
            swarm = await swarm_facade.get_swarm_details(swarm_id)
        except ResourceDoesNotExist as exc:
            raise ResourceDoesNotExist(f"Swarm {swarm_id} not found") from exc

        effective_project_id = project_id or swarm.get("project_id") or "default-theater"
        source, last_seen, drones = self.live_store.get_swarm_drones(
            project_id=effective_project_id,
            swarm_id=str(swarm_id),
            stale_threshold_s=self.stale_threshold_s,
        )

        # Check persisted SwarmLiveState rows if in-memory store has no events yet
        if not drones:
            stmt = select(SwarmLiveState).where(
                SwarmLiveState.project_id == effective_project_id,
                SwarmLiveState.swarm_id == str(swarm_id),
            )
            res = await self.session.execute(stmt)
            rows = res.scalars().all()
            if rows:
                now = datetime.now(timezone.utc)
                any_fresh = False
                for row in rows:
                    seen = row.last_seen_utc
                    if seen.tzinfo is None:
                        seen = seen.replace(tzinfo=timezone.utc)
                    age_s = (now - seen).total_seconds()
                    is_stale = age_s > self.stale_threshold_s or row.flight_status == "offline_lwt"
                    if not is_stale:
                        any_fresh = True
                    if last_seen is None or seen > last_seen:
                        last_seen = seen
                    drones.append(
                        DroneTelemetryItem(
                            id=f"{swarm_id}-{row.drone_id}",
                            drone_id=row.drone_id,
                            status=row.flight_status,
                            battery_pct=row.battery_pct,
                            position=DroneTelemetryPosition(lat=row.lat, lng=row.lon, alt_m=row.alt_m),
                            heading=row.heading_deg,
                            speed=row.speed_ms,
                            current_mission=row.flight_status,
                            stale=is_stale,
                        )
                    )
                source = "mqtt_live" if any_fresh else "mqtt_stale"

        return TelemetryProjectionResponse(
            swarm_id=str(swarm_id),
            project_id=effective_project_id,
            telemetry_source=source,  # type: ignore[arg-type]
            last_seen_utc=last_seen.isoformat() if last_seen else None,
            drones=drones,
        )

    async def get_swarm_diagnostics(
        self,
        swarm_id: uuid.UUID,
        project_id: str | None = None,
        compactor_pending: int | None = None,
    ) -> dict[str, Any]:
        """Return push telemetry ingestion & staleness diagnostics for a swarm."""
        projection = await self.get_swarm_telemetry_projection(swarm_id=swarm_id, project_id=project_id)
        if compactor_pending is None:
            compactor_pending = (
                int(self.compactor.pending_count())
                if self.compactor is not None and hasattr(self.compactor, "pending_count")
                else 0
            )
        return {
            "swarm_id": projection.swarm_id,
            "project_id": projection.project_id,
            "telemetry_source": projection.telemetry_source,
            "active_drone_count": len(projection.drones),
            "stale_drone_count": sum(1 for d in projection.drones if d.stale),
            "total_ingested_events": self.live_store.total_events_ingested(),
            "compactor_buffer_depth": compactor_pending,
            "last_seen_utc": projection.last_seen_utc,
        }
