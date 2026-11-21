"""Hermetic unit & API tests for Coordinate-Free Corridor Survey SMEAC intake, dispatch, C2 API, and security."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.corridor.models.storage.survey import CorridorSurvey
from src.uservice.database.engine import get_db
from src.uservice.main import app
from src.uservice.operation import facade as operation_facade
from src.uservice.security.jit import issue_jit_credential
from src.uservice.smeac.models.contract.command import MissionType, SwarmCommand
from src.uservice.smeac.operations import smeac_agents
from src.uservice.smeac.operations.process import (
    ProcessSmeacInput,
    dispatch_edge_mission_activity,
    parse_smeac_activity,
)
from src.uservice.smeac.operations.smeac_agents import (
    GeoJsonTargetArea,
    SmeacParseResult,
    SwarmCommandDTO,
)
from src.uservice.swarm.models.storage.instance import SwarmInstance, SwarmStatus


def _install_db_override(session):
    async def _override():
        yield session

    app.dependency_overrides[get_db] = _override


@pytest.mark.asyncio
async def test_us1_coordinate_free_smeac_intake_and_lead_scout_assignment(
    sqlite_db_session,
    in_memory_memgraph_client,
    local_minio_store: MinioStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """T010 [US1]: Coordinate-free SMEAC order validates params, defaults 20m, assigns drone-1 + staging holds, and persists CorridorSurvey."""
    captured_workflows: list[ProcessSmeacInput] = []

    async def _capture_workflow(wf_cls, wf_input, *, task_queue: str, workflow_id: str):
        captured_workflows.append(wf_input)
        return workflow_id

    monkeypatch.setattr(operation_facade, "start_workflow", _capture_workflow)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    swarm_id = uuid.uuid4()
    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_id,
            name="Alpha Corridor Swarm",
            project_id="default-theater",
            endpoint_url="http://127.0.0.1:18090",
            status=SwarmStatus.READY.value,
            drone_count=3,
            created_by="commander-1",
        )
    )
    await sqlite_db_session.commit()

    async def _stub_parse_smeac_order(**kwargs):
        return SmeacParseResult(
            commands=[
                SwarmCommandDTO(
                    mission_type="corridor_survey",
                    formation_type="line",
                    target_area=GeoJsonTargetArea(type="RelativeCorridor", coordinates=[]),
                    target_object_class="vehicle",
                    drone_count=3,
                    altitude_m=None,
                    priority="normal",
                    survey_params={
                        "target_distance_m": None,
                        "return_to_origin": True,
                        "corridor_descriptor": "subterranean maintenance corridor",
                        "intelligence_focus": ["vehicle", "hazard"],
                        "min_altitude_m": 1.2,
                        "max_altitude_m": 2.0,
                        "cruise_speed_ms": 1.5,
                    },
                )
            ],
            reasoning="Coordinate-free corridor survey assigned to drone-1; drone-2 and drone-3 hold at staging.",
        )

    monkeypatch.setattr(smeac_agents, "parse_smeac_order", _stub_parse_smeac_order)

    _install_db_override(sqlite_db_session)
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.minio_store = local_minio_store

    tok = await issue_jit_credential(
        agent_name="commander-1",
        scopes=["smeac:create", "smeac:read", "swarm:read"],
        lifetime_seconds=3600,
    )
    headers = {"Authorization": f"Bearer {tok['token']}"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                f"/api/v1/swarms/{swarm_id}/orders",
                headers=headers,
                json={
                    "project_id": "default-theater",
                    "situation": "Unmapped corridor ahead of lead UAV.",
                    "mission": "Go check the corridor and go back; note any vehicles or hazards.",
                    "execution": "Stay within low ceiling bounds.",
                },
            )
            assert res.status_code == 201, res.text
            data = res.json()["data"]
            assert data["status"] == "translated"
            assert data["pending_hitl_decision_id"] is None
            assert len(data["commands"]) == 1
            cmd = data["commands"][0]
            assert cmd["mission_type"] == "corridor_survey"
            assert cmd["target_area"] == {"type": "RelativeCorridor", "coordinates": []}
            assert cmd["lead_scout_drone_id"] == "drone-1"
            assert cmd["staging_hold_drone_ids"] == ["drone-2", "drone-3"]
            assert cmd["survey_params"]["target_distance_m"] == 20.0
            assert cmd["survey_params"]["distance_defaulted"] is True
            assert cmd["survey_params"]["return_to_origin"] is True
            # Omitted altitude_m clamped to clamp(2.5, 1.2, 2.0) == 2.0
            assert cmd["altitude_m"] == pytest.approx(2.0)
            assert cmd["survey_id"] is not None

            # Verify GET order status also surfaces corridor metadata
            status_res = await client.get(
                f"/api/v1/swarms/{swarm_id}/orders/{data['order_id']}",
                headers=headers,
            )
            assert status_res.status_code == 200
            status_cmd = status_res.json()["data"]["commands"][0]
            assert status_cmd["survey_id"] == cmd["survey_id"]
            assert status_cmd["lead_scout_drone_id"] == "drone-1"
            assert status_cmd["staging_hold_drone_ids"] == ["drone-2", "drone-3"]
            assert status_cmd["survey_params"]["target_distance_m"] == 20.0

        # Confirm CorridorSurvey & SwarmCommand rows persisted
        surveys = (await sqlite_db_session.execute(select(CorridorSurvey))).scalars().all()
        assert len(surveys) == 1
        assert surveys[0].requested_distance_m == 20.0
        assert surveys[0].distance_defaulted is True
        assert surveys[0].lead_scout_drone_id == "drone-1"
        assert surveys[0].staging_hold_drone_ids == ["drone-2", "drone-3"]

        db_cmd = (await sqlite_db_session.execute(select(SwarmCommand))).scalar_one()
        assert db_cmd.mission_type == MissionType.CORRIDOR_SURVEY
        assert db_cmd.survey_params is not None
        assert json.loads(db_cmd.survey_params)["target_distance_m"] == 20.0

        # Confirm workflow payload includes entry_altitude_m and staging_hold_drone_ids
        assert len(captured_workflows) == 1
        assert captured_workflows[0].commands[0]["staging_hold_drone_ids"] == ["drone-2", "drone-3"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_us1_validation_rejects_non_positive_distance_and_out_of_bounds_altitude_accepts_large_distance(
    sqlite_db_session,
    in_memory_memgraph_client,
    local_minio_store: MinioStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """T010 [US1]: Rejects <= 0 distance & explicit out-of-envelope altitude_m (422), accepts unbounded positive distance."""
    monkeypatch.setattr(operation_facade, "start_workflow", lambda *a, **kw: "ok")

    async def _noop_wf(*a, **kw):
        return "wf-id"

    monkeypatch.setattr(operation_facade, "start_workflow", _noop_wf)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    swarm_id = uuid.uuid4()
    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_id,
            name="Validation Swarm",
            project_id="default-theater",
            endpoint_url="http://127.0.0.1:18090",
            status=SwarmStatus.READY.value,
            drone_count=2,
            created_by="commander-1",
        )
    )
    await sqlite_db_session.commit()

    _install_db_override(sqlite_db_session)
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.minio_store = local_minio_store

    tok = await issue_jit_credential(
        agent_name="commander-1",
        scopes=["smeac:create", "smeac:read"],
        lifetime_seconds=3600,
    )
    headers = {"Authorization": f"Bearer {tok['token']}"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Non-positive distance -> 422
            async def _zero_dist(**kwargs):
                return SmeacParseResult(
                    commands=[
                        SwarmCommandDTO(
                            mission_type="corridor_survey",
                            formation_type="line",
                            target_area=GeoJsonTargetArea(type="RelativeCorridor", coordinates=[]),
                            drone_count=2,
                            survey_params={"target_distance_m": 0.0, "corridor_descriptor": "corridor"},
                        )
                    ],
                    reasoning="Zero distance test.",
                )

            monkeypatch.setattr(smeac_agents, "parse_smeac_order", _zero_dist)
            r_zero = await client.post(
                f"/api/v1/swarms/{swarm_id}/orders",
                headers=headers,
                json={"project_id": "default-theater", "situation": "S", "mission": "Check 0m", "execution": "E"},
            )
            assert r_zero.status_code == 422

            # 2. Explicit out-of-envelope altitude -> 422
            async def _bad_alt(**kwargs):
                return SmeacParseResult(
                    commands=[
                        SwarmCommandDTO(
                            mission_type="corridor_survey",
                            formation_type="line",
                            target_area=GeoJsonTargetArea(type="RelativeCorridor", coordinates=[]),
                            drone_count=2,
                            altitude_m=15.0,
                            survey_params={
                                "target_distance_m": 25.0,
                                "corridor_descriptor": "corridor",
                                "min_altitude_m": 1.2,
                                "max_altitude_m": 8.0,
                            },
                        )
                    ],
                    reasoning="Out-of-envelope altitude test.",
                )

            monkeypatch.setattr(smeac_agents, "parse_smeac_order", _bad_alt)
            r_alt = await client.post(
                f"/api/v1/swarms/{swarm_id}/orders",
                headers=headers,
                json={"project_id": "default-theater", "situation": "S", "mission": "Check at 15m", "execution": "E"},
            )
            assert r_alt.status_code == 422
            assert (await sqlite_db_session.execute(select(CorridorSurvey))).scalars().all() == []

            # 3. Large positive distance (250m) accepted without upper cap
            async def _long_dist(**kwargs):
                return SmeacParseResult(
                    commands=[
                        SwarmCommandDTO(
                            mission_type="corridor_survey",
                            formation_type="line",
                            target_area=GeoJsonTargetArea(type="RelativeCorridor", coordinates=[]),
                            drone_count=2,
                            altitude_m=3.0,
                            survey_params={
                                "target_distance_m": 250.0,
                                "corridor_descriptor": "deep transit tunnel",
                                "min_altitude_m": 1.2,
                                "max_altitude_m": 8.0,
                            },
                        )
                    ],
                    reasoning="Long 250m endurance-bounded corridor survey.",
                )

            monkeypatch.setattr(smeac_agents, "parse_smeac_order", _long_dist)
            r_long = await client.post(
                f"/api/v1/swarms/{swarm_id}/orders",
                headers=headers,
                json={"project_id": "default-theater", "situation": "S", "mission": "Check 250m", "execution": "E"},
            )
            assert r_long.status_code == 201
            assert r_long.json()["data"]["commands"][0]["survey_params"]["target_distance_m"] == 250.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_us1_temporal_replay_reload_and_edge_corridor_dispatch(
    sqlite_db_session,
    monkeypatch: pytest.MonkeyPatch,
):
    """T010/T016 [US1]: parse_smeac_activity reloads CorridorSurvey metadata on empty commands and dispatch posts /corridor-survey/start."""
    from src.uservice.smeac.models.storage.smeac import SmeacOrder

    swarm_id = uuid.uuid4()
    order_id = uuid.uuid4()
    cmd_id = uuid.uuid4()
    survey_id = uuid.uuid4()

    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_id,
            name="Dispatch Swarm",
            project_id="default-theater",
            endpoint_url="http://127.0.0.1:18090",
            status=SwarmStatus.READY.value,
            drone_count=3,
            created_by="commander-1",
        )
    )
    sqlite_db_session.add(
        SmeacOrder(
            id=order_id,
            project_id="default-theater",
            commander_id="commander-1",
            swarm_instance_id=swarm_id,
            situation="Tunnel",
            mission="Survey 20m",
            execution="Single scout",
            status="translated",
        )
    )
    params_payload = {
        "target_distance_m": 20.0,
        "distance_defaulted": False,
        "return_to_origin": True,
        "corridor_descriptor": "tunnel",
        "intelligence_focus": ["vehicle"],
        "min_altitude_m": 1.2,
        "max_altitude_m": 6.0,
        "cruise_speed_ms": 1.5,
    }
    sqlite_db_session.add(
        SwarmCommand(
            id=cmd_id,
            smeac_order_id=order_id,
            mission_type=MissionType.CORRIDOR_SURVEY,
            formation_type="line",
            target_area=json.dumps({"type": "RelativeCorridor", "coordinates": []}),
            target_object_class="vehicle",
            drone_count=3,
            altitude_m=2.5,
            is_high_impact=False,
            survey_params=json.dumps(params_payload),
        )
    )
    sqlite_db_session.add(
        CorridorSurvey(
            id=survey_id,
            project_id="default-theater",
            swarm_instance_id=swarm_id,
            smeac_order_id=order_id,
            command_id=cmd_id,
            lead_scout_drone_id="drone-1",
            staging_hold_drone_ids=["drone-2", "drone-3"],
            corridor_descriptor="tunnel",
            requested_distance_m=20.0,
            distance_defaulted=False,
            return_to_origin=True,
            min_altitude_m=1.2,
            max_altitude_m=6.0,
            intelligence_focus=["vehicle"],
        )
    )
    await sqlite_db_session.commit()

    class _SessionCtx:
        async def __aenter__(self):
            return sqlite_db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    import src.uservice.database.engine as db_engine

    monkeypatch.setattr(db_engine, "async_session", lambda: _SessionCtx())

    # 1. Replay DB reload path (commands=[])
    reloaded = await parse_smeac_activity(
        ProcessSmeacInput(
            order_id=str(order_id),
            commander_id="commander-1",
            swarm_instance_id=str(swarm_id),
            situation="Tunnel",
            mission="Survey 20m",
            execution="Single scout",
            project_id="default-theater",
            commands=[],
        )
    )
    assert len(reloaded["commands"]) == 1
    rcmd = reloaded["commands"][0]
    assert rcmd["survey_id"] == str(survey_id)
    assert rcmd["lead_scout_drone_id"] == "drone-1"
    assert rcmd["staging_hold_drone_ids"] == ["drone-2", "drone-3"]
    assert rcmd["survey_params"]["target_distance_m"] == 20.0

    # 2. Dispatch activity -> calls /corridor-survey/start only (not /navigate or /target)
    posted: list[tuple[str, dict]] = []

    class _FakeHttpClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url: str, json: dict):
            posted.append((url, json))
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"status": "accepted"},
            )

    monkeypatch.setattr(httpx, "AsyncClient", _FakeHttpClient)

    res = await dispatch_edge_mission_activity(
        {
            "order_id": str(order_id),
            "swarm_instance_id": str(swarm_id),
            "project_id": "default-theater",
            "endpoint_url": "http://127.0.0.1:18090",
            "commands": reloaded["commands"],
        }
    )
    assert res["status"] == "executed"
    assert len(posted) == 1
    url, body = posted[0]
    assert url == "http://127.0.0.1:18090/corridor-survey/start"
    assert body["survey_id"] == str(survey_id)
    assert body["drone_id"] == "drone-1"
    assert body["staging_hold_drone_ids"] == ["drone-2", "drone-3"]
    assert body["entry_altitude_m"] == 2.5
    assert body["target_distance_m"] == 20.0


@pytest.mark.asyncio
async def test_us4_ingestor_materializes_full_snapshots_and_serves_secure_bff_api(
    sqlite_db_session,
    in_memory_memgraph_client,
    in_memory_mqtt_bus,
    local_minio_store: MinioStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """T032 [US4]: TelemetryIngestor materializes all snapshots/decisions/findings into C2 API, enforces RBAC/IDOR & BFF headers, and logs AuditEvents."""
    from src.edge.telemetry.publisher import build_corridor_snapshot_key
    from src.uservice.operation.audit import ActorType, AuditEvent
    from src.uservice.smeac.models.storage.smeac import SmeacOrder
    from src.uservice.telemetry.models.contract.events import (
        CorridorPhasePayload,
        CorridorReportPayload,
        CorridorSnapshotPayload,
        CorridorTrajectoryPayload,
        SwarmTelemetryEvent,
        build_telemetry_topic,
    )
    from src.uservice.telemetry.operations.compactor import ParquetCompactor
    from src.uservice.telemetry.operations.ingestor import TelemetryIngestor
    from src.uservice.telemetry.models.storage.live_state import LiveTelemetryStore

    swarm_id = uuid.uuid4()
    other_swarm_id = uuid.uuid4()
    order_id = uuid.uuid4()
    cmd_id = uuid.uuid4()
    survey_id = uuid.uuid4()

    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_id,
            name="C2 Report Swarm",
            project_id="default-theater",
            endpoint_url="http://127.0.0.1:18090",
            status=SwarmStatus.READY.value,
            drone_count=3,
            created_by="commander-1",
        )
    )
    sqlite_db_session.add(
        SwarmInstance(
            id=other_swarm_id,
            name="Other Swarm",
            project_id="default-theater",
            endpoint_url="http://127.0.0.1:18091",
            status=SwarmStatus.READY.value,
            drone_count=1,
            created_by="commander-1",
        )
    )
    sqlite_db_session.add(
        SmeacOrder(
            id=order_id,
            project_id="default-theater",
            commander_id="commander-1",
            swarm_instance_id=swarm_id,
            situation="Corridor",
            mission="Check 20m",
            execution="Single scout",
            status="executed",
        )
    )
    sqlite_db_session.add(
        CorridorSurvey(
            id=survey_id,
            project_id="default-theater",
            swarm_instance_id=swarm_id,
            smeac_order_id=order_id,
            command_id=cmd_id,
            lead_scout_drone_id="drone-1",
            staging_hold_drone_ids=["drone-2", "drone-3"],
            corridor_descriptor="maintenance corridor",
            requested_distance_m=20.0,
            distance_defaulted=False,
            return_to_origin=True,
            min_altitude_m=1.2,
            max_altitude_m=8.0,
            intelligence_focus=["vehicle"],
        )
    )
    await sqlite_db_session.commit()
    await local_minio_store.ensure_buckets()

    class _SessionCtx:
        async def __aenter__(self):
            return sqlite_db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    from src.uservice.corridor.operations.survey_service import ingest_corridor_event

    async def _corridor_cb(event):
        await ingest_corridor_event(sqlite_db_session, event)
        await sqlite_db_session.commit()

    compactor = ParquetCompactor(minio_store=local_minio_store, flush_interval_s=10.0)
    ingestor = TelemetryIngestor(
        live_store=LiveTelemetryStore(),
        compactor=compactor,
        db_session_factory=lambda: _SessionCtx(),
        corridor_survey_callback=_corridor_cb,
    )

    # Upload 3 valid JPEG snapshots & publish corridor events across initial_look_around, outbound, and returning (`FR-020`)
    snap_ids = [uuid.uuid4() for _ in range(3)]
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"CORRIDOR_FRAME" * 8
    topic = build_telemetry_topic("default-theater", str(swarm_id), "drone-1", "alert")
    for idx, snap_id in enumerate(snap_ids, start=1):
        key = build_corridor_snapshot_key(
            "default-theater", str(swarm_id), str(survey_id), "drone-1", str(snap_id)
        )
        await local_minio_store.put_object(local_minio_store.SNAPSHOT_BUCKET, key, jpeg_bytes, content_type="image/jpeg")
        phase = ("initial_look_around", "outbound_discovery", "returning")[idx - 1]
        payload = CorridorSnapshotPayload(
            survey_id=str(survey_id),
            snapshot_id=str(snap_id),
            sequence_num=idx,
            phase=phase,
            rel_x_m=float(idx * 4.0),
            rel_y_m=0.0,
            rel_z_m=2.3,
            cumulative_distance_m=float(idx * 5.0),
            visual_confidence=0.92,
            corridor_open=True,
            estimated_width_m=3.2,
            estimated_height_m=2.7,
            analysis_latency_ms=32.0,
            byte_size=len(jpeg_bytes),
            structural_tags=["curve_right"] if idx == 2 else [],
            findings=[
                {
                    "finding_id": str(uuid.uuid4()),
                    "finding_type": "target_interest",
                    "label": "vehicle",
                    "confidence": 0.91,
                    "matches_mission_interest": True,
                    "rel_x_m": 8.0,
                    "rel_y_m": 0.0,
                    "rel_z_m": 2.3,
                    "heading_deg": 90.0,
                    "cumulative_distance_m": 10.0,
                }
            ]
            if idx == 2
            else [],
        )
        evt = SwarmTelemetryEvent(
            project_id="default-theater",
            swarm_id=str(swarm_id),
            drone_id="drone-1",
            metric_type="alert",
            lat=47.39775,
            lon=8.54561,
            alt_m=502.3,
            heading_deg=90.0,
            flight_status=f"survey_{phase}",
            snapshot_uri=f"s3://{local_minio_store.SNAPSHOT_BUCKET}/{key}",
            extra=payload.model_dump(mode="json"),
        )
        assert await ingestor.handle_raw_message(topic, evt.model_dump_json()) is True

    dec_id = uuid.uuid4()
    traj_evt = SwarmTelemetryEvent(
        project_id="default-theater",
        swarm_id=str(swarm_id),
        drone_id="drone-1",
        metric_type="alert",
        lat=47.39775,
        lon=8.54561,
        alt_m=502.3,
        heading_deg=90.0,
        flight_status="survey_outbound_discovery",
        extra=CorridorTrajectoryPayload(
            survey_id=str(survey_id),
            decision_id=str(dec_id),
            sequence_num=1,
            action="trajectory_update",
            from_phase="initial_look_around",
            to_phase="outbound_discovery",
            target_rel_x_m=4.0,
            target_rel_y_m=0.0,
            target_rel_z_m=2.3,
            commanded_heading_deg=90.0,
            cleared_distance_m=4.0,
            speed_ms=1.5,
            trigger_snapshot_ids=[str(snap_ids[0])],
            analysis_latency_ms=32.0,
            rationale="East opening cleared.",
            breadcrumb={
                "index": 1,
                "rel_x_m": 0.0,
                "rel_y_m": 0.0,
                "rel_z_m": 2.5,
                "heading_deg": 90.0,
                "cumulative_distance_m": 0.0,
                "estimated_width_m": 3.2,
                "estimated_height_m": 2.7,
                "snapshot_id": str(snap_ids[0]),
            },
        ).model_dump(mode="json"),
    )
    assert await ingestor.handle_raw_message(topic, traj_evt.model_dump_json()) is True

    rep_evt = SwarmTelemetryEvent(
        project_id="default-theater",
        swarm_id=str(swarm_id),
        drone_id="drone-1",
        metric_type="alert",
        lat=47.39775,
        lon=8.54561,
        alt_m=502.5,
        heading_deg=90.0,
        flight_status="survey_completed",
        extra=CorridorReportPayload(
            survey_id=str(survey_id),
            status="completed",
            completion_reason="distance_reached",
            surveyed_distance_m=20.0,
            requested_distance_m=20.0,
            discovered_path=[
                {
                    "index": 1,
                    "rel_x_m": 0.0,
                    "rel_y_m": 0.0,
                    "rel_z_m": 2.5,
                    "heading_deg": 90.0,
                    "cumulative_distance_m": 0.0,
                    "snapshot_id": str(snap_ids[0]),
                }
            ],
            structural_features=["curve_right"],
            unexplored_branches=[],
            snapshot_count=3,
            decision_count=1,
            finding_count=1,
        ).model_dump(mode="json"),
    )
    assert await ingestor.handle_raw_message(topic, rep_evt.model_dump_json()) is True

    _install_db_override(sqlite_db_session)
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.minio_store = local_minio_store

    read_only_tok = await issue_jit_credential("observer", ["swarm:read"], lifetime_seconds=3600)
    full_tok = await issue_jit_credential("commander-1", ["swarm:read", "smeac:create"], lifetime_seconds=3600)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # 1. Missing JWT -> 401
            unauth = await client.get(f"/api/v1/swarms/{swarm_id}/corridor-surveys")
            assert unauth.status_code == 401

            # 2. List & Full CorridorIntelligenceReport (`swarm:read`)
            list_res = await client.get(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys",
                headers={"Authorization": f"Bearer {read_only_tok['token']}"},
            )
            assert list_res.status_code == 200
            assert len(list_res.json()["data"]) == 1
            assert list_res.json()["data"][0]["snapshot_count"] == 3

            rep_res = await client.get(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}",
                headers={"Authorization": f"Bearer {read_only_tok['token']}"},
            )
            assert rep_res.status_code == 200
            report = rep_res.json()["data"]
            assert len(report["snapshots"]) == 3
            assert len(report["decisions"]) == 1
            assert len(report["findings"]) == 1
            assert report["completion_reason"] == "distance_reached"

            # 3. Authenticated BFF snapshot proxy with nosniff & private, no-store headers
            img_res = await client.get(
                report["snapshots"][0]["image_proxy_url"],
                headers={"Authorization": f"Bearer {read_only_tok['token']}"},
            )
            assert img_res.status_code == 200
            assert img_res.headers.get("x-content-type-options") == "nosniff"
            assert img_res.headers.get("cache-control") == "private, no-store"
            assert img_res.content.startswith(b"\xff\xd8\xff")

            # 4. Cross-swarm & cross-project IDOR -> 404
            idor_res = await client.get(
                f"/api/v1/swarms/{other_swarm_id}/corridor-surveys/{survey_id}",
                headers={"Authorization": f"Bearer {full_tok['token']}"},
            )
            assert idor_res.status_code == 404

            idor_proj_res = await client.get(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/snapshots/{snap_ids[0]}/image?project_id=other-theater",
                headers={"Authorization": f"Bearer {full_tok['token']}"},
            )
            assert idor_proj_res.status_code == 404

            # 5. RBAC: read-only scope rejected on POST recall & emergency-abort -> 403
            forbidden_res = await client.post(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/recall",
                headers={"Authorization": f"Bearer {read_only_tok['token']}"},
                json={"rationale": "Unauthorized recall"},
            )
            assert forbidden_res.status_code == 403

            # 6. Commander Recall & Emergency Abort forward to edge & write ActorType.COMMANDER AuditEvent
            forwarded: list[str] = []

            class _FakeEdgeClient:
                def __init__(self, *a, **kw):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def post(self, url: str, json: dict):
                    forwarded.append(url)
                    return httpx.Response(200, request=httpx.Request("POST", url), json={"status": "ok"})

            monkeypatch.setattr(httpx, "AsyncClient", _FakeEdgeClient)
            rec_res = await client.post(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/recall",
                headers={"Authorization": f"Bearer {full_tok['token']}"},
                json={"rationale": "Return immediately"},
            )
            assert rec_res.status_code == 200
            assert rec_res.json()["data"]["override_type"] == "recall"
            assert forwarded[-1] == f"http://127.0.0.1:18090/corridor-survey/{survey_id}/recall"

            abort_res = await client.post(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/emergency-abort",
                headers={"Authorization": f"Bearer {full_tok['token']}"},
                json={"rationale": "Immediate hold"},
            )
            assert abort_res.status_code == 200
            assert abort_res.json()["data"]["override_type"] == "emergency_abort"
            assert abort_res.json()["data"]["phase"] == "emergency_hold"
            assert forwarded[-1] == f"http://127.0.0.1:18090/corridor-survey/{survey_id}/emergency-abort"

            audits = (await sqlite_db_session.execute(select(AuditEvent))).scalars().all()
            assert any(a.actor_type == ActorType.AGENT for a in audits)
            assert any(
                a.actor_type == ActorType.COMMANDER and a.details.get("override_type") == "recall"
                for a in audits
            )
            assert any(
                a.actor_type == ActorType.COMMANDER and a.details.get("override_type") == "emergency_abort"
                for a in audits
            )

            # 7. Cross-swarm / cross-project ingest isolation, invalid snapshot_uri drop, and terminal-phase replay guard
            cross_evt = SwarmTelemetryEvent(
                project_id="rogue-theater",
                swarm_id=str(other_swarm_id),
                drone_id="drone-1",
                metric_type="alert",
                lat=47.39775,
                lon=8.54561,
                alt_m=502.3,
                heading_deg=0.0,
                flight_status="survey_outbound_discovery",
                extra=CorridorPhasePayload(
                    survey_id=str(survey_id),
                    from_phase="initial_look_around",
                    to_phase="outbound_discovery",
                    flight_status="survey_outbound_discovery",
                    reason="cross-tenant spoof attempt",
                    rel_x_m=0.0,
                    rel_y_m=0.0,
                    rel_z_m=2.0,
                    heading_deg=0.0,
                    cumulative_distance_m=0.0,
                ).model_dump(mode="json"),
            )
            assert await ingest_corridor_event(sqlite_db_session, cross_evt) is False

            bad_uri_evt = SwarmTelemetryEvent(
                project_id="default-theater",
                swarm_id=str(swarm_id),
                drone_id="drone-1",
                metric_type="alert",
                lat=47.39775,
                lon=8.54561,
                alt_m=502.3,
                heading_deg=0.0,
                flight_status="survey_outbound_discovery",
                snapshot_uri="s3://tactical-snapshots/../../etc/passwd",
                extra=CorridorSnapshotPayload(
                    survey_id=str(survey_id),
                    snapshot_id=str(uuid.uuid4()),
                    sequence_num=99,
                    phase="outbound_discovery",
                    rel_x_m=1.0,
                    rel_y_m=0.0,
                    rel_z_m=2.0,
                    cumulative_distance_m=1.0,
                    visual_confidence=0.9,
                    corridor_open=True,
                    analysis_latency_ms=10.0,
                    byte_size=128,
                ).model_dump(mode="json"),
            )
            await ingest_corridor_event(sqlite_db_session, bad_uri_evt)
            after_bad = await sqlite_db_session.get(CorridorSurvey, survey_id)
            assert after_bad is not None
            assert after_bad.phase == "emergency_hold"

            replay_phase_evt = SwarmTelemetryEvent(
                project_id="default-theater",
                swarm_id=str(swarm_id),
                drone_id="drone-1",
                metric_type="alert",
                lat=47.39775,
                lon=8.54561,
                alt_m=502.3,
                heading_deg=90.0,
                flight_status="survey_outbound_discovery",
                replayed=True,
                extra=CorridorPhasePayload(
                    survey_id=str(survey_id),
                    from_phase="initial_look_around",
                    to_phase="outbound_discovery",
                    flight_status="survey_outbound_discovery",
                    reason="DDIL replay must not revert emergency_hold",
                    rel_x_m=4.0,
                    rel_y_m=0.0,
                    rel_z_m=2.3,
                    heading_deg=90.0,
                    cumulative_distance_m=4.0,
                ).model_dump(mode="json"),
            )
            assert await ingest_corridor_event(sqlite_db_session, replay_phase_evt) is True
            after_replay = await sqlite_db_session.get(CorridorSurvey, survey_id)
            assert after_replay is not None
            assert after_replay.phase == "emergency_hold"
            assert after_replay.status == "aborted"

            # 8. Unreachable edge endpoint returns clean 502 instead of 500
            class _FailingEdgeClient:
                def __init__(self, *a, **kw):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def post(self, url: str, json: dict):
                    raise httpx.ConnectError("edge unreachable", request=httpx.Request("POST", url))

            monkeypatch.setattr(httpx, "AsyncClient", _FailingEdgeClient)
            bad_edge_res = await client.post(
                f"/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/recall",
                headers={"Authorization": f"Bearer {full_tok['token']}"},
                json={"rationale": "Edge offline check"},
            )
            assert bad_edge_res.status_code == 502
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_smeac_order_idor_and_swarm_ownership(
    sqlite_db_session,
    in_memory_memgraph_client,
    local_minio_store: MinioStore,
    monkeypatch: pytest.MonkeyPatch,
):
    """T046/Review Hardening: Rejects missing/cross-project swarms on POST /orders (404) and cross-swarm GET /orders/{id} (404)."""
    from src.uservice.smeac.models.storage.smeac import SmeacOrder

    async def _noop_wf(*a, **kw):
        return "wf-idor"

    async def _stub_parse(**kwargs):
        return SmeacParseResult(
            commands=[
                SwarmCommandDTO(
                    mission_type="corridor_survey",
                    formation_type="line",
                    target_area=GeoJsonTargetArea(type="RelativeCorridor", coordinates=[]),
                    drone_count=2,
                    survey_params={"target_distance_m": 20.0, "corridor_descriptor": "corridor"},
                )
            ],
            reasoning="IDOR check order.",
        )

    monkeypatch.setattr(operation_facade, "start_workflow", _noop_wf)
    monkeypatch.setattr(smeac_agents, "parse_smeac_order", _stub_parse)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    swarm_a = uuid.uuid4()
    swarm_b = uuid.uuid4()
    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_a,
            name="Swarm A",
            project_id="theater-alpha",
            endpoint_url="http://127.0.0.1:18090",
            status=SwarmStatus.READY.value,
            drone_count=2,
            created_by="commander-1",
        )
    )
    sqlite_db_session.add(
        SwarmInstance(
            id=swarm_b,
            name="Swarm B",
            project_id="theater-beta",
            endpoint_url="http://127.0.0.1:18091",
            status=SwarmStatus.READY.value,
            drone_count=2,
            created_by="commander-1",
        )
    )
    await sqlite_db_session.commit()

    _install_db_override(sqlite_db_session)
    app.state.memgraph_client = in_memory_memgraph_client
    app.state.minio_store = local_minio_store

    tok = await issue_jit_credential(
        agent_name="commander-1",
        scopes=["smeac:create", "smeac:read"],
        lifetime_seconds=3600,
    )
    headers = {"Authorization": f"Bearer {tok['token']}"}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Missing swarm -> 404 without creating order
            miss_res = await client.post(
                f"/api/v1/swarms/{uuid.uuid4()}/orders",
                headers=headers,
                json={"project_id": "theater-alpha", "situation": "S", "mission": "M", "execution": "E"},
            )
            assert miss_res.status_code == 404

            # Cross-project swarm -> 404 without creating order
            cross_proj = await client.post(
                f"/api/v1/swarms/{swarm_a}/orders",
                headers=headers,
                json={"project_id": "theater-beta", "situation": "S", "mission": "M", "execution": "E"},
            )
            assert cross_proj.status_code == 404
            assert (await sqlite_db_session.execute(select(SmeacOrder))).scalars().all() == []

            # Valid order on swarm_a cannot be queried via swarm_b (cross-swarm IDOR -> 404)
            ok_post = await client.post(
                f"/api/v1/swarms/{swarm_a}/orders",
                headers=headers,
                json={"project_id": "theater-alpha", "situation": "S", "mission": "Check corridor", "execution": "E"},
            )
            assert ok_post.status_code == 201
            order_id = ok_post.json()["data"]["order_id"]

            cross_get = await client.get(
                f"/api/v1/swarms/{swarm_b}/orders/{order_id}",
                headers=headers,
            )
            assert cross_get.status_code == 404
    finally:
        app.dependency_overrides.clear()


