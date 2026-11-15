"""5-15s Parquet micro-batch compactor flushing telemetry to MinIO tactical-telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import io
import json
import logging
import os
import time
import uuid
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent

logger = logging.getLogger(__name__)


def _event_to_row(event: SwarmTelemetryEvent) -> dict[str, Any]:
    ts = event.timestamp.astimezone(timezone.utc)
    return {
        "event_id": str(event.event_id),
        "timestamp": ts.isoformat(),
        "timestamp_us": int(ts.timestamp() * 1_000_000),
        "project_id": event.project_id,
        "swarm_id": str(event.swarm_id),
        "drone_id": event.drone_id,
        "metric_type": event.metric_type,
        "lat": float(event.lat),
        "lon": float(event.lon),
        "alt_m": float(event.alt_m),
        "heading_deg": float(event.heading_deg),
        "speed_ms": float(event.speed_ms),
        "battery_pct": float(event.battery_pct),
        "flight_status": event.flight_status,
        "target_class": event.target_class,
        "confidence": float(event.confidence) if event.confidence is not None else None,
        "snapshot_uri": event.snapshot_uri,
        "mission_id": event.mission_id,
        "replayed": bool(event.replayed),
        "extra_json": json.dumps(event.extra) if event.extra is not None else None,
    }


def write_parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Serialize normalized telemetry rows into Apache Parquet bytes with snappy compression."""
    schema = pa.schema(
        [
            ("event_id", pa.string()),
            ("timestamp", pa.timestamp("us", tz="UTC")),
            ("project_id", pa.string()),
            ("swarm_id", pa.string()),
            ("drone_id", pa.string()),
            ("metric_type", pa.string()),
            ("lat", pa.float64()),
            ("lon", pa.float64()),
            ("alt_m", pa.float64()),
            ("heading_deg", pa.float32()),
            ("speed_ms", pa.float32()),
            ("battery_pct", pa.float32()),
            ("flight_status", pa.string()),
            ("target_class", pa.string()),
            ("confidence", pa.float32()),
            ("snapshot_uri", pa.string()),
            ("mission_id", pa.string()),
            ("replayed", pa.bool_()),
            ("extra_json", pa.string()),
        ]
    )
    parsed_rows = []
    for r in rows:
        ts_val = r["timestamp"]
        if isinstance(ts_val, str):
            ts_dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        else:
            ts_dt = ts_val
        parsed_rows.append(
            {
                **r,
                "timestamp": ts_dt,
            }
        )
    cols = {field.name: [row.get(field.name) for row in parsed_rows] for field in schema}
    table = pa.table(cols, schema=schema)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()


def read_parquet_bytes(data: bytes) -> list[dict[str, Any]]:
    """Deserialize native Apache Parquet bytes."""
    table = pq.read_table(io.BytesIO(data))
    rows = table.to_pylist()
    for r in rows:
        if isinstance(r.get("timestamp"), datetime):
            ts = r["timestamp"].astimezone(timezone.utc)
            r["timestamp_us"] = int(ts.timestamp() * 1_000_000)
            r["timestamp"] = ts.isoformat()
    return rows


class ParquetCompactor:
    """Micro-batch compactor flushing buffered telemetry events every 5-15s to MinIO."""

    def __init__(
        self,
        minio_store: MinioStore | Any,
        flush_interval_s: float | None = None,
        max_batch_size: int | None = None,
    ) -> None:
        interval = float(
            flush_interval_s if flush_interval_s is not None else os.getenv("PARQUET_FLUSH_INTERVAL_S", "10")
        )
        if interval < 5.0 or interval > 15.0:
            raise ValueError(f"PARQUET_FLUSH_INTERVAL_S must be within [5, 15] seconds, got {interval}")
        self.minio_store = minio_store
        self.flush_interval_s = interval
        self.max_batch_size = int(
            max_batch_size if max_batch_size is not None else os.getenv("PARQUET_BATCH_SIZE", "500")
        )
        self._buffer: list[SwarmTelemetryEvent] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def enqueue(self, event: SwarmTelemetryEvent) -> None:
        """Append a validated telemetry event to the in-memory compaction buffer."""
        self._buffer.append(event)

    def pending_count(self) -> int:
        return len(self._buffer)

    async def flush(self) -> list[str]:
        """Compact buffered events into Hive-partitioned Parquet objects in MinIO.

        Retains buffered partitions cleanly if MinIO upload fails.
        """
        async with self._lock:
            if not self._buffer:
                return []

            batch = list(self._buffer)
            grouped: dict[tuple[str, str, str], list[SwarmTelemetryEvent]] = defaultdict(list)
            for ev in batch:
                dt_str = ev.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
                grouped[(ev.project_id, dt_str, str(ev.swarm_id))].append(ev)

            uploaded_keys: list[str] = []
            uploaded_events: set[int] = set()
            epoch_ms = int(time.time() * 1000)

            try:
                for (project_id, dt_str, swarm_id), events in grouped.items():
                    rows = [_event_to_row(e) for e in events]
                    parquet_bytes = write_parquet_bytes(rows)
                    key = (
                        f"projects/{project_id}/dt={dt_str}/swarm={swarm_id}/"
                        f"{epoch_ms}_{uuid.uuid4().hex[:8]}.parquet"
                    )
                    await self.minio_store.put_object(
                        MinioStore.PARQUET_BUCKET,
                        key,
                        parquet_bytes,
                        content_type="application/vnd.apache.parquet",
                    )
                    uploaded_keys.append(key)
                    for ev in events:
                        uploaded_events.add(id(ev))
            finally:
                # Only remove successfully persisted events so outages never drop buffered rows
                if uploaded_events:
                    self._buffer = [ev for ev in self._buffer if id(ev) not in uploaded_events]

            return uploaded_keys

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_s)
                if self._buffer:
                    await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Parquet compaction cycle deferred (%s); buffer retained (%d rows)", exc, len(self._buffer))

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
