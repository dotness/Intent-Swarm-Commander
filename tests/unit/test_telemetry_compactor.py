"""Hermetic unit tests for 5-15s Parquet micro-batch compaction and MinIO outage retention."""

import uuid
from datetime import datetime, timezone

import pytest

from src.uservice.analytics.operations.minio_store import MinioUnavailableError
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.telemetry.models.storage.live_state import LiveTelemetryStore
from src.uservice.telemetry.operations.compactor import ParquetCompactor, read_parquet_bytes


def _sample_event(project_id: str, swarm_id: str, event_id: uuid.UUID | None = None, **kw) -> SwarmTelemetryEvent:
    return SwarmTelemetryEvent(
        event_id=event_id or uuid.uuid4(),
        timestamp=datetime(2026, 11, 14, 20, 15, 0, tzinfo=timezone.utc),
        project_id=project_id,
        swarm_id=swarm_id,
        drone_id="drone-1",
        metric_type=kw.get("metric_type", "navigation"),
        lat=kw.get("lat", 52.521),
        lon=kw.get("lon", 13.405),
        alt_m=kw.get("alt_m", 120.0),
        battery_pct=kw.get("battery_pct", 88.0),
        target_class=kw.get("target_class"),
        confidence=kw.get("confidence"),
        snapshot_uri=kw.get("snapshot_uri"),
        replayed=kw.get("replayed", False),
    )


def test_compactor_interval_bounds():
    with pytest.raises(ValueError):
        ParquetCompactor(minio_store=None, flush_interval_s=2.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ParquetCompactor(minio_store=None, flush_interval_s=30.0)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_live_state_dedup_and_partitioned_parquet_flush(local_minio_store):
    await local_minio_store.ensure_buckets()
    live_store = LiveTelemetryStore(dedup_capacity=1000)
    compactor = ParquetCompactor(minio_store=local_minio_store, flush_interval_s=10.0, max_batch_size=100)

    swarm_a = str(uuid.uuid4())
    swarm_b = str(uuid.uuid4())
    dup_id = uuid.uuid4()

    ev1 = _sample_event("default-theater", swarm_a, event_id=dup_id, battery_pct=91.0)
    ev1_dup = _sample_event("default-theater", swarm_a, event_id=dup_id, battery_pct=91.0)
    ev2 = _sample_event(
        "alpha-theater",
        swarm_b,
        metric_type="detection",
        target_class="armored_vehicle",
        confidence=0.94,
    )

    for ev in (ev1, ev1_dup, ev2):
        if live_store.record_event(ev):
            compactor.enqueue(ev)

    assert live_store.total_events_ingested() == 2
    assert live_store.pending_count() == 2
    assert compactor.pending_count() == 2

    keys = await compactor.flush()
    assert len(keys) == 2
    assert compactor.pending_count() == 0

    default_keys = [k for k in keys if k.startswith(f"projects/default-theater/dt=2026-11-14/swarm={swarm_a}/")]
    alpha_keys = [k for k in keys if k.startswith(f"projects/alpha-theater/dt=2026-11-14/swarm={swarm_b}/")]
    assert len(default_keys) == 1
    assert len(alpha_keys) == 1

    raw_default = await local_minio_store.get_object(local_minio_store.PARQUET_BUCKET, default_keys[0])
    assert raw_default[:4] == b"PAR1"
    assert raw_default[-4:] == b"PAR1"
    assert not raw_default.startswith(b"PAR1ISCC")
    rows_default = read_parquet_bytes(raw_default)
    assert len(rows_default) == 1
    assert rows_default[0]["event_id"] == str(dup_id)
    assert rows_default[0]["project_id"] == "default-theater"
    assert rows_default[0]["battery_pct"] == pytest.approx(91.0)

    raw_alpha = await local_minio_store.get_object(local_minio_store.PARQUET_BUCKET, alpha_keys[0])
    assert raw_alpha[:4] == b"PAR1"
    assert raw_alpha[-4:] == b"PAR1"
    assert not raw_alpha.startswith(b"PAR1ISCC")
    rows_alpha = read_parquet_bytes(raw_alpha)
    assert len(rows_alpha) == 1
    assert rows_alpha[0]["target_class"] == "armored_vehicle"


@pytest.mark.asyncio
async def test_compactor_retains_buffer_on_minio_outage(local_s3_client, local_minio_store):
    compactor = ParquetCompactor(minio_store=local_minio_store, flush_interval_s=10.0, max_batch_size=10)
    ev = _sample_event("default-theater", str(uuid.uuid4()))
    compactor.enqueue(ev)

    local_s3_client.unavailable = True
    with pytest.raises(MinioUnavailableError):
        await compactor.flush()

    # Events must be retained cleanly until MinIO recovers
    assert compactor.pending_count() == 1

    local_s3_client.unavailable = False
    await local_minio_store.ensure_buckets()
    keys = await compactor.flush()
    assert len(keys) == 1
    assert compactor.pending_count() == 0
