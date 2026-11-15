"""Hermetic REST contract tests for target lineage and MinIO snapshot proxy."""

from datetime import datetime, timezone
import uuid

import httpx
import pytest

from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.database.engine import get_db
from src.uservice.main import app
from src.uservice.security.jit import issue_jit_credential
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.threat.operations.correlator import TargetCorrelator


async def _analyst_headers() -> dict[str, str]:
    tok = await issue_jit_credential(
        agent_name="analyst-1",
        scopes=["analytics:read", "analytics:write", "threat:read"],
        lifetime_seconds=3600,
    )
    return {"Authorization": f"Bearer {tok['token']}"}


@pytest.mark.asyncio
async def test_target_lineage_review_and_snapshot_proxy(
    sqlite_db_session,
    in_memory_memgraph_client,
    local_minio_store: MinioStore,
):
    async def _override_db():
        yield sqlite_db_session

    app.dependency_overrides[get_db] = _override_db
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.minio_store = local_minio_store

    await local_minio_store.ensure_buckets()

    correlator = TargetCorrelator(graph_client=in_memory_memgraph_client)
    ev1_id = uuid.uuid4()
    ev2_id = uuid.uuid4()
    s3_key = f"projects/default-theater/swarms/swarm-a/drones/drone-1/{ev1_id}.jpg"
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    await local_minio_store.put_object(
        MinioStore.SNAPSHOT_BUCKET,
        s3_key,
        jpeg_bytes,
        content_type="image/jpeg",
    )

    t0 = datetime.now(timezone.utc)
    ev1 = SwarmTelemetryEvent(
        event_id=ev1_id,
        timestamp=t0,
        project_id="default-theater",
        swarm_id="swarm-a",
        drone_id="drone-1",
        metric_type="detection",
        lat=52.5300,
        lon=13.4100,
        alt_m=55.0,
        target_class="apc",
        confidence=0.92,
        bbox=[12, 14, 120, 140],
        snapshot_uri=f"s3://{MinioStore.SNAPSHOT_BUCKET}/{s3_key}",
    )
    ev2 = SwarmTelemetryEvent(
        event_id=ev2_id,
        timestamp=t0,
        project_id="default-theater",
        swarm_id="swarm-a",
        drone_id="drone-2",
        metric_type="detection",
        lat=52.5301,
        lon=13.4101,
        alt_m=60.0,
        target_class="apc",
        confidence=0.88,
        bbox=[20, 22, 110, 130],
        snapshot_uri=f"s3://{MinioStore.SNAPSHOT_BUCKET}/{s3_key}",
    )
    r1 = await correlator.ingest_detection(ev1)
    await correlator.ingest_detection(ev2)
    target_id = r1["target_id"]

    try:
        headers = await _analyst_headers()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. List correlated targets
            list_res = await client.get("/api/v1/targets?project_id=default-theater", headers=headers)
            assert list_res.status_code == 200
            items = list_res.json()["data"]["items"]
            assert len(items) == 1
            assert items[0]["target_id"] == target_id
            assert items[0]["observation_count"] == 2

            # 2. Target lineage returns observations + snapshot proxy URL
            lineage_res = await client.get(
                f"/api/v1/targets/{target_id}/lineage?project_id=default-theater",
                headers=headers,
            )
            assert lineage_res.status_code == 200
            lineage_data = lineage_res.json()["data"]
            assert len(lineage_data["observations"]) == 2
            proxy_url = lineage_data["observations"][0]["snapshot_proxy_url"]
            assert f"/api/v1/analytics/detections/{ev1_id}/snapshot" in proxy_url

            # 3. Snapshot endpoint requires auth (401 without token) and serves JPEG with nosniff
            unauth = await client.get(f"/api/v1/analytics/detections/{ev1_id}/snapshot")
            assert unauth.status_code == 401

            snap_res = await client.get(
                f"/api/v1/analytics/detections/{ev1_id}/snapshot?project_id=default-theater",
                headers=headers,
            )
            assert snap_res.status_code == 200
            assert snap_res.headers["content-type"] == "image/jpeg"
            assert snap_res.headers.get("x-content-type-options") == "nosniff"
            assert snap_res.content.startswith(b"\xff\xd8\xff")

            missing_snap = await client.get(
                f"/api/v1/analytics/detections/{uuid.uuid4()}/snapshot",
                headers=headers,
            )
            assert missing_snap.status_code == 404

            # 4. Analyst review (422 if split_event misses split_event_id; 200 on confirm & split)
            bad_split = await client.post(
                f"/api/v1/targets/{target_id}/review",
                headers=headers,
                json={"project_id": "default-theater", "action": "split_event"},
            )
            assert bad_split.status_code == 422

            confirm_res = await client.post(
                f"/api/v1/targets/{target_id}/review",
                headers=headers,
                json={"project_id": "default-theater", "action": "confirm", "notes": "Confirmed APC"},
            )
            assert confirm_res.status_code == 200
            assert confirm_res.json()["data"]["status"] == "confirmed"

            split_res = await client.post(
                f"/api/v1/targets/{target_id}/review",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "action": "split_event",
                    "split_event_id": str(ev2_id),
                },
            )
            assert split_res.status_code == 200
            assert split_res.json()["data"]["target_id"] != target_id
    finally:
        app.dependency_overrides.pop(get_db, None)
