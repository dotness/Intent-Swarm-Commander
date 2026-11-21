"""Edge MQTT telemetry publisher with LWT, DDIL spooling, live-first reconnect, and backlog drain."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
import uuid

import cv2
import paho.mqtt.client as mqtt

from src.edge.telemetry.spool import EdgeSpool
from src.edge.vision.inference import crop_detection_jpeg
from src.uservice.analytics.operations.minio_store import validate_object_key
from src.uservice.telemetry.models.contract.events import (
    CORRIDOR_SURVEY_EVENT_TYPES,
    CorridorSnapshotPayload,
    EdgeAvoidanceCommand,
    PROJECT_SLUG_RE,
    SwarmTelemetryEvent,
    build_lwt_payload,
    build_telemetry_topic,
    classify_qos_and_priority,
    corridor_phase_to_flight_status,
)

MAX_CORRIDOR_SNAPSHOT_BYTES = 5 * 1024 * 1024
_JPEG_MAGIC = b"\xff\xd8\xff"
_DRONE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _normalize_heading_deg(heading_deg: float) -> float:
    h = float(heading_deg) % 360.0
    return 0.0 if h >= 360.0 or h < 0.0 else h


def validate_corridor_snapshot_bytes(jpeg_bytes: bytes) -> bytes:
    """Validate non-empty JPEG magic bytes and <= 5 MB size bound (`FR-020`)."""
    if not isinstance(jpeg_bytes, (bytes, bytearray)) or not jpeg_bytes:
        raise ValueError("Corridor snapshot payload must be non-empty bytes")
    raw = bytes(jpeg_bytes)
    if not raw.startswith(_JPEG_MAGIC):
        raise ValueError("Corridor snapshot payload must start with JPEG magic bytes (0xFF 0xD8 0xFF)")
    if len(raw) > MAX_CORRIDOR_SNAPSHOT_BYTES:
        raise ValueError(
            f"Corridor snapshot exceeds {MAX_CORRIDOR_SNAPSHOT_BYTES} byte limit ({len(raw)} bytes)"
        )
    return raw


def encode_corridor_frame_jpeg(frame: Any, quality: int = 85) -> bytes:
    """Encode a raw frame or pre-encoded JPEG bytes and enforce snapshot security checks."""
    if isinstance(frame, (bytes, bytearray)):
        return validate_corridor_snapshot_bytes(bytes(frame))
    if frame is None or not hasattr(frame, "shape"):
        raise ValueError("Cannot encode empty or invalid corridor frame")
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError("cv2.imencode('.jpg') returned False for corridor snapshot")
    return validate_corridor_snapshot_bytes(bytes(buf.tobytes()))


def build_corridor_snapshot_key(
    project_id: str,
    swarm_id: str,
    survey_id: str,
    drone_id: str,
    snapshot_id: str,
) -> str:
    """Construct and validate the canonical UUID-keyed MinIO object path for corridor snapshots."""
    if not PROJECT_SLUG_RE.match(project_id):
        raise ValueError(f"Invalid project_id slug: {project_id!r}")
    if not _DRONE_ID_RE.match(drone_id):
        raise ValueError(f"Invalid drone_id: {drone_id!r}")
    canonical_swarm = str(uuid.UUID(str(swarm_id)))
    canonical_survey = str(uuid.UUID(str(survey_id)))
    canonical_snapshot = str(uuid.UUID(str(snapshot_id)))
    key = (
        f"projects/{project_id}/swarms/{canonical_swarm}/"
        f"corridor-surveys/{canonical_survey}/drones/{drone_id}/{canonical_snapshot}.jpg"
    )
    return validate_object_key(key)

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

    async def publish_corridor_snapshot(
        self,
        *,
        survey_id: str,
        sequence_num: int,
        phase: str,
        rel_x_m: float,
        rel_y_m: float,
        rel_z_m: float,
        heading_deg: float,
        cumulative_distance_m: float,
        visual_confidence: float,
        corridor_open: bool,
        analysis_latency_ms: float,
        estimated_width_m: float | None = None,
        estimated_height_m: float | None = None,
        structural_tags: list[str] | None = None,
        findings: list[dict[str, Any]] | None = None,
        snapshot_id: str | None = None,
        snapshot_bytes: bytes | None = None,
        frame: Any = None,
        lat: float = 0.0,
        lon: float = 0.0,
        alt_m: float = 0.0,
        speed_ms: float = 0.0,
        battery_pct: float = 100.0,
        mission_id: str | None = None,
        drone_id: str | None = None,
    ) -> SwarmTelemetryEvent:
        """Persist every corridor snapshot to MinIO/EdgeSpool and publish QoS 1 MQTT metadata (`FR-020`)."""
        effective_drone_id = drone_id or self.drone_id
        effective_snapshot_id = str(uuid.UUID(str(snapshot_id))) if snapshot_id else str(uuid.uuid4())
        canonical_survey_id = str(uuid.UUID(str(survey_id)))

        if snapshot_bytes is not None:
            raw_jpeg = validate_corridor_snapshot_bytes(snapshot_bytes)
        else:
            raw_jpeg = encode_corridor_frame_jpeg(frame)

        s3_key = build_corridor_snapshot_key(
            project_id=self.project_id,
            swarm_id=self.swarm_id,
            survey_id=canonical_survey_id,
            drone_id=effective_drone_id,
            snapshot_id=effective_snapshot_id,
        )

        snapshot_uri: str | None = None
        snapshot_local_path: str | None = None
        uploaded = False
        if self.minio_store is not None:
            try:
                await self.minio_store.put_object(
                    self.minio_store.SNAPSHOT_BUCKET,
                    s3_key,
                    raw_jpeg,
                    content_type="image/jpeg",
                )
                snapshot_uri = f"s3://{self.minio_store.SNAPSHOT_BUCKET}/{s3_key}"
                uploaded = True
            except Exception as exc:
                logger.warning("Corridor snapshot upload deferred to edge spool (%s)", exc)

        if not uploaded:
            snap_dir = (
                Path(self.spool.db_path).parent / "snapshots"
                if self.spool.db_path != ":memory:"
                else Path("/tmp/isc_edge_snapshots")
            )
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_file = snap_dir / f"{effective_snapshot_id}.jpg"
            snap_file.write_bytes(raw_jpeg)
            snapshot_local_path = str(snap_file)
            snapshot_uri = f"s3://tactical-snapshots/{s3_key}"

        payload = CorridorSnapshotPayload(
            survey_id=canonical_survey_id,
            snapshot_id=effective_snapshot_id,
            sequence_num=int(sequence_num),
            phase=phase,
            rel_x_m=float(rel_x_m),
            rel_y_m=float(rel_y_m),
            rel_z_m=float(rel_z_m),
            cumulative_distance_m=max(0.0, float(cumulative_distance_m)),
            visual_confidence=max(0.0, min(1.0, float(visual_confidence))),
            corridor_open=bool(corridor_open),
            estimated_width_m=float(estimated_width_m) if estimated_width_m is not None else None,
            estimated_height_m=float(estimated_height_m) if estimated_height_m is not None else None,
            analysis_latency_ms=max(0.0, float(analysis_latency_ms)),
            byte_size=len(raw_jpeg),
            structural_tags=list(structural_tags or []),
            findings=list(findings or []),
        )

        event = SwarmTelemetryEvent(
            project_id=self.project_id,
            swarm_id=self.swarm_id,
            drone_id=effective_drone_id,
            metric_type="alert",
            lat=float(lat),
            lon=float(lon),
            alt_m=float(alt_m),
            heading_deg=_normalize_heading_deg(heading_deg),
            speed_ms=max(0.0, float(speed_ms)),
            battery_pct=max(0.0, min(100.0, float(battery_pct))),
            flight_status=corridor_phase_to_flight_status(phase),
            snapshot_uri=snapshot_uri,
            mission_id=mission_id,
            extra=payload.model_dump(mode="json"),
        )
        await self.publish_event(event, snapshot_local_path=snapshot_local_path)
        return event

    async def publish_corridor_event(
        self,
        *,
        survey_event_type: str,
        payload: dict[str, Any],
        flight_status: str,
        lat: float = 0.0,
        lon: float = 0.0,
        alt_m: float = 0.0,
        heading_deg: float = 0.0,
        speed_ms: float = 0.0,
        battery_pct: float = 100.0,
        mission_id: str | None = None,
        drone_id: str | None = None,
    ) -> SwarmTelemetryEvent:
        """Emit a QoS 1 corridor telemetry/provenance event (`corridor_trajectory`, `corridor_phase`, `corridor_report`, `corridor_override`)."""
        if survey_event_type not in CORRIDOR_SURVEY_EVENT_TYPES:
            raise ValueError(f"Unsupported corridor event type: {survey_event_type!r}")
        effective_drone_id = drone_id or self.drone_id
        extra_payload = dict(payload)
        extra_payload.setdefault(
            "command_source",
            "operator_corridor_override"
            if survey_event_type == "corridor_override"
            else "edge_corridor_survey",
        )
        extra_payload.setdefault(
            "decision_authority",
            "commander" if survey_event_type == "corridor_override" else "edge",
        )
        extra_payload["survey_event_type"] = survey_event_type

        event = SwarmTelemetryEvent(
            project_id=self.project_id,
            swarm_id=self.swarm_id,
            drone_id=effective_drone_id,
            metric_type="alert",
            lat=float(lat),
            lon=float(lon),
            alt_m=float(alt_m),
            heading_deg=_normalize_heading_deg(heading_deg),
            speed_ms=max(0.0, float(speed_ms)),
            battery_pct=max(0.0, min(100.0, float(battery_pct))),
            flight_status=flight_status,
            mission_id=mission_id,
            extra=extra_payload,
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

                extra = payload_dict.get("extra") if isinstance(payload_dict.get("extra"), dict) else {}
                is_corridor_snap = extra.get("survey_event_type") == "corridor_snapshot"
                if rec.snapshot_local_path and self.minio_store is not None and (
                    is_corridor_snap or not payload_dict.get("snapshot_uri")
                ):
                    local_file = Path(rec.snapshot_local_path)
                    if local_file.is_file():
                        if is_corridor_snap:
                            s3_key = build_corridor_snapshot_key(
                                project_id=rec.project_id,
                                swarm_id=rec.swarm_id,
                                survey_id=str(extra["survey_id"]),
                                drone_id=rec.drone_id,
                                snapshot_id=str(extra["snapshot_id"]),
                            )
                        else:
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
