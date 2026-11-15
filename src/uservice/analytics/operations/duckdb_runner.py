"""Sub-2s Analytical AAR query engine over Hive-partitioned Parquet objects in MinIO."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import tempfile
import time
from typing import Any

import duckdb

from src.uservice.analytics.models.contract.aar import AarQueryType
from src.uservice.analytics.operations.minio_store import MinioStore

logger = logging.getLogger(__name__)


def _to_iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class DuckdbAarRunner:
    """Executes sub-2s analytical SQL queries over MinIO telemetry Parquet partitions."""

    def __init__(self, minio_store: MinioStore | None = None) -> None:
        self.minio_store = minio_store or MinioStore()

    async def execute_aar(
        self,
        *,
        project_id: str = "default-theater",
        query_type: AarQueryType = "summary",
        swarm_id: str | None = None,
        drone_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 2000,
    ) -> dict[str, Any]:
        """Run an isolated OLAP query against Parquet partitions for project_id."""
        started = time.perf_counter()

        prefix = f"projects/{project_id}/"
        keys = await self.minio_store.list_objects(MinioStore.PARQUET_BUCKET, prefix=prefix)
        parquet_keys = [k for k in keys if k.endswith(".parquet")]
        if swarm_id:
            swarm_segment = f"/swarm={swarm_id}/"
            parquet_keys = [k for k in parquet_keys if swarm_segment in k]

        if not parquet_keys:
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            empty_rows = (
                [
                    {
                        "total_events": 0,
                        "unique_swarms": 0,
                        "unique_drones": 0,
                        "detection_count": 0,
                        "replayed_count": 0,
                        "min_battery_pct": None,
                        "avg_alt_m": None,
                        "first_event_ts": None,
                        "last_event_ts": None,
                    }
                ]
                if query_type == "summary"
                else []
            )
            return {
                "project_id": project_id,
                "query_type": query_type,
                "execution_ms": elapsed_ms,
                "row_count": len(empty_rows),
                "rows": empty_rows,
                "engine": "duckdb",
            }

        raw_blobs: list[bytes] = [
            await self.minio_store.get_object(MinioStore.PARQUET_BUCKET, key)
            for key in parquet_keys
        ]
        rows, engine = self._query_native_duckdb(
            raw_blobs=raw_blobs,
            project_id=project_id,
            query_type=query_type,
            swarm_id=swarm_id,
            drone_id=drone_id,
            from_iso=_to_iso_utc(from_ts),
            to_iso=_to_iso_utc(to_ts),
            limit=limit,
        )

        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return {
            "project_id": project_id,
            "query_type": query_type,
            "execution_ms": elapsed_ms,
            "row_count": len(rows),
            "rows": rows,
            "engine": engine,
        }

    @staticmethod
    def _build_where_and_params(
        *,
        project_id: str,
        swarm_id: str | None,
        drone_id: str | None,
        from_iso: str | None,
        to_iso: str | None,
        extra_clauses: list[str] | None = None,
    ) -> tuple[str, list[Any]]:
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if swarm_id:
            clauses.append("swarm_id = ?")
            params.append(swarm_id)
        if drone_id:
            clauses.append("drone_id = ?")
            params.append(drone_id)
        if from_iso:
            clauses.append("timestamp >= ?")
            params.append(from_iso)
        if to_iso:
            clauses.append("timestamp <= ?")
            params.append(to_iso)
        if extra_clauses:
            clauses.extend(extra_clauses)
        return " AND ".join(clauses), params

    def _query_native_duckdb(
        self,
        *,
        raw_blobs: list[bytes],
        project_id: str,
        query_type: AarQueryType,
        swarm_id: str | None,
        drone_id: str | None,
        from_iso: str | None,
        to_iso: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str]:
        with tempfile.TemporaryDirectory(prefix="isc_duckdb_") as tmpdir:
            file_paths: list[str] = []
            for idx, blob in enumerate(raw_blobs):
                fp = Path(tmpdir) / f"part_{idx}.parquet"
                fp.write_bytes(blob)
                file_paths.append(str(fp))

            con = duckdb.connect(":memory:")
            try:
                con.execute("CREATE TEMP TABLE telemetry AS SELECT * FROM read_parquet(?)", [file_paths])
                extra = ["metric_type = 'detection'"] if query_type == "detections" else None
                where_sql, params = self._build_where_and_params(
                    project_id=project_id,
                    swarm_id=swarm_id,
                    drone_id=drone_id,
                    from_iso=from_iso,
                    to_iso=to_iso,
                    extra_clauses=extra,
                )
                sql, final_params = self._select_sql(query_type, where_sql, params, limit)
                cur = con.execute(sql, final_params)
                cols = [d[0] for d in cur.description]
                out = [dict(zip(cols, row)) for row in cur.fetchall()]
                return out, "duckdb"
            finally:
                con.close()

    @staticmethod
    def _select_sql(
        query_type: AarQueryType,
        where_sql: str,
        params: list[Any],
        limit: int,
    ) -> tuple[str, list[Any]]:
        if query_type == "summary":
            sql = f"""
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT swarm_id) AS unique_swarms,
                    COUNT(DISTINCT drone_id) AS unique_drones,
                    SUM(CASE WHEN metric_type = 'detection' THEN 1 ELSE 0 END) AS detection_count,
                    SUM(CASE WHEN CAST(replayed AS INTEGER) = 1 THEN 1 ELSE 0 END) AS replayed_count,
                    MIN(battery_pct) AS min_battery_pct,
                    AVG(alt_m) AS avg_alt_m,
                    MIN(timestamp) AS first_event_ts,
                    MAX(timestamp) AS last_event_ts
                FROM telemetry
                WHERE {where_sql}
            """
            return sql, list(params)

        if query_type == "trajectory":
            sql = f"""
                SELECT event_id, timestamp, swarm_id, drone_id, metric_type,
                       lat, lon, alt_m, heading_deg, speed_ms, replayed
                FROM telemetry
                WHERE {where_sql}
                ORDER BY timestamp ASC
                LIMIT ?
            """
            return sql, [*params, int(limit)]

        if query_type == "battery_decay":
            sql = f"""
                SELECT timestamp, swarm_id, drone_id, battery_pct, alt_m, speed_ms
                FROM telemetry
                WHERE {where_sql}
                ORDER BY timestamp ASC
                LIMIT ?
            """
            return sql, [*params, int(limit)]

        # query_type == "detections"
        sql = f"""
            SELECT event_id, timestamp, swarm_id, drone_id, target_class,
                   confidence, lat, lon, alt_m, snapshot_uri, mission_id, replayed
            FROM telemetry
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        return sql, [*params, int(limit)]
