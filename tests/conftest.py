"""Hermetic pytest configuration and test doubles (Constitution Principle VI / FR-014).

All test doubles (in-memory MQTT bus, local filesystem S3 client, and in-memory
Memgraph property graph driver) live strictly inside tests/ so zero mocks, stubs,
or dummy fallbacks ever enter src/.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest
from botocore.exceptions import ClientError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# ---------------------------------------------------------------------------
# PostgreSQL -> SQLite dialect compilation bridge for hermetic ORM tests
# ---------------------------------------------------------------------------

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element: Any, compiler: Any, **kw: Any) -> str:
    return "JSON"


# ---------------------------------------------------------------------------
# Global outbound network socket isolation guard
# ---------------------------------------------------------------------------

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def _is_loopback_target(address: Any) -> bool:
    if isinstance(address, (str, bytes)):
        # AF_UNIX socket path or abstract namespace
        return True
    if isinstance(address, tuple) and len(address) >= 1:
        host = str(address[0])
        return host in _ALLOWED_HOSTS or host.startswith("127.")
    return False


@pytest.fixture(autouse=True)
def _network_isolation_guard(monkeypatch: pytest.MonkeyPatch):
    """Fail any non-loopback network socket attempt during hermetic tests."""
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_create_conn = socket.create_connection

    def _guarded_connect(self: socket.socket, address: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback_target(address):
            raise RuntimeError(f"Hermetic test violation: outbound network blocked ({address!r})")
        return orig_connect(self, address)

    def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback_target(address):
            raise RuntimeError(f"Hermetic test violation: outbound network blocked ({address!r})")
        return orig_connect_ex(self, address)

    def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_loopback_target(address):
            raise RuntimeError(f"Hermetic test violation: outbound network blocked ({address!r})")
        return orig_create_conn(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _guarded_create_connection)
    yield


# ---------------------------------------------------------------------------
# In-memory MQTT pub/sub broker double
# ---------------------------------------------------------------------------

def mqtt_topic_matches(topic_filter: str, topic: str) -> bool:
    """Evaluate MQTT wildcard topic matching (+ single-level, # multi-level)."""
    filter_parts = topic_filter.split("/")
    topic_parts = topic.split("/")
    for idx, f_part in enumerate(filter_parts):
        if f_part == "#":
            return True
        if idx >= len(topic_parts):
            return False
        if f_part != "+" and f_part != topic_parts[idx]:
            return False
    return len(filter_parts) == len(topic_parts)


@dataclass
class PublishedMessage:
    topic: str
    payload: bytes
    qos: int
    retain: bool = False


class InMemoryMqttBus:
    """Thread/async-safe in-memory MQTT broker test double supporting wildcards and disconnects."""

    def __init__(self) -> None:
        self.connected: bool = True
        self.messages: list[PublishedMessage] = []
        self._subscribers: list[tuple[str, Callable[[str, bytes], Awaitable[None] | None]]] = []

    def disconnect(self) -> None:
        self.connected = False

    def reconnect(self) -> None:
        self.connected = True

    def subscribe(
        self,
        topic_filter: str,
        handler: Callable[[str, bytes], Awaitable[None] | None],
    ) -> None:
        self._subscribers.append((topic_filter, handler))

    def unsubscribe(self, handler: Callable[[str, bytes], Awaitable[None] | None]) -> None:
        self._subscribers = [(tf, h) for tf, h in self._subscribers if h != handler]

    async def publish(
        self,
        topic: str,
        payload: bytes | str,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        if not self.connected:
            raise ConnectionError("MQTT broker disconnected")
        raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        self.messages.append(PublishedMessage(topic=topic, payload=raw, qos=qos, retain=retain))
        for topic_filter, handler in list(self._subscribers):
            if mqtt_topic_matches(topic_filter, topic):
                res = handler(topic, raw)
                if asyncio.iscoroutine(res):
                    await res


@pytest.fixture
def in_memory_mqtt_bus() -> InMemoryMqttBus:
    return InMemoryMqttBus()


# ---------------------------------------------------------------------------
# Local filesystem boto3-compatible S3 / MinIO test double
# ---------------------------------------------------------------------------

class _BytesBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class LocalFilesystemS3Client:
    """Filesystem-backed boto3 S3 client double for hermetic MinIO tests."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.unavailable: bool = False

    def _check_available(self) -> None:
        if self.unavailable:
            raise OSError("Simulated MinIO outage")

    def list_buckets(self) -> dict[str, Any]:
        self._check_available()
        buckets = [{"Name": p.name} for p in sorted(self.root.iterdir()) if p.is_dir()]
        return {"Buckets": buckets}

    def create_bucket(self, Bucket: str) -> dict[str, Any]:
        self._check_available()
        (self.root / Bucket).mkdir(parents=True, exist_ok=True)
        return {"Location": f"/{Bucket}"}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str = "application/octet-stream") -> dict[str, Any]:
        self._check_available()
        bucket_dir = self.root / Bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        dest = (bucket_dir / Key).resolve()
        if not str(dest).startswith(str(bucket_dir.resolve())):
            raise ValueError(f"Path traversal blocked: {Key}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Body)
        return {"ETag": f'"{uuid.uuid4().hex}"', "ContentType": ContentType}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self._check_available()
        bucket_dir = self.root / Bucket
        target = (bucket_dir / Key).resolve()
        if not str(target).startswith(str(bucket_dir.resolve())) or not target.is_file():
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
                "GetObject",
            )
        return {"Body": _BytesBody(target.read_bytes())}

    def list_objects_v2(
        self,
        Bucket: str,
        Prefix: str = "",
        ContinuationToken: str | None = None,
    ) -> dict[str, Any]:
        self._check_available()
        bucket_dir = self.root / Bucket
        if not bucket_dir.is_dir():
            return {"Contents": [], "IsTruncated": False}
        contents = []
        for path in sorted(bucket_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(bucket_dir).as_posix()
                if rel.startswith(Prefix):
                    contents.append({"Key": rel, "Size": path.stat().st_size})
        return {"Contents": contents, "IsTruncated": False}


@pytest.fixture
def local_s3_client(tmp_path: Path) -> LocalFilesystemS3Client:
    return LocalFilesystemS3Client(tmp_path / "minio")


@pytest.fixture
def local_minio_store(local_s3_client: LocalFilesystemS3Client):
    from src.uservice.analytics.operations.minio_store import MinioStore

    store = MinioStore(
        endpoint_url="http://127.0.0.1:9000",
        access_key="hermetic-test-access",
        secret_key="hermetic-test-secret",
        s3_client=local_s3_client,
    )
    return store


# ---------------------------------------------------------------------------
# In-memory Memgraph openCypher property-graph driver double
# ---------------------------------------------------------------------------

class InMemoryMemgraphDriver:
    """Structured in-memory property-graph driver handling canonical PMA openCypher queries."""

    def __init__(self) -> None:
        self.unavailable: bool = False
        self.projects: dict[str, dict[str, Any]] = {}
        self.threat_zones: dict[str, dict[str, Any]] = {}
        self.detections: dict[str, dict[str, Any]] = {}
        self.targets: dict[str, dict[str, Any]] = {}
        # event_id -> attribution properties (+ target_id)
        self.attributions: dict[str, dict[str, Any]] = {}
        self.intersects_rels: list[dict[str, Any]] = []

    def _ensure_up(self) -> None:
        if self.unavailable:
            from src.uservice.threat.operations.graph_client import MemgraphUnavailableError

            raise MemgraphUnavailableError("Simulated Memgraph outage")

    async def execute_write(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._ensure_up()
        q = " ".join(query.split())

        if q.startswith("CREATE CONSTRAINT") or q.startswith("CREATE INDEX"):
            return []

        if "MERGE (t:ThreatZone" in q:
            tid = params["threat_id"]
            pid = params["project_id"]
            self.projects.setdefault(pid, {"project_id": pid})
            zone = {
                "threat_id": tid,
                "project_id": pid,
                "name": params["name"],
                "threat_type": params.get("threat_type", "RESTRICTED"),
                "severity": params.get("severity", "high"),
                "lat": float(params["lat"]),
                "lon": float(params["lon"]),
                "radius_m": float(params["radius_m"]),
                "min_alt_m": float(params.get("min_alt_m", 0.0)),
                "max_alt_m": float(params.get("max_alt_m", 500.0)),
                "polygon_geojson": params.get("polygon_geojson"),
                "active": bool(params.get("active", True)),
                "source": params.get("source", "api"),
                "created_at": params.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "created_by": params.get("created_by", "commander"),
                "deactivated_at": params.get("deactivated_at"),
                "deactivated_by": params.get("deactivated_by"),
                "deactivation_reason": params.get("deactivation_reason"),
            }
            self.threat_zones[tid] = zone
            return [{"t": copy.deepcopy(zone)}]

        if "MATCH (t:ThreatZone" in q and "SET t.active = false" in q:
            tid = params["threat_id"]
            pid = params.get("project_id")
            zone = self.threat_zones.get(tid)
            if not zone or (pid and zone["project_id"] != pid):
                return []
            zone["active"] = False
            zone["deactivated_at"] = params.get("deactivated_at") or datetime.now(timezone.utc).isoformat()
            zone["deactivated_by"] = params.get("deactivated_by", "commander")
            zone["deactivation_reason"] = params.get("deactivation_reason", "")
            return [{"t": copy.deepcopy(zone)}]

        if "MERGE (m:SwarmMission" in q and "INTERSECTS_THREAT" in q:
            rel = {
                "command_id": params["command_id"],
                "threat_id": params["threat_id"],
                "project_id": params.get("project_id", "default-theater"),
                "overridden": bool(params.get("overridden", False)),
                "override_rationale": params.get("override_rationale"),
                "hitl_decision_id": params.get("hitl_decision_id"),
                "distance_m": float(params.get("distance_m", 0.0)),
                "detected_at": params.get("detected_at") or datetime.now(timezone.utc).isoformat(),
            }
            self.intersects_rels.append(rel)
            return [{"rel": copy.deepcopy(rel)}]

        if "MERGE (d:DetectionEvent" in q and "MERGE (e:TargetEntity" in q:
            ev_id = params["event_id"]
            tid = params["target_id"]
            pid = params["project_id"]
            self.projects.setdefault(pid, {"project_id": pid})

            detection = {
                "event_id": ev_id,
                "project_id": pid,
                "swarm_id": params["swarm_id"],
                "drone_id": params["drone_id"],
                "mission_id": params.get("mission_id"),
                "target_class": params["target_class"],
                "confidence": float(params["confidence"]),
                "lat": float(params["lat"]),
                "lon": float(params["lon"]),
                "alt_m": float(params.get("alt_m", 0.0)),
                "snapshot_uri": params.get("snapshot_uri"),
                "detected_at": params["detected_at"],
            }
            self.detections[ev_id] = detection

            existing = self.targets.get(tid)
            if existing is None:
                existing = {
                    "target_id": tid,
                    "project_id": pid,
                    "canonical_class": params["canonical_class"],
                    "status": params.get("status", "auto_correlated"),
                    "first_seen_at": params["detected_at"],
                    "last_seen_at": params["detected_at"],
                    "last_lat": float(params["lat"]),
                    "last_lon": float(params["lon"]),
                    "observation_count": 1,
                }
                self.targets[tid] = existing
            else:
                cnt = int(existing["observation_count"]) + 1
                existing["observation_count"] = cnt
                existing["last_seen_at"] = max(existing["last_seen_at"], params["detected_at"])
                existing["first_seen_at"] = min(existing["first_seen_at"], params["detected_at"])
                existing["last_lat"] = float(params["lat"])
                existing["last_lon"] = float(params["lon"])

            self.attributions[ev_id] = {
                "target_id": tid,
                "match_method": params.get("match_method", "auto_spatio_temporal"),
                "distance_m": float(params.get("distance_m", 0.0)),
                "delta_s": float(params.get("delta_s", 0.0)),
                "verified_by_analyst": bool(params.get("verified_by_analyst", False)),
                "reviewed_by": None,
                "reviewed_at": None,
            }
            return [{"e": copy.deepcopy(existing), "d": copy.deepcopy(detection)}]

        if "MATCH (d:DetectionEvent" in q and "SPLIT_EVENT" in q:
            old_tid = params["old_target_id"]
            new_tid = params["new_target_id"]
            ev_id = params["event_id"]
            det = self.detections.get(ev_id)
            attr = self.attributions.get(ev_id)
            old_t = self.targets.get(old_tid)
            if not det or not attr or attr["target_id"] != old_tid or not old_t:
                return []

            new_t = {
                "target_id": new_tid,
                "project_id": det["project_id"],
                "canonical_class": det["target_class"],
                "status": "split",
                "first_seen_at": det["detected_at"],
                "last_seen_at": det["detected_at"],
                "last_lat": det["lat"],
                "last_lon": det["lon"],
                "observation_count": 1,
            }
            self.targets[new_tid] = new_t
            self.attributions[ev_id] = {
                "target_id": new_tid,
                "match_method": "analyst_split",
                "distance_m": 0.0,
                "delta_s": 0.0,
                "verified_by_analyst": True,
                "reviewed_by": params.get("reviewed_by"),
                "reviewed_at": params.get("reviewed_at"),
            }
            remaining = [eid for eid, a in self.attributions.items() if a["target_id"] == old_tid]
            old_t["observation_count"] = len(remaining)
            return [{"old_target": copy.deepcopy(old_t), "new_target": copy.deepcopy(new_t)}]

        if "MATCH (e:TargetEntity" in q and "SET e.status =" in q:
            tid = params["target_id"]
            pid = params.get("project_id")
            target = self.targets.get(tid)
            if not target or (pid and target["project_id"] != pid):
                return []
            target["status"] = params["status"]
            for eid, attr in self.attributions.items():
                if attr["target_id"] == tid:
                    attr["verified_by_analyst"] = True
                    attr["match_method"] = "analyst_confirmed"
                    attr["reviewed_by"] = params.get("reviewed_by")
                    attr["reviewed_at"] = params.get("reviewed_at")
            return [{"e": copy.deepcopy(target)}]

        return []

    async def execute_read(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._ensure_up()
        q = " ".join(query.split())

        if q == "RETURN 1 AS ok":
            return [{"ok": 1}]

        if "MATCH (t:ThreatZone" in q:
            pid = params.get("project_id")
            include_inactive = bool(params.get("include_inactive", False))
            out = []
            for z in self.threat_zones.values():
                if pid and z["project_id"] != pid:
                    continue
                if not include_inactive and not z["active"]:
                    continue
                out.append({"t": copy.deepcopy(z)})
            return out

        if "MATCH (d:DetectionEvent" in q and "event_id" in params:
            det = self.detections.get(params["event_id"])
            return [{"d": copy.deepcopy(det)}] if det else []

        if "MATCH (e:TargetEntity" in q and "target_id: $target_id" in q:
            tid = params.get("target_id")
            pid = params.get("project_id")
            target = self.targets.get(tid)
            if not target or (pid and target["project_id"] != pid):
                return []
            obs = []
            for eid, attr in self.attributions.items():
                if attr["target_id"] == tid:
                    det = self.detections.get(eid, {})
                    obs.append({**copy.deepcopy(det), **copy.deepcopy(attr)})
            obs.sort(key=lambda x: str(x.get("detected_at", "")))
            return [{"e": copy.deepcopy(target), "observations": obs}]

        if "MATCH (e:TargetEntity" in q:
            pid = params.get("project_id")
            tclass = params.get("target_class")
            status = params.get("status")
            out = []
            for t in self.targets.values():
                if pid and t["project_id"] != pid:
                    continue
                if tclass and t["canonical_class"].lower() != str(tclass).lower():
                    continue
                if status and t["status"] != status:
                    continue
                item = copy.deepcopy(t)
                matching_events = [
                    self.detections[eid]
                    for eid, attr in self.attributions.items()
                    if attr["target_id"] == t["target_id"] and eid in self.detections
                ]
                matching_events.sort(key=lambda d: str(d.get("detected_at", "")))
                item["latest_event_id"] = matching_events[-1]["event_id"] if matching_events else None
                item["latest_snapshot_uri"] = matching_events[-1].get("snapshot_uri") if matching_events else None
                out.append({"e": item})
            return out

        return []


@pytest.fixture
def in_memory_memgraph_driver() -> InMemoryMemgraphDriver:
    return InMemoryMemgraphDriver()


@pytest.fixture
def in_memory_memgraph_client(in_memory_memgraph_driver: InMemoryMemgraphDriver):
    from src.uservice.threat.operations.graph_client import MemgraphClient

    return MemgraphClient(driver=in_memory_memgraph_driver)


# ---------------------------------------------------------------------------
# Hermetic async SQLite ORM session fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def sqlite_db_session():
    """Provide a clean per-test SQLite async session with all C2 ORM tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Import all ORM storage models so metadata registers every table cleanly
    from src.uservice.database.base import Base  # noqa: F401
    import src.uservice.smeac.models.storage.smeac  # noqa: F401
    import src.uservice.smeac.models.contract.command  # noqa: F401
    import src.uservice.smeac.models.contract.violation  # noqa: F401
    import src.uservice.hitl.models.storage.decision  # noqa: F401
    import src.uservice.operation.models  # noqa: F401
    import src.uservice.operation.audit  # noqa: F401
    import src.uservice.swarm.models.storage.instance  # noqa: F401
    import src.uservice.telemetry.models.storage.live_state  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()
