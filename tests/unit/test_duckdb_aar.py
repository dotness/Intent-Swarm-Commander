"""Hermetic unit tests for DuckdbAarRunner sub-2s OLAP queries and theater isolation."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest

from src.uservice.analytics.operations.duckdb_runner import DuckdbAarRunner
from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.telemetry.operations.compactor import ParquetCompactor


def _make_event(
    *,
    project_id: str,
    swarm_id: str,
    drone_id: str,
    metric_type: str,
    ts: datetime,
    battery_pct: float,
    lat: float,
    lon: float,
    target_class: str | None = None,
    confidence: float | None = None,
    replayed: bool = False,
) -> SwarmTelemetryEvent:
    return SwarmTelemetryEvent(
        event_id=uuid.uuid4(),
        timestamp=ts,
        project_id=project_id,
        swarm_id=swarm_id,
        drone_id=drone_id,
        metric_type=metric_type,  # type: ignore[arg-type]
        lat=lat,
        lon=lon,
        alt_m=75.0,
        heading_deg=90.0,
        speed_ms=14.0,
        battery_pct=battery_pct,
        target_class=target_class,
        confidence=confidence,
        replayed=replayed,
        snapshot_uri=f"s3://tactical-snapshots/projects/{project_id}/snap.jpg"
        if metric_type == "detection"
        else None,
    )


@pytest.mark.asyncio
async def test_aar_runner_queries_four_views_under_2s_and_isolates_theater(
    local_minio_store: MinioStore,
):
    await local_minio_store.ensure_buckets()
    compactor = ParquetCompactor(minio_store=local_minio_store, flush_interval_s=5.0)
    t0 = datetime(2026, 11, 15, 8, 0, 0, tzinfo=timezone.utc)

    # Flush 1,000 events across default-theater and 25 events in bravo-theater
    for idx in range(1000):
        drone = f"drone-{(idx % 4) + 1}"
        bat = max(10.0, 99.0 - (idx * 0.08))
        is_det = idx % 100 == 0
        compactor.enqueue(
            _make_event(
                project_id="default-theater",
                swarm_id="swarm-alpha",
                drone_id=drone,
                metric_type="detection" if is_det else "navigation",
                ts=t0 + timedelta(seconds=idx),
                battery_pct=bat,
                lat=52.5200 + (idx * 0.00001),
                lon=13.4050 + (idx * 0.00001),
                target_class="supply_truck" if is_det else None,
                confidence=0.91 if is_det else None,
                replayed=(idx % 50 == 0),
            )
        )

    for idx in range(25):
        compactor.enqueue(
            _make_event(
                project_id="bravo-theater",
                swarm_id="swarm-bravo",
                drone_id="drone-9",
                metric_type="detection",
                ts=t0 + timedelta(seconds=idx),
                battery_pct=88.0,
                lat=48.8566,
                lon=2.3522,
                target_class="sam_launcher",
                confidence=0.95,
            )
        )

    await compactor.flush()
    runner = DuckdbAarRunner(minio_store=local_minio_store)

    # 1. summary view < 2000ms and isolated to default-theater (1,000 not 1,025)
    summary = await runner.execute_aar(project_id="default-theater", query_type="summary")
    assert summary["engine"] == "duckdb"
    assert summary["execution_ms"] < 2000.0
    assert summary["rows"][0]["total_events"] == 1000
    assert summary["rows"][0]["unique_drones"] == 4
    assert summary["rows"][0]["detection_count"] == 10
    assert summary["rows"][0]["replayed_count"] == 20

    # 2. trajectory ordered chronologically
    traj = await runner.execute_aar(project_id="default-theater", query_type="trajectory", drone_id="drone-1")
    assert traj["engine"] == "duckdb"
    assert traj["execution_ms"] < 2000.0
    assert traj["row_count"] == 250
    assert traj["rows"][0]["timestamp"] <= traj["rows"][-1]["timestamp"]

    # 3. battery_decay curve
    bat = await runner.execute_aar(project_id="default-theater", query_type="battery_decay")
    assert bat["engine"] == "duckdb"
    assert bat["execution_ms"] < 2000.0
    assert bat["row_count"] == 1000
    assert bat["rows"][0]["battery_pct"] >= bat["rows"][-1]["battery_pct"]

    # 4. detections strictly scoped by project_id
    dets = await runner.execute_aar(project_id="default-theater", query_type="detections")
    assert dets["engine"] == "duckdb"
    assert dets["execution_ms"] < 2000.0
    assert dets["row_count"] == 10
    assert all(r["target_class"] == "supply_truck" for r in dets["rows"])

    bravo_dets = await runner.execute_aar(project_id="bravo-theater", query_type="detections")
    assert bravo_dets["engine"] == "duckdb"
    assert bravo_dets["row_count"] == 25
    assert all(r["target_class"] == "sam_launcher" for r in bravo_dets["rows"])
