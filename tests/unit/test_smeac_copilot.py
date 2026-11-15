"""Hermetic unit & API tests for non-executing read-only SMEAC Copilot."""

from datetime import datetime, timezone
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.database.engine import get_db
from src.uservice.hitl.models.storage.decision import HitlDecision
from src.uservice.main import app
from src.uservice.operation import facade as operation_facade
from src.uservice.security.jit import issue_jit_credential
from src.uservice.smeac.models.contract.command import SwarmCommand
from src.uservice.smeac.models.storage.smeac import SmeacOrder
from src.uservice.smeac.operations import smeac_agents
from src.uservice.smeac.operations.copilot import SmeacCopilot
from src.uservice.smeac.operations.smeac_agents import SmeacParseResult, SwarmCommandDTO
from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent
from src.uservice.telemetry.operations.compactor import ParquetCompactor
from src.uservice.threat.facade.threat import ThreatFacade
from src.uservice.threat.models.contract.schemas import ThreatZoneCreateRequest


@pytest.mark.asyncio
async def test_smeac_copilot_is_strictly_read_only_with_grounded_citations_and_fails_on_outage(
    sqlite_db_session,
    in_memory_memgraph_driver,
    in_memory_memgraph_client,
    local_minio_store: MinioStore,
    monkeypatch: pytest.MonkeyPatch,
):
    workflow_calls: list[str] = []

    async def _fail_if_workflow_started(*args, **kwargs):
        workflow_calls.append("called")
        raise AssertionError("Copilot MUST NEVER start a Temporal workflow")

    async def _stub_llm(self, *, project_id, commander_intent, threats_desc, targets_desc, aar_desc):
        threat_summary = "; ".join(threats_desc) if threats_desc else "None"
        return {
            "situation": f"Theater {project_id}. Active threats: {threat_summary}. AAR: {aar_desc}",
            "mission": f"Non-executing draft mission for intent: {commander_intent}",
            "execution": "Coordinate corridor ISR avoiding active radar envelopes.",
            "admin_logistics": "Standard swarm reserve and telemetry logging active.",
            "command_signal": "Direct datalink and commander HITL channel.",
        }

    monkeypatch.setattr(operation_facade, "start_workflow", _fail_if_workflow_started)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    async def _override_db():
        yield sqlite_db_session

    app.dependency_overrides[get_db] = _override_db
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.minio_store = local_minio_store

    await local_minio_store.ensure_buckets()

    # Seed one active ThreatZone in Memgraph & one detection in MinIO Parquet
    t_facade = ThreatFacade(
        session=sqlite_db_session,
        user={"sub": "commander-1", "scope": "threat:read threat:write"},
        graph_client=in_memory_memgraph_client,
    )
    threat = await t_facade.create_threat(
        ThreatZoneCreateRequest(
            project_id="default-theater",
            name="SA-11 Radar Hill",
            threat_type="SAM",
            severity="critical",
            lat=52.5320,
            lon=13.4150,
            radius_m=900.0,
        )
    )

    compactor = ParquetCompactor(minio_store=local_minio_store, flush_interval_s=5.0)
    compactor.enqueue(
        SwarmTelemetryEvent(
            event_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            project_id="default-theater",
            swarm_id="swarm-alpha",
            drone_id="drone-1",
            metric_type="detection",
            lat=52.5300,
            lon=13.4100,
            alt_m=80.0,
            battery_pct=84.0,
            target_class="command_vehicle",
            confidence=0.91,
        )
    )
    await compactor.flush()

    tok = await issue_jit_credential(
        agent_name="commander-1",
        scopes=["smeac:create", "smeac:read", "threat:read", "analytics:read"],
        lifetime_seconds=3600,
    )
    headers = {"Authorization": f"Bearer {tok['token']}"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Missing GEMINI_API_KEY must fail with 500 rather than falling back to a template
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)
            no_key_res = await client.post(
                "/api/v1/smeac/draft",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "commander_intent": "Draft contingency patrol route.",
                },
            )
            assert no_key_res.status_code == 500

            monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
            monkeypatch.setattr(SmeacCopilot, "_synthesize_with_llm", _stub_llm)

            res = await client.post(
                "/api/v1/smeac/draft",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "commander_intent": "Conduct northern corridor ISR avoiding radar envelope.",
                    "include_aar_context": True,
                    "include_threat_context": True,
                },
            )
            assert res.status_code == 200
            payload = res.json()
            assert payload["meta"]["copilot_engine"] == "gemini_rag"
            data = payload["data"]
            assert data["draft_only"] is True
            assert data["status"] == "draft"
            assert data["project_id"] == "default-theater"
            assert "SA-11 Radar Hill" in data["situation"] or any(
                c["source_id"] == threat.threat_id for c in data["source_citations"]
            )
            assert len(data["source_citations"]) >= 2

            # Zero Temporal workflows & zero SQL writes
            assert len(workflow_calls) == 0
            order_count = await sqlite_db_session.scalar(select(func.count()).select_from(SmeacOrder))
            cmd_count = await sqlite_db_session.scalar(select(func.count()).select_from(SwarmCommand))
            hitl_count = await sqlite_db_session.scalar(select(func.count()).select_from(HitlDecision))
            assert order_count == 0
            assert cmd_count == 0
            assert hitl_count == 0

            # When Memgraph goes down, copilot must fail hard with HTTP 500 (no degraded_mode)
            in_memory_memgraph_driver.unavailable = True
            outage_res = await client.post(
                "/api/v1/smeac/draft",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "commander_intent": "Draft contingency patrol route.",
                },
            )
            assert outage_res.status_code == 500
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_smeac_order_persists_draft_source_refs_round_trip(
    sqlite_db_session,
    in_memory_memgraph_client,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.uservice.swarm.models.storage.instance import SwarmInstance, SwarmStatus

    async def _noop_start_workflow(*args, **kwargs):
        return "wf-ok"

    async def _stub_parse_smeac_order(**kwargs):
        return SmeacParseResult(
            commands=[
                SwarmCommandDTO(
                    mission_type="patrol",
                    formation_type="line",
                    target_area={"type": "Point", "coordinates": [13.40, 52.52]},
                    drone_count=3,
                    altitude_m=60.0,
                    priority="normal",
                )
            ],
            reasoning="Parsed patrol command via Gemini test double.",
        )

    monkeypatch.setattr(operation_facade, "start_workflow", _noop_start_workflow)
    monkeypatch.setattr(smeac_agents, "parse_smeac_order", _stub_parse_smeac_order)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    swarm_id = uuid.uuid4()
    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_id,
            name="swarm-draft-ref-test",
            project_id="default-theater",
            status=SwarmStatus.READY.value,
            drone_count=3,
            created_by="commander-1",
        )
    )
    await sqlite_db_session.flush()

    async def _override_db():
        yield sqlite_db_session

    app.dependency_overrides[get_db] = _override_db
    app.state.memgraph_client = in_memory_memgraph_client

    tok = await issue_jit_credential(
        agent_name="commander-1",
        scopes=["smeac:create", "smeac:read"],
        lifetime_seconds=3600,
    )
    headers = {"Authorization": f"Bearer {tok['token']}"}
    expected_refs = ["threat_zone:threat-001", "aar_summary:default-theater"]

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            post_res = await client.post(
                f"/api/v1/swarms/{swarm_id}/orders",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "situation": "Corridor monitored.",
                    "mission": "Patrol 52.52, 13.40.",
                    "execution": "Maintain 60m altitude.",
                    "draft_source_refs": expected_refs,
                },
            )
            assert post_res.status_code == 201
            order_data = post_res.json()["data"]
            assert order_data["draft_source_refs"] == expected_refs

            order_id = uuid.UUID(order_data["order_id"])
            stored = await sqlite_db_session.get(SmeacOrder, order_id)
            assert stored is not None
            assert stored.draft_source_refs is not None
            assert '"threat_zone:threat-001"' in stored.draft_source_refs

            get_res = await client.get(
                f"/api/v1/swarms/{swarm_id}/orders/{order_id}",
                headers=headers,
            )
            assert get_res.status_code == 200
            assert get_res.json()["data"]["draft_source_refs"] == expected_refs
    finally:
        app.dependency_overrides.pop(get_db, None)
