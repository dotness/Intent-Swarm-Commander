"""Hermetic end-to-end PMA C4ISR pipeline integration test (MQTT -> DDIL -> Parquet -> AAR -> Targets -> Threat HITL -> Copilot)."""

from datetime import datetime, timezone
from pathlib import Path
import uuid

import httpx
import pytest

from src.edge.telemetry.publisher import EdgeTelemetryPublisher
from src.edge.telemetry.spool import EdgeSpool
from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.database.engine import get_db
from src.uservice.hitl.facade import hitl as hitl_module
from src.uservice.main import app
from src.uservice.operation import facade as operation_facade
from src.uservice.security.jit import issue_jit_credential
from src.uservice.smeac.operations import smeac_agents
from src.uservice.smeac.operations.copilot import SmeacCopilot
from src.uservice.smeac.operations.smeac_agents import SmeacParseResult, SwarmCommandDTO
from src.uservice.swarm.models.storage.instance import SwarmInstance
from src.uservice.telemetry.models.contract.events import (
    WILDCARD_TELEMETRY_TOPIC,
    SwarmTelemetryEvent,
)
from src.uservice.telemetry.models.storage.live_state import LiveTelemetryStore
from src.uservice.telemetry.operations.compactor import ParquetCompactor
from src.uservice.telemetry.operations.ingestor import TelemetryIngestor
from src.uservice.threat.operations.correlator import TargetCorrelator


@pytest.mark.asyncio
async def test_full_pma_c4isr_pipeline_hermetic(
    tmp_path: Path,
    sqlite_db_session,
    in_memory_mqtt_bus,
    local_s3_client,
    local_minio_store: MinioStore,
    in_memory_memgraph_driver,
    in_memory_memgraph_client,
    monkeypatch: pytest.MonkeyPatch,
):
    signaled_workflows: list[dict] = []

    async def _noop_start_workflow(*args, **kwargs):
        return "wf-pma-ok"

    async def _capture_signal_workflow(workflow_id: str, signal_name: str, arg=None):
        signaled_workflows.append({"workflow_id": workflow_id, "signal_name": signal_name, "arg": arg})

    async def _stub_parse_smeac_order(**kwargs):
        return SmeacParseResult(
            commands=[
                SwarmCommandDTO(
                    mission_type="recon",
                    formation_type="line",
                    target_area={
                        "type": "LineString",
                        "coordinates": [[13.4100, 52.5300], [13.4120, 52.5310]],
                    },
                    drone_count=2,
                    altitude_m=60.0,
                    priority="high",
                )
            ],
            reasoning="Northern MSR recon route crossing target corridor.",
        )

    async def _stub_llm(self, *, project_id, commander_intent, threats_desc, targets_desc, aar_desc):
        return {
            "situation": f"{project_id}: {'; '.join(threats_desc)}. Targets: {'; '.join(targets_desc)}. {aar_desc}",
            "mission": commander_intent,
            "execution": "Route alpha swarm around active SAM envelope.",
            "admin_logistics": "DDIL spooling and Parquet AAR active.",
            "command_signal": "Mandatory HITL gate enforced.",
        }

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(operation_facade, "start_workflow", _noop_start_workflow)
    monkeypatch.setattr(hitl_module, "signal_workflow", _capture_signal_workflow)
    monkeypatch.setattr(smeac_agents, "parse_smeac_order", _stub_parse_smeac_order)
    monkeypatch.setattr(SmeacCopilot, "_synthesize_with_llm", _stub_llm)

    await local_minio_store.ensure_buckets()

    live_store = LiveTelemetryStore()
    compactor = ParquetCompactor(minio_store=local_minio_store, flush_interval_s=5.0)
    correlator = TargetCorrelator(graph_client=in_memory_memgraph_client)
    ingestor = TelemetryIngestor(
        live_store=live_store,
        compactor=compactor,
        detection_callback=correlator.ingest_detection,
        db_session_factory=None,
    )
    in_memory_mqtt_bus.subscribe(WILDCARD_TELEMETRY_TOPIC, ingestor.handle_raw_message)

    async def _override_db():
        yield sqlite_db_session

    app.dependency_overrides[get_db] = _override_db
    app.state.telemetry_store = live_store
    app.state.minio_store = local_minio_store
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.parquet_compactor = compactor
    app.state.telemetry_ingestor = ingestor

    swarm_uuid = uuid.uuid4()
    swarm_id = str(swarm_uuid)
    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_uuid,
            name="Alpha Recon Swarm",
            project_id="default-theater",
            status="active",
            drone_count=2,
            endpoint_url="mqtt://mosquitto:1883",
            created_by="commander-pma",
        )
    )
    await sqlite_db_session.commit()

    spool_1 = EdgeSpool(db_path=str(tmp_path / "drone1_spool.db"))
    pub_drone_1 = EdgeTelemetryPublisher(
        project_id="default-theater",
        swarm_id=swarm_id,
        drone_id="drone-1",
        spool=spool_1,
        transport=in_memory_mqtt_bus,
        minio_store=local_minio_store,
    )
    pub_drone_2 = EdgeTelemetryPublisher(
        project_id="default-theater",
        swarm_id=swarm_id,
        drone_id="drone-2",
        spool=EdgeSpool(db_path=str(tmp_path / "drone2_spool.db")),
        transport=in_memory_mqtt_bus,
        minio_store=local_minio_store,
    )

    try:
        tok = await issue_jit_credential(
            agent_name="commander-pma",
            scopes=[
                "swarm:read",
                "swarm:write",
                "telemetry:read",
                "threat:read",
                "threat:write",
                "analytics:read",
                "analytics:write",
                "smeac:create",
                "smeac:read",
                "hitl:read",
                "hitl:decide",
            ],
            lifetime_seconds=3600,
        )
        headers = {"Authorization": f"Bearer {tok['token']}"}

        # 1. Live telemetry push from Drone 1
        ev_live = SwarmTelemetryEvent(
            project_id="default-theater",
            swarm_id=swarm_id,
            drone_id="drone-1",
            metric_type="navigation",
            lat=52.5200,
            lon=13.4050,
            alt_m=60.0,
            battery_pct=95.0,
        )
        assert await pub_drone_1.publish_event(ev_live) is True

        # 2. Simulated RF/DDIL disconnect: spool navigation + cropped JPEG detection locally
        in_memory_mqtt_bus.disconnect()
        local_s3_client.unavailable = True

        ev_queued_nav = SwarmTelemetryEvent(
            project_id="default-theater",
            swarm_id=swarm_id,
            drone_id="drone-1",
            metric_type="navigation",
            lat=52.5250,
            lon=13.4080,
            alt_m=65.0,
            battery_pct=92.0,
        )
        assert await pub_drone_1.publish_event(ev_queued_nav) is False

        jpeg_blob = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        det_ev1 = await pub_drone_1.publish_detection(
            lat=52.5300,
            lon=13.4100,
            alt_m=70.0,
            target_class="armored_vehicle",
            confidence=0.93,
            bbox=[10, 10, 80, 90],
            snapshot_bytes=jpeg_blob,
            battery_pct=91.0,
        )
        assert spool_1.get_status(swarm_id).queued_rows == 2

        # 3. Link recovers -> drain backlog uploads snapshot & replays queued events (replayed=True)
        in_memory_mqtt_bus.reconnect()
        local_s3_client.unavailable = False
        drained = await pub_drone_1.drain_backlog()
        assert drained == 2
        assert spool_1.get_status(swarm_id).queued_rows == 0

        # 4. Drone 2 sees same target 15m away -> correlates into same TargetEntity
        await pub_drone_2.publish_detection(
            lat=52.5301,
            lon=13.4101,
            alt_m=72.0,
            target_class="armored_vehicle",
            confidence=0.89,
            bbox=[14, 18, 92, 96],
            snapshot_bytes=jpeg_blob,
            battery_pct=94.0,
        )

        # 5. Compact buffered events into MinIO Parquet
        uploaded_keys = await compactor.flush()
        assert len(uploaded_keys) >= 1

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # A. Live telemetry projection via REST facade
            tel_res = await client.get(f"/api/v1/swarms/{swarm_id}/telemetry", headers=headers)
            assert tel_res.status_code == 200
            drones = tel_res.json()["drones"]
            assert len(drones) == 2

            # B. Sub-2s AAR over Parquet partitions
            aar_res = await client.get(
                "/api/v1/analytics/aar?project_id=default-theater&query_type=summary",
                headers=headers,
            )
            assert aar_res.status_code == 200
            aar_data = aar_res.json()["data"]
            assert aar_data["engine"] == "duckdb"
            assert aar_data["execution_ms"] < 2000.0
            assert aar_data["rows"][0]["total_events"] == 4
            assert aar_data["rows"][0]["detection_count"] == 2
            assert aar_data["rows"][0]["replayed_count"] == 2

            # C. Correlated target lineage & MinIO JPEG proxy
            tgt_res = await client.get("/api/v1/targets?project_id=default-theater", headers=headers)
            assert tgt_res.status_code == 200
            targets = tgt_res.json()["data"]["items"]
            assert len(targets) == 1
            assert targets[0]["observation_count"] == 2
            target_id = targets[0]["target_id"]

            snap_res = await client.get(
                f"/api/v1/analytics/detections/{det_ev1.event_id}/snapshot?project_id=default-theater",
                headers=headers,
            )
            assert snap_res.status_code == 200
            assert snap_res.headers["content-type"] == "image/jpeg"
            assert snap_res.content.startswith(b"\xff\xd8\xff")

            # D. ThreatZone registration + route intersection HITL gate + 422 blank rationale + override
            threat_res = await client.post(
                "/api/v1/threats",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "name": "Mobile SA-17 North Corridor",
                    "threat_type": "SAM",
                    "severity": "critical",
                    "lat": 52.5310,
                    "lon": 13.4120,
                    "radius_m": 800.0,
                },
            )
            assert threat_res.status_code == 201
            threat_id = threat_res.json()["data"]["threat_id"]

            order_res = await client.post(
                f"/api/v1/swarms/{swarm_id}/orders",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "situation": "Enemy SAM reported along northern MSR.",
                    "mission": "Fly recon corridor 52.5310, 13.4120 immediately.",
                    "execution": "High-speed echelon sweep across 52.5310, 13.4120.",
                },
            )
            assert order_res.status_code == 201
            order_data = order_res.json()["data"]
            assert order_data["status"] == "pending_hitl"
            assert order_data["pending_hitl_decision_id"] is not None
            decision_id = order_data["pending_hitl_decision_id"]
            assert any(c["threat_id"] == threat_id for c in order_data["threat_conflicts"])

            # Blank override justification rejected with HTTP 422
            bad_hitl = await client.post(
                f"/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide",
                headers=headers,
                json={"decision": "approved", "rationale": ""},
            )
            assert bad_hitl.status_code == 422

            # Explicit justification succeeds & records Memgraph INTERSECTS_THREAT
            ok_hitl = await client.post(
                f"/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide",
                headers=headers,
                json={
                    "decision": "approved",
                    "rationale": "SEAD suppression window active for corridor transit.",
                },
            )
            assert ok_hitl.status_code == 200
            assert ok_hitl.json()["data"]["command_status"] == "executing"
            assert len(in_memory_memgraph_driver.intersects_rels) == 1
            assert len(signaled_workflows) == 1
            assert signaled_workflows[0]["signal_name"] == "hitl_decision"

            # E. Non-executing SMEAC Copilot returns grounded draft_only=True citing Threat, Target & AAR
            draft_res = await client.post(
                "/api/v1/smeac/draft",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "commander_intent": "Re-task alpha swarm around Mobile SA-17 to verify target.",
                },
            )
            assert draft_res.status_code == 200
            draft = draft_res.json()["data"]
            assert draft["draft_only"] is True
            assert draft["status"] == "draft"
            cite_types = {c["source_type"] for c in draft["source_citations"]}
            assert {"threat_zone", "target_entity", "aar_summary"}.issubset(cite_types)
            assert target_id in {c["source_id"] for c in draft["source_citations"]}
    finally:
        app.dependency_overrides.pop(get_db, None)
