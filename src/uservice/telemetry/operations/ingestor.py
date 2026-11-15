"""Async MQTT wildcard ingestor subscribing to edge push telemetry and detections."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import os
from typing import Any, Awaitable, Callable

from src.uservice.telemetry.models.contract.events import (
    WILDCARD_TELEMETRY_TOPIC,
    SwarmTelemetryEvent,
    validate_topic_matches_event,
)
from src.uservice.telemetry.models.storage.live_state import LiveTelemetryStore, SwarmLiveState
from src.uservice.telemetry.operations.compactor import ParquetCompactor

import aiomqtt

logger = logging.getLogger(__name__)


class TelemetryIngestor:
    """Consumes push MQTT messages on telemetry/projects/+/swarms/+/+/+."""

    def __init__(
        self,
        live_store: LiveTelemetryStore,
        compactor: ParquetCompactor,
        detection_callback: Callable[[SwarmTelemetryEvent], Awaitable[None]] | None = None,
        transport: Any = None,
        broker_host: str | None = None,
        broker_port: int | None = None,
        db_session_factory: Any = None,
    ) -> None:
        self.live_store = live_store
        self.compactor = compactor
        self.detection_callback = detection_callback
        self.transport = transport
        self.broker_host = broker_host or os.getenv("MQTT_BROKER_HOST", "localhost")
        self.broker_port = int(broker_port or os.getenv("MQTT_BROKER_PORT", "1883"))
        self.db_session_factory = db_session_factory
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def handle_raw_message(self, topic: str, payload: bytes | str) -> bool:
        """Validate, deduplicate, project, compact, and route detection events."""
        raw_str = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        event = SwarmTelemetryEvent.model_validate_json(raw_str)
        validate_topic_matches_event(topic, event)

        if not self.live_store.record_event(event):
            return False

        self.compactor.enqueue(event)

        if self.db_session_factory is not None:
            await self._upsert_live_state(event)

        if event.metric_type == "detection" and self.detection_callback is not None:
            await self.detection_callback(event)

        return True

    async def _upsert_live_state(self, event: SwarmTelemetryEvent) -> None:
        key_id = f"{event.project_id}:{event.swarm_id}:{event.drone_id}"
        async with self.db_session_factory() as session:
            row = await session.get(SwarmLiveState, key_id)
            now = datetime.now(timezone.utc)
            if row is None:
                row = SwarmLiveState(
                    id=key_id,
                    project_id=event.project_id,
                    swarm_id=str(event.swarm_id),
                    drone_id=event.drone_id,
                    metric_type=event.metric_type,
                    lat=event.lat,
                    lon=event.lon,
                    alt_m=event.alt_m,
                    heading_deg=event.heading_deg,
                    speed_ms=event.speed_ms,
                    battery_pct=event.battery_pct,
                    flight_status=event.flight_status,
                    last_event_id=str(event.event_id),
                    replayed=event.replayed,
                    last_seen_utc=now,
                )
                session.add(row)
            else:
                if (not event.replayed) or event.timestamp >= row.last_seen_utc:
                    row.metric_type = event.metric_type
                    row.lat = event.lat
                    row.lon = event.lon
                    row.alt_m = event.alt_m
                    row.heading_deg = event.heading_deg
                    row.speed_ms = event.speed_ms
                    row.battery_pct = event.battery_pct
                    row.flight_status = event.flight_status
                    row.last_event_id = str(event.event_id)
                    row.replayed = event.replayed
                    row.last_seen_utc = now
            await session.commit()

    async def _subscribe_loop(self) -> None:
        while self._running:
            try:
                async with aiomqtt.Client(hostname=self.broker_host, port=self.broker_port) as client:
                    await client.subscribe(WILDCARD_TELEMETRY_TOPIC, qos=1)
                    logger.info("TelemetryIngestor subscribed to %s on %s:%s", WILDCARD_TELEMETRY_TOPIC, self.broker_host, self.broker_port)
                    async for message in client.messages:
                        if not self._running:
                            break
                        try:
                            await self.handle_raw_message(str(message.topic), message.payload)
                        except Exception as msg_exc:
                            logger.warning("Dropped malformed MQTT message on %s: %s", message.topic, msg_exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("MQTT ingestor connection retry in 3s (%s:%s): %s", self.broker_host, self.broker_port, exc)
                await asyncio.sleep(3.0)

    def start(self) -> None:
        """Start consuming telemetry from injected transport or live Mosquitto broker."""
        if self.transport is not None:
            self.transport.subscribe(WILDCARD_TELEMETRY_TOPIC, self.handle_raw_message)
            self._running = True
            return
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._subscribe_loop())

    async def stop(self) -> None:
        self._running = False
        if self.transport is not None and hasattr(self.transport, "unsubscribe"):
            self.transport.unsubscribe(self.handle_raw_message)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
