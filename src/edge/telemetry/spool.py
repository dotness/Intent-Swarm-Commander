"""SQLite WAL DDIL write-ahead spool with priority-aware eviction."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.uservice.telemetry.models.contract.events import (
    SpoolStatusResponse,
    SwarmTelemetryEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class SpoolRecord:
    """Single row stored in the edge SQLite DDIL spool."""

    row_id: int
    event_id: str
    project_id: str
    swarm_id: str
    drone_id: str
    metric_type: str
    priority: int
    qos: int
    topic: str
    payload_json: str
    snapshot_local_path: str | None
    created_at_utc: str
    attempts: int


class EdgeSpool:
    """Embedded SQLite WAL spool protecting telemetry during DDIL disconnects."""

    def __init__(
        self,
        db_path: str | None = None,
        max_records: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self.db_path = db_path or os.getenv("EDGE_SPOOL_DB_PATH", "/tmp/isc_edge_spool.db")
        self.max_records = max_records
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_spool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    project_id TEXT NOT NULL,
                    swarm_id TEXT NOT NULL,
                    drone_id TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    qos INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    snapshot_local_path TEXT NULL,
                    created_at_utc TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    synced_at_utc TEXT NULL
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edge_spool_drain ON edge_spool(synced_at_utc, priority DESC, created_at_utc ASC);"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edge_spool_evict ON edge_spool(priority ASC, created_at_utc ASC);"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_spool_stats (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    evicted_routine_count INTEGER NOT NULL DEFAULT 0,
                    evicted_critical_count INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO edge_spool_stats (id, evicted_routine_count, evicted_critical_count) VALUES (1, 0, 0);"
            )
            self._conn.commit()

    def _needs_eviction_locked(self) -> bool:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM edge_spool WHERE synced_at_utc IS NULL;"
        ).fetchone()[0]
        if count >= self.max_records:
            return True
        if self.db_path != ":memory:" and Path(self.db_path).exists():
            if Path(self.db_path).stat().st_size >= self.max_bytes and count > 0:
                return True
        return False

    def _evict_one_locked(self) -> None:
        routine = self._conn.execute(
            "SELECT id FROM edge_spool WHERE synced_at_utc IS NULL AND priority = 0 ORDER BY created_at_utc ASC, id ASC LIMIT 1;"
        ).fetchone()
        if routine is not None:
            self._conn.execute("DELETE FROM edge_spool WHERE id = ?;", (routine[0],))
            self._conn.execute(
                "UPDATE edge_spool_stats SET evicted_routine_count = evicted_routine_count + 1 WHERE id = 1;"
            )
            return

        critical = self._conn.execute(
            "SELECT id FROM edge_spool WHERE synced_at_utc IS NULL ORDER BY created_at_utc ASC, id ASC LIMIT 1;"
        ).fetchone()
        if critical is not None:
            self._conn.execute("DELETE FROM edge_spool WHERE id = ?;", (critical[0],))
            self._conn.execute(
                "UPDATE edge_spool_stats SET evicted_critical_count = evicted_critical_count + 1 WHERE id = 1;"
            )
            logger.warning("Edge spool saturated with priority=1 records; evicted oldest critical entry id=%s", critical[0])

    def enqueue(
        self,
        event: SwarmTelemetryEvent,
        priority: int,
        qos: int,
        topic: str,
        snapshot_local_path: str | None = None,
    ) -> int:
        """Persist telemetry event to SQLite WAL spool with priority-aware eviction."""
        payload_json = event.model_dump_json()
        ts_str = event.timestamp.astimezone(timezone.utc).isoformat()
        with self._lock:
            while self._needs_eviction_locked():
                self._evict_one_locked()

            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO edge_spool (
                    event_id, project_id, swarm_id, drone_id, metric_type,
                    priority, qos, topic, payload_json, snapshot_local_path,
                    created_at_utc, attempts, synced_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL);
                """,
                (
                    str(event.event_id),
                    event.project_id,
                    str(event.swarm_id),
                    event.drone_id,
                    event.metric_type,
                    int(priority),
                    int(qos),
                    topic,
                    payload_json,
                    snapshot_local_path,
                    ts_str,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def peek_unsynced(self, limit: int = 50) -> list[SpoolRecord]:
        """Fetch next batch ordered by priority DESC then chronological FIFO."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, event_id, project_id, swarm_id, drone_id, metric_type,
                       priority, qos, topic, payload_json, snapshot_local_path,
                       created_at_utc, attempts
                FROM edge_spool
                WHERE synced_at_utc IS NULL
                ORDER BY priority DESC, created_at_utc ASC, id ASC
                LIMIT ?;
                """,
                (int(limit),),
            ).fetchall()
        return [SpoolRecord(*row) for row in rows]

    def mark_synced(self, row_id: int) -> None:
        """Delete an acknowledged spooled row after successful broker delivery."""
        with self._lock:
            self._conn.execute("DELETE FROM edge_spool WHERE id = ?;", (int(row_id),))
            self._conn.commit()

    def increment_attempt(self, row_id: int) -> None:
        """Increment retry counter on transient replay failure."""
        with self._lock:
            self._conn.execute(
                "UPDATE edge_spool SET attempts = attempts + 1 WHERE id = ?;",
                (int(row_id),),
            )
            self._conn.commit()

    def get_status(self, swarm_id: str = "") -> SpoolStatusResponse:
        """Return queued depth, priority breakdown, and eviction statistics."""
        with self._lock:
            total, prio, routine, oldest = self._conn.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(CASE WHEN priority >= 1 THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN priority = 0 THEN 1 ELSE 0 END), 0),
                    MIN(created_at_utc)
                FROM edge_spool
                WHERE synced_at_utc IS NULL;
                """
            ).fetchone()
            evicted_routine, evicted_critical = self._conn.execute(
                "SELECT evicted_routine_count, evicted_critical_count FROM edge_spool_stats WHERE id = 1;"
            ).fetchone()
        return SpoolStatusResponse(
            swarm_id=swarm_id,
            queued_rows=int(total or 0),
            priority_queued_rows=int(prio or 0),
            routine_queued_rows=int(routine or 0),
            evicted_routine_count=int(evicted_routine or 0),
            evicted_critical_count=int(evicted_critical or 0),
            max_records=self.max_records,
            oldest_queued_utc=oldest,
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
