"""Hermetic unit tests for SQLite WAL DDIL EdgeSpool and EdgeTelemetryPublisher."""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.edge.telemetry.publisher import EdgeTelemetryPublisher
from src.edge.telemetry.spool import EdgeSpool
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent, build_telemetry_topic


def _make_event(
    swarm_id: str,
    metric_type: str = "navigation",
    ts: datetime | None = None,
    battery_pct: float = 80.0,
    target_class: str | None = None,
    lat: float = 52.52,
) -> SwarmTelemetryEvent:
    return SwarmTelemetryEvent(
        event_id=uuid.uuid4(),
        timestamp=ts or datetime.now(timezone.utc),
        project_id="default-theater",
        swarm_id=swarm_id,
        drone_id="drone-1",
        metric_type=metric_type,
        lat=lat,
        lon=13.40,
        alt_m=100.0,
        battery_pct=battery_pct,
        target_class=target_class,
        confidence=0.92 if metric_type == "detection" else None,
    )


def test_edge_spool_wal_and_priority_eviction(tmp_path: Path):
    db_path = tmp_path / "edge_spool.db"
    spool = EdgeSpool(db_path=str(db_path), max_records=5)

    # Verify WAL journal mode is active
    with sqlite3.connect(db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert str(mode).lower() == "wal"

    sid = str(uuid.uuid4())
    base = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)

    # Enqueue 3 routine navigation events (priority=0)
    for i in range(3):
        ev = _make_event(sid, "navigation", ts=base + timedelta(seconds=i))
        spool.enqueue(
            ev,
            priority=0,
            qos=0,
            topic=build_telemetry_topic("default-theater", sid, "drone-1", "navigation"),
        )

    # Enqueue 3 critical detection events (priority=1) -> capacity=5 -> must evict oldest priority=0 row
    det_ids = []
    for i in range(3, 6):
        ev = _make_event(sid, "detection", ts=base + timedelta(seconds=i), target_class="truck")
        det_ids.append(str(ev.event_id))
        spool.enqueue(
            ev,
            priority=1,
            qos=1,
            topic=build_telemetry_topic("default-theater", sid, "drone-1", "detection"),
        )

    status = spool.get_status()
    assert status.queued_rows == 5
    assert status.evicted_routine_count >= 1
    assert status.evicted_critical_count == 0

    rows = spool.peek_unsynced(limit=10)
    remaining_ids = [r.event_id for r in rows]
    # All 3 priority=1 detections must still be preserved
    for did in det_ids:
        assert did in remaining_ids

    # Priority-first drain order (priority=1 rows first, FIFO within priority)
    assert [r.priority for r in rows[:3]] == [1, 1, 1]
    assert [r.event_id for r in rows[:3]] == det_ids


def test_edge_spool_critical_overflow_only_when_no_routine_rows(tmp_path: Path):
    spool = EdgeSpool(db_path=str(tmp_path / "crit.db"), max_records=2)
    sid = str(uuid.uuid4())
    base = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)

    ids = []
    for i in range(3):
        ev = _make_event(sid, "detection", ts=base + timedelta(seconds=i), target_class="radar")
        ids.append(str(ev.event_id))
        spool.enqueue(
            ev,
            priority=1,
            qos=1,
            topic=build_telemetry_topic("default-theater", sid, "drone-1", "detection"),
        )

    status = spool.get_status()
    assert status.queued_rows == 2
    assert status.evicted_critical_count == 1
    rows = spool.peek_unsynced(limit=10)
    assert [r.event_id for r in rows] == ids[1:]


@pytest.mark.asyncio
async def test_live_first_reconnect_and_async_backlog_drain(tmp_path: Path, in_memory_mqtt_bus):
    spool = EdgeSpool(db_path=str(tmp_path / "publisher_spool.db"), max_records=100)
    sid = str(uuid.uuid4())
    pub = EdgeTelemetryPublisher(
        project_id="default-theater",
        swarm_id=sid,
        drone_id="drone-1",
        spool=spool,
        transport=in_memory_mqtt_bus,
    )

    # Disconnect broker to trigger DDIL spooling
    in_memory_mqtt_bus.disconnect()
    base = datetime(2026, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
    nav_offline = _make_event(sid, "navigation", ts=base, lat=52.5001)
    det_offline = _make_event(sid, "detection", ts=base + timedelta(seconds=1), target_class="tank", lat=52.5002)

    await pub.publish_event(nav_offline)
    await pub.publish_event(det_offline)
    assert len(in_memory_mqtt_bus.messages) == 0
    assert spool.get_status().queued_rows == 2

    # Reconnect: live frame MUST transmit first with replayed=False BEFORE backlog drains
    in_memory_mqtt_bus.reconnect()
    live_evt = _make_event(sid, "navigation", ts=base + timedelta(seconds=5), lat=52.5009)
    await pub.publish_event(live_evt)

    assert len(in_memory_mqtt_bus.messages) == 1
    first_payload = json.loads(in_memory_mqtt_bus.messages[0].payload.decode("utf-8"))
    assert first_payload["event_id"] == str(live_evt.event_id)
    assert first_payload["replayed"] is False

    # Now drain backlog asynchronously -> spooled detection (priority=1) then nav (priority=0), replayed=True
    drained = await pub.drain_backlog()
    assert drained == 2
    assert spool.get_status().queued_rows == 0
    assert len(in_memory_mqtt_bus.messages) == 3

    replayed_1 = json.loads(in_memory_mqtt_bus.messages[1].payload.decode("utf-8"))
    replayed_2 = json.loads(in_memory_mqtt_bus.messages[2].payload.decode("utf-8"))
    assert replayed_1["event_id"] == str(det_offline.event_id)
    assert replayed_1["replayed"] is True
    assert replayed_2["event_id"] == str(nav_offline.event_id)
    assert replayed_2["replayed"] is True


@pytest.mark.asyncio
async def test_flight_controller_publishes_detection_with_crop_and_mission_id(
    tmp_path: Path,
    in_memory_mqtt_bus,
    local_minio_store,
):
    from src.edge.navigation.flight_controller import FlightController
    from src.edge.vision.inference import Detection

    await local_minio_store.ensure_buckets()
    jpeg_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    class _CameraDouble:
        width = 640

        def read_frame(self):
            return jpeg_frame

    class _InferenceDouble:
        def detect(self, frame, target_class=None):
            return [
                Detection(
                    class_name="truck",
                    confidence=0.94,
                    bbox=(10, 12, 90, 96),
                    center=(50, 54),
                )
            ]

    sid = str(uuid.uuid4())
    spool = EdgeSpool(db_path=str(tmp_path / "fc_spool.db"), max_records=20)
    pub = EdgeTelemetryPublisher(
        project_id="default-theater",
        swarm_id=sid,
        drone_id="drone-1",
        spool=spool,
        transport=in_memory_mqtt_bus,
        minio_store=local_minio_store,
    )
    fc = FlightController(
        camera=_CameraDouble(),
        inference=_InferenceDouble(),
        target_class="truck",
        telemetry_publisher=pub,
        mission_id="cmd-mission-42",
        obstacle_avoidance_enabled=False,
    )
    fc._running = True
    fc.last_lat = 52.5300
    fc.last_lon = 13.4100
    fc.last_alt_m = 75.0
    fc.state.approach_distance_m = 3.0  # exit after 1 detection iteration

    await fc._navigation_loop()

    assert len(in_memory_mqtt_bus.messages) == 1
    msg = in_memory_mqtt_bus.messages[0]
    assert msg.qos == 1
    payload = json.loads(msg.payload.decode("utf-8"))
    assert payload["metric_type"] == "detection"
    assert payload["target_class"] == "truck"
    assert payload["confidence"] == pytest.approx(0.94)
    assert payload["bbox"] == [10, 12, 90, 96]
    assert payload["mission_id"] == "cmd-mission-42"
    assert payload["flight_status"] == "approaching"
    assert payload["snapshot_uri"] is not None
    assert payload["snapshot_uri"].startswith(f"s3://{local_minio_store.SNAPSHOT_BUCKET}/")

    s3_key = payload["snapshot_uri"].split(f"s3://{local_minio_store.SNAPSHOT_BUCKET}/", 1)[1]
    stored_bytes = await local_minio_store.get_object(local_minio_store.SNAPSHOT_BUCKET, s3_key)
    assert stored_bytes == jpeg_frame


@pytest.mark.asyncio
async def test_edge_telemetry_loop_publishes_navigation_and_battery_events(
    tmp_path: Path,
    in_memory_mqtt_bus,
    monkeypatch: pytest.MonkeyPatch,
):
    from types import SimpleNamespace
    from src.edge.api import server as edge_server

    async def _aiter(items):
        for item in items:
            yield item

    class _TelemetryDouble:
        def position(self):
            return _aiter([SimpleNamespace(latitude_deg=52.52, longitude_deg=13.40, absolute_altitude_m=65.0)])

        def battery(self):
            return _aiter([SimpleNamespace(remaining_percent=0.15)])

        def heading(self):
            return _aiter([SimpleNamespace(heading_deg=270.0)])

    drone_double = SimpleNamespace(telemetry=_TelemetryDouble())
    sid = str(uuid.uuid4())
    spool = EdgeSpool(db_path=str(tmp_path / "loop_spool.db"), max_records=20)
    pub = EdgeTelemetryPublisher(
        project_id="default-theater",
        swarm_id=sid,
        drone_id="drone-1",
        spool=spool,
        transport=in_memory_mqtt_bus,
    )

    monkeypatch.setattr(edge_server, "_drone", drone_double)
    monkeypatch.setattr(edge_server, "_telemetry_publisher", pub)

    await edge_server.telemetry_loop()

    assert len(in_memory_mqtt_bus.messages) == 2
    by_metric = {}
    for msg in in_memory_mqtt_bus.messages:
        body = json.loads(msg.payload.decode("utf-8"))
        by_metric[body["metric_type"]] = (msg.qos, body)

    assert "navigation" in by_metric
    assert by_metric["navigation"][0] == 0
    assert by_metric["navigation"][1]["lat"] == pytest.approx(52.52)

    assert "battery" in by_metric
    assert by_metric["battery"][0] == 1  # <20% battery promotes to QoS 1
    assert by_metric["battery"][1]["battery_pct"] == pytest.approx(15.0)


