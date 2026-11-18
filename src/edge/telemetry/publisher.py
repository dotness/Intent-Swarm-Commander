"""Edge MQTT telemetry publisher with LWT, DDIL spooling, live-first reconnect, and backlog drain."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.edge.telemetry.spool import EdgeSpool
from src.edge.vision.inference import crop_detection_jpeg
from src.uservice.telemetry.models.contract.events import (
    EdgeAvoidanceCommand,
    SwarmTelemetryEvent,
    build_lwt_payload,
    build_telemetry_topic,
    classify_qos_and_priority,
)

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class EdgeTelemetryPublisher:
    """Publishes drone telemetry over MQTT with SQLite WAL DDIL buffering."""

    def __init__(
        self,
        project_id: str | None = None,
        swarm_id: str = "swarm-default",
        drone_id: str = "drone-1",
        spool: EdgeSpool | None = None,
        transport: Any = None,
        minio_store: Any = None,
        broker_host: str | None = None,
        broker_port: int | None = None,
    ) -> None:
        self.project_id = project_id or os.getenv("DEFAULT_PROJECT_ID", "default-theater")
        self.swarm_id = str(swarm_id)
        self.drone_id = drone_id
        self.spool = spool or EdgeSpool()
        self.transport = transport
        self.minio_store = minio_store
        self.broker_host = broker_host or os.getenv("MQTT_BROKER_HOST", "localhost")
        self.broker_port = int(broker_port or os.getenv("MQTT_BROKER_PORT", "1883"))

        self._paho_client: Any = None
        self._paho_connected = False
        self._drain_task: asyncio.Task[None] | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def connect(self) -> bool:
        """Connect native paho-mqtt client (if no custom transport was injected)."""
        if self.transport is not None:
            return bool(getattr(self.transport, "connected", True))


        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{self.swarm_id}-{self.drone_id}")
        lwt_topic = build_telemetry_topic(self.project_id, self.swarm_id, self.drone_id, "health")
        lwt_payload = json.dumps(build_lwt_payload(self.project_id, self.swarm_id, self.drone_id))
        client.will_set(lwt_topic, payload=lwt_payload, qos=1, retain=True)

        def _on_connect(_client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
            if reason_code == 0 or getattr(reason_code, "value", 1) == 0:
                self._paho_connected = True
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.drain_backlog(), self._loop)
            else:
                self._paho_connected = False

        def _on_disconnect(_client: Any, _userdata: Any, _flags: Any = None, _reason_code: Any = None, _properties: Any = None) -> None:
            self._paho_connected = False

        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect

        try:
            client.connect(self.broker_host, self.broker_port, keepalive=30)
            client.loop_start()
            self._paho_client = client
            return True
        except Exception as exc:
            logger.warning("MQTT broker connect failed (%s:%s): %s", self.broker_host, self.broker_port, exc)
            self._paho_connected = False
            return False

    async def _send_raw(self, topic: str, payload: str, qos: int) -> None:
        if self.transport is not None:
            res = self.transport.publish(topic, payload, qos=qos)
            if asyncio.iscoroutine(res):
                await res
            return

        if self._paho_client is None or not self._paho_client.is_connected():
            raise ConnectionError("MQTT client disconnected")

        info = self._paho_client.publish(topic, payload=payload, qos=qos)
        if qos > 0:
            await asyncio.to_thread(info.wait_for_publish, 3.0)
            if not info.is_published():
                raise ConnectionError("MQTT QoS 1 publish timed out")

    async def publish_event(
        self,
        event: SwarmTelemetryEvent,
        snapshot_local_path: str | None = None,
    ) -> bool:
        """Publish live event first; spool to SQLite WAL on disconnect."""
        topic = build_telemetry_topic(
            event.project_id,
            str(event.swarm_id),
            event.drone_id,
            event.metric_type,
        )
        qos, priority = classify_qos_and_priority(event)
        live_event = event.model_copy(update={"replayed": False})

        try:
            await self._send_raw(topic, live_event.model_dump_json(), qos=qos)
            return True
        except Exception as exc:
            logger.debug("Live publish failed (%s); spooling event_id=%s", exc, event.event_id)
            self.spool.enqueue(
                live_event,
                priority=priority,
                qos=qos,
                topic=topic,
                snapshot_local_path=snapshot_local_path,
            )
            return False

    async def publish_detection(
        self,
        lat: float,
        lon: float,
        alt_m: float,
        target_class: str,
        confidence: float,
        bbox: tuple[int, int, int, int] | list[int] | None = None,
        snapshot_bytes: bytes | None = None,
        mission_id: str | None = None,
        heading_deg: float = 0.0,
        speed_ms: float = 0.0,
        battery_pct: float = 100.0,
        flight_status: str = "active",
        frame: Any = None,
        drone_id: str | None = None,
    ) -> SwarmTelemetryEvent:
        """Upload or spool target JPEG snapshot and emit a QoS 1 detection event."""
        effective_drone_id = drone_id or self.drone_id
        if snapshot_bytes is None and frame is not None:
            if bbox is not None and len(bbox) == 4:
                crop_bbox = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
            elif hasattr(frame, "shape"):
                crop_bbox = (0, 0, int(frame.shape[1]), int(frame.shape[0]))
            else:
                crop_bbox = (0, 0, 1, 1)
            snapshot_bytes = crop_detection_jpeg(frame, crop_bbox)

        event = SwarmTelemetryEvent(
            project_id=self.project_id,
            swarm_id=self.swarm_id,
            drone_id=effective_drone_id,
            metric_type="detection",
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            heading_deg=heading_deg,
            speed_ms=speed_ms,
            battery_pct=battery_pct,
            flight_status=flight_status,
            target_class=target_class,
            confidence=confidence,
            bbox=list(bbox) if bbox else None,
            mission_id=mission_id,
        )

        snapshot_local_path: str | None = None
        if snapshot_bytes:
            s3_key = (
                f"projects/{self.project_id}/swarms/{self.swarm_id}/"
                f"drones/{effective_drone_id}/{event.event_id}.jpg"
            )
            uploaded = False
            if self.minio_store is not None:
                try:
                    await self.minio_store.put_object(
                        self.minio_store.SNAPSHOT_BUCKET,
                        s3_key,
                        snapshot_bytes,
                        content_type="image/jpeg",
                    )
                    event = event.model_copy(
                        update={"snapshot_uri": f"s3://{self.minio_store.SNAPSHOT_BUCKET}/{s3_key}"}
                    )
                    uploaded = True
                except Exception as exc:
                    logger.warning("Snapshot upload deferred to edge spool (%s)", exc)

            if not uploaded:
                snap_dir = (
                    Path(self.spool.db_path).parent / "snapshots"
                    if self.spool.db_path != ":memory:"
                    else Path("/tmp/isc_edge_snapshots")
                )
                snap_dir.mkdir(parents=True, exist_ok=True)
                snap_file = snap_dir / f"{event.event_id}.jpg"
                snap_file.write_bytes(snapshot_bytes)
                snapshot_local_path = str(snap_file)

        await self.publish_event(event, snapshot_local_path=snapshot_local_path)
        return event

    async def publish_avoidance_alert(
        self,
        *,
        lat: float,
        lon: float,
        alt_m: float,
        action: str,
        previous_heading_deg: float,
        commanded_heading_deg: float,
        course_delta_deg: float,
        obstacle_class: str | None = None,
        bypass_direction: str | None = None,
        confidence: float | None = None,
        bbox: tuple[int, int, int, int] | list[int] | None = None,
        trigger_detection_id: str | None = None,
        mission_id: str | None = None,
        flight_status: str = "bypassing",
        speed_ms: float = 0.0,
        battery_pct: float = 100.0,
        drone_id: str | None = None,
    ) -> SwarmTelemetryEvent:
        """Emit a QoS 1 alert telemetry event proving edge-autonomous course modification."""
        effective_drone_id = drone_id or self.drone_id
        cmd = EdgeAvoidanceCommand(
            action=action,  # type: ignore[arg-type]
            obstacle_class=obstacle_class,
            bypass_direction=bypass_direction,  # type: ignore[arg-type]
            previous_heading_deg=float(previous_heading_deg) % 360.0,
            commanded_heading_deg=float(commanded_heading_deg) % 360.0,
            course_delta_deg=max(-180.0, min(180.0, float(course_delta_deg))),
            trigger_detection_id=trigger_detection_id,
            llm_matched_target=False,
        )
        event = SwarmTelemetryEvent(
            project_id=self.project_id,
            swarm_id=self.swarm_id,
            drone_id=effective_drone_id,
            metric_type="alert",
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            heading_deg=float(commanded_heading_deg) % 360.0,
            speed_ms=max(0.0, float(speed_ms)),
            battery_pct=max(0.0, min(100.0, float(battery_pct))),
            flight_status=flight_status,
            target_class=obstacle_class,
            confidence=confidence,
            bbox=list(bbox) if bbox else None,
            mission_id=mission_id,
            extra=cmd.model_dump(mode="json"),
        )
        await self.publish_event(event)
        return event

    async def drain_backlog(self, batch_size: int = 50) -> int:
        """Drain unsynced spooled events with replayed=True without starving live sends."""
        records = self.spool.peek_unsynced(limit=batch_size)
        drained = 0
        for rec in records:
            try:
                payload_dict = json.loads(rec.payload_json)
                payload_dict["replayed"] = True

                if rec.snapshot_local_path and not payload_dict.get("snapshot_uri") and self.minio_store is not None:
                    local_file = Path(rec.snapshot_local_path)
                    if local_file.is_file():
                        s3_key = (
                            f"projects/{rec.project_id}/swarms/{rec.swarm_id}/"
                            f"drones/{rec.drone_id}/{rec.event_id}.jpg"
                        )
                        await self.minio_store.put_object(
                            self.minio_store.SNAPSHOT_BUCKET,
                            s3_key,
                            local_file.read_bytes(),
                            content_type="image/jpeg",
                        )
                        payload_dict["snapshot_uri"] = f"s3://{self.minio_store.SNAPSHOT_BUCKET}/{s3_key}"

                await self._send_raw(rec.topic, json.dumps(payload_dict), qos=rec.qos)
                self.spool.mark_synced(rec.row_id)
                drained += 1
            except Exception as exc:
                self.spool.increment_attempt(rec.row_id)
                logger.debug("Backlog replay paused at row id=%s (%s)", rec.row_id, exc)
                break
        return drained

    async def _drain_loop(self, interval_s: float) -> None:
        while self._running:
            try:
                await asyncio.sleep(interval_s)
                if self.spool.get_status(self.swarm_id).queued_rows > 0:
                    await self.drain_backlog()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Drain loop warning: %s", exc)

    def start(self, interval_s: float = 1.0) -> None:
        self._loop = asyncio.get_running_loop()
        self.connect()
        if not self._running:
            self._running = True
            self._drain_task = asyncio.create_task(self._drain_loop(interval_s))

    async def stop(self) -> None:
        self._running = False
        if self._drain_task is not None:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None
        if self._paho_client is not None:
            try:
                self._paho_client.loop_stop()
                self._paho_client.disconnect()
            except Exception:
                pass
            self._paho_client = None
