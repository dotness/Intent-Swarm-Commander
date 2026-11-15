"""Standalone PMA C4ISR stack verification & sub-2s AAR benchmark script."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.edge.telemetry.publisher import EdgeTelemetryPublisher
from src.edge.telemetry.spool import EdgeSpool
from src.uservice.analytics.operations.duckdb_runner import DuckdbAarRunner
from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.telemetry.operations.compactor import ParquetCompactor
from src.uservice.threat.operations.graph_client import MemgraphClient


async def run_benchmark(project_id: str, row_count: int, check_live_infra: bool) -> int:
    print(f"[PMA Verify] Project={project_id} | BenchmarkRows={row_count} | LiveInfra={check_live_infra}")

    with tempfile.TemporaryDirectory(prefix="isc_pma_verify_") as tmpdir:
        tmp_root = Path(tmpdir)
        spool = EdgeSpool(db_path=str(tmp_root / "verify_spool.db"))
        ev = SwarmTelemetryEvent(
            project_id=project_id,
            swarm_id="verify-swarm",
            drone_id="drone-1",
            metric_type="alert",
            lat=52.52,
            lon=13.405,
            alt_m=50.0,
            battery_pct=88.0,
        )
        spool.enqueue(ev, priority=100, qos=1, topic=f"telemetry/projects/{project_id}/swarms/verify-swarm/drone-1/alert")
        status = spool.get_status("verify-swarm")
        assert status.queued_rows == 1, "EdgeSpool failed to enqueue alert event"
        print(f"  [OK] EdgeSpool WAL persistence verified ({status.queued_rows} queued)")

        if check_live_infra:
            minio = MinioStore()
            await minio.ensure_buckets()
            memgraph = MemgraphClient()
            ok = await memgraph.ping()
            await memgraph.close()
            if not ok:
                raise RuntimeError("Memgraph ping failed")
            print("  [OK] Live MinIO & Memgraph connectivity verified")
            target_minio = minio
        else:
            from tests.conftest import LocalFilesystemS3Client

            target_minio = MinioStore(s3_client=LocalFilesystemS3Client(tmp_root / "s3"))
            await target_minio.ensure_buckets()

        compactor = ParquetCompactor(minio_store=target_minio, flush_interval_s=5.0)
        t0 = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
        for idx in range(row_count):
            is_det = idx % 200 == 0
            compactor.enqueue(
                SwarmTelemetryEvent(
                    event_id=uuid.uuid4(),
                    timestamp=t0 + timedelta(seconds=idx),
                    project_id=project_id,
                    swarm_id="verify-swarm",
                    drone_id=f"drone-{(idx % 5) + 1}",
                    metric_type="detection" if is_det else "navigation",
                    lat=52.52 + idx * 1e-5,
                    lon=13.405 + idx * 1e-5,
                    alt_m=60.0,
                    battery_pct=max(15.0, 99.0 - idx * 0.005),
                    target_class="truck" if is_det else None,
                    confidence=0.9 if is_det else None,
                )
            )
        keys = await compactor.flush()
        print(f"  [OK] ParquetCompactor flushed {row_count} events into {len(keys)} partition(s)")

        runner = DuckdbAarRunner(minio_store=target_minio)
        summary = await runner.execute_aar(project_id=project_id, query_type="summary")
        exec_ms = summary["execution_ms"]
        print(f"  [OK] AAR ({summary['engine']}) summary on {row_count} rows completed in {exec_ms:.2f} ms")
        if exec_ms >= 2000.0:
            raise RuntimeError(f"AAR exceeded 2000ms SLA: {exec_ms:.2f} ms")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PMA C4ISR stack components & AAR latency SLA.")
    parser.add_argument("--project-id", default="default-theater")
    parser.add_argument("--rows", type=int, default=10000, help="Benchmark telemetry event count")
    parser.add_argument("--live", action="store_true", help="Also verify live MinIO & Memgraph services")
    args = parser.parse_args()
    return asyncio.run(run_benchmark(args.project_id, args.rows, args.live))


if __name__ == "__main__":
    raise SystemExit(main())
