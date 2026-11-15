"""Hermetic REST contract tests for /api/v1/threats and HITL 422 override enforcement."""

import json
import uuid

import httpx
import pytest

from src.uservice.database.engine import get_db
from src.uservice.hitl.models.storage.decision import HitlDecision
from src.uservice.main import app
from src.uservice.security.jit import issue_jit_credential


async def _commander_headers(scopes: list[str] | None = None) -> dict[str, str]:
    tok = await issue_jit_credential(
        agent_name="commander-1",
        scopes=scopes or [
            "threat:read",
            "threat:write",
            "hitl:read",
            "hitl:decide",
            "smeac:create",
            "smeac:read",
        ],
        lifetime_seconds=3600,
    )
    return {"Authorization": f"Bearer {tok['token']}"}


@pytest.mark.asyncio
async def test_threat_crud_and_outage_returns_500(
    sqlite_db_session,
    in_memory_memgraph_driver,
    in_memory_memgraph_client,
    monkeypatch,
):
    async def _override_db():
        yield sqlite_db_session

    app.dependency_overrides[get_db] = _override_db
    app.state.memgraph_client = in_memory_memgraph_client
    try:
        headers = await _commander_headers()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create active threat
            create_res = await client.post(
                "/api/v1/threats",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "name": "Mobile SA-17 Battery North",
                    "threat_type": "SAM",
                    "severity": "critical",
                    "lat": 52.5310,
                    "lon": 13.4120,
                    "radius_m": 800.0,
                    "min_alt_m": 0.0,
                    "max_alt_m": 450.0,
                    "source": "sigint-operator",
                },
            )
            assert create_res.status_code == 201
            body = create_res.json()
            threat_id = body["data"]["threat_id"]
            assert body["data"]["active"] is True
            assert body.get("meta") is None

            # 2. List active threats
            list_res = await client.get("/api/v1/threats?project_id=default-theater", headers=headers)
            assert list_res.status_code == 200
            list_body = list_res.json()
            assert len(list_body["data"]["threats"]) == 1
            assert "fallback_static_zones" not in list_body["data"]

            # 3. Deactivation requires non-blank min_length=5 reason
            bad_deact = await client.patch(
                f"/api/v1/threats/{threat_id}/deactivate",
                headers=headers,
                json={"project_id": "default-theater", "reason": "ok"},
            )
            assert bad_deact.status_code == 422

            # 4. Valid manual deactivation
            good_deact = await client.patch(
                f"/api/v1/threats/{threat_id}/deactivate",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "reason": "SEAD confirmed battery neutralized by visual recon.",
                },
            )
            assert good_deact.status_code == 200
            assert good_deact.json()["data"]["active"] is False

            # 5. Memgraph outage -> both POST and GET return HTTP 500 directly
            in_memory_memgraph_driver.unavailable = True
            outage_post = await client.post(
                "/api/v1/threats",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "name": "Should Fail Closed",
                    "threat_type": "EW",
                    "severity": "high",
                    "lat": 52.50,
                    "lon": 13.40,
                    "radius_m": 500.0,
                },
            )
            assert outage_post.status_code == 500

            outage_get = await client.get("/api/v1/threats?project_id=default-theater", headers=headers)
            assert outage_get.status_code == 500

            # 6. MinIO outage -> GET /api/v1/analytics/aar returns HTTP 500 directly
            from src.uservice.analytics.operations.minio_store import MinioUnavailableError

            class _DownMinio:
                async def list_objects(self, *args, **kwargs):
                    raise MinioUnavailableError("Simulated MinIO outage")

            tok_analytics = await issue_jit_credential(
                agent_name="analyst-1",
                scopes=["analytics:read"],
                lifetime_seconds=3600,
            )
            prev_minio = getattr(app.state, "minio_store", None)
            app.state.minio_store = _DownMinio()
            try:
                aar_outage = await client.get(
                    "/api/v1/analytics/aar?project_id=default-theater",
                    headers={"Authorization": f"Bearer {tok_analytics['token']}"},
                )
                assert aar_outage.status_code == 500
            finally:
                app.state.minio_store = prev_minio
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_hitl_override_422_on_blank_rationale(
    sqlite_db_session,
    in_memory_memgraph_client,
):
    async def _override_db():
        yield sqlite_db_session

    app.dependency_overrides[get_db] = _override_db
    app.state.memgraph_client = in_memory_memgraph_client

    swarm_id = uuid.uuid4()
    command_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    threat_id = str(uuid.uuid4())

    record = HitlDecision(
        id=decision_id,
        project_id="default-theater",
        swarm_command_id=command_id,
        commander_id="commander-1",
        decision="pending",
        action_summary="RECON intersects SA-17 Battery",
        timeout_seconds=600,
        status="pending",
        is_threat_override=True,
        threat_zone_ids=json.dumps([threat_id]),
    )
    sqlite_db_session.add(record)
    await sqlite_db_session.commit()

    try:
        headers = await _commander_headers()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Blank rationale must be rejected with HTTP 422
            res_blank = await client.post(
                f"/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide",
                headers=headers,
                json={"decision": "approved", "rationale": "   "},
            )
            assert res_blank.status_code == 422

            # Valid justification succeeds
            res_ok = await client.post(
                f"/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide",
                headers=headers,
                json={
                    "decision": "approved",
                    "rationale": "Authorized tactical transit under SEAD suppression window.",
                },
            )
            assert res_ok.status_code == 200
            assert res_ok.json()["data"]["command_status"] == "executing"
    finally:
        app.dependency_overrides.pop(get_db, None)
