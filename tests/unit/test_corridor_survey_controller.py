"""Hermetic unit tests for CorridorSurveyController and edge corridor HTTP endpoints."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import uuid

import httpx
import pytest

from src.edge.api import server as edge_server
from src.edge.navigation.corridor_survey import CorridorSurveyController, CorridorSurveyConfig, SurveyPhase
from src.edge.vision.corridor_analyzer import CorridorBranchCandidate, CorridorFrameAnalysis


class _RecordingPublisher:
    def __init__(self, swarm_id: str) -> None:
        self.project_id = "default-theater"
        self.swarm_id = swarm_id
        self.drone_id = "drone-1"
        self.snapshots: list[dict] = []
        self.events: list[dict] = []

    async def publish_corridor_snapshot(self, **kwargs):
        snap_id = kwargs.get("snapshot_id") or str(uuid.uuid4())
        rec = {**kwargs, "snapshot_id": snap_id}
        self.snapshots.append(rec)
        return SimpleNamespace(event_id=str(uuid.uuid4()), extra={"snapshot_id": snap_id})

    async def publish_corridor_event(self, **kwargs):
        self.events.append(kwargs)
        return SimpleNamespace(event_id=str(uuid.uuid4()), **kwargs)

    async def publish_event(self, event, snapshot_local_path=None):
        self.events.append({"raw_event": event})
        return True


class _StubCamera:
    def __init__(self, frame_factory) -> None:
        self._frame_factory = frame_factory
        self._capture = SimpleNamespace(isOpened=lambda: True)

    def open(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def read_frame(self):
        return self._frame_factory()


class _FakeAction:
    def __init__(self, owner: "_FakeDrone") -> None:
        self._owner = owner
        self.hold_calls = 0
        self.takeoff_altitudes: list[float] = []
        self.goto_calls: list[tuple[float, float, float, float]] = []

    async def arm(self) -> None:
        self._owner.armed = True

    async def set_takeoff_altitude(self, alt_m: float) -> None:
        self.takeoff_altitudes.append(alt_m)

    async def takeoff(self) -> None:
        self._owner.in_air = True
        self._owner.rel_alt = self.takeoff_altitudes[-1] if self.takeoff_altitudes else 2.5

    async def goto_location(self, lat: float, lon: float, abs_alt_m: float, yaw_deg: float) -> None:
        self.goto_calls.append((lat, lon, abs_alt_m, yaw_deg))
        self._owner.lat = lat
        self._owner.lon = lon
        self._owner.abs_alt = abs_alt_m
        self._owner.rel_alt = abs_alt_m - self._owner.ground_alt_m
        self._owner.heading_deg = float(yaw_deg) % 360.0

    async def hold(self) -> None:
        self.hold_calls += 1


class _FakeDrone:
    def __init__(self, ground_alt_m: float = 500.0) -> None:
        self.lat = 47.39775
        self.lon = 8.54560
        self.ground_alt_m = ground_alt_m
        self.rel_alt = 0.0
        self.abs_alt = ground_alt_m
        self.heading_deg = 0.0
        self.battery_pct = 96.0
        self.armed = False
        self.in_air = False
        self.action = _FakeAction(self)


def _dummy_jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + (b"\x00" * 64)


class _HeadingScriptAnalyzer:
    def __init__(self, open_headings: set[int]) -> None:
        self.open_headings = open_headings
        self.get_heading = lambda: 0.0

    def analyze_frame(self, frame, intelligence_focus=None) -> CorridorFrameAnalysis:
        h = int(round(self.get_heading())) % 360
        closest = min(range(0, 360, 45), key=lambda k: min(abs(h - k), 360 - abs(h - k)))
        is_open = closest in self.open_headings
        branch = (
            CorridorBranchCandidate(
                azimuth_offset_deg=0.0,
                elevation_offset_m=0.0,
                openness_score=0.92,
                estimated_width_m=3.4,
                estimated_height_m=2.8,
            )
            if is_open
            else None
        )
        return CorridorFrameAnalysis(
            visual_confidence=0.95,
            blur_score=180.0,
            brightness_score=140.0,
            is_frozen=False,
            corridor_open=is_open,
            is_dead_end=not is_open,
            primary_branch=branch,
            secondary_branches=[],
            structural_tags=[] if is_open else ["dead_end"],
            target_findings=[],
            hazards=[],
            analysis_latency_ms=12.0,
        )


@pytest.mark.asyncio
async def test_us1_initial_360_sweep_holds_at_origin_and_clears_east_opening():
    """T012 [US1]: Performs 8-heading 360° yaw sweep at origin with zero horizontal advance before validation (`SC-002`)."""
    swarm_id = str(uuid.uuid4())
    survey_id = str(uuid.uuid4())
    drone = _FakeDrone()
    pub = _RecordingPublisher(swarm_id=swarm_id)
    analyzer = _HeadingScriptAnalyzer(open_headings={90})
    analyzer.get_heading = lambda: drone.heading_deg
    cam = _StubCamera(lambda: _dummy_jpeg())

    config = CorridorSurveyConfig(
        survey_id=survey_id,
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        project_id="default-theater",
        drone_id="drone-1",
        entry_altitude_m=2.5,
        target_distance_m=20.0,
        snapshot_interval_s=0.01,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl = CorridorSurveyController(
        config=config,
        camera=cam,
        analyzer=analyzer,
        drone=drone,
        telemetry_publisher=pub,
    )
    ok, instr = await ctrl.run_initial_look_around()
    assert ok is True
    assert instr is not None
    assert instr.commanded_heading_deg == pytest.approx(90.0)
    assert instr.target_rel_z_m == pytest.approx(2.5)
    assert len(instr.trigger_snapshot_ids) == 1

    # All 8 headings captured while hovering at origin (rel_x=0, rel_y=0)
    assert len(pub.snapshots) == 8
    for snap in pub.snapshots:
        assert snap["phase"] == "initial_look_around"
        assert snap["rel_x_m"] == pytest.approx(0.0)
        assert snap["rel_y_m"] == pytest.approx(0.0)
        assert snap["rel_z_m"] == pytest.approx(2.5)
    assert [int(round(s["heading_deg"])) for s in pub.snapshots] == [0, 45, 90, 135, 180, 225, 270, 315]

    # Telemetry events reflect canonical survey_initial_look_around -> survey_outbound_discovery
    phase_events = [e for e in pub.events if e.get("survey_event_type") == "corridor_phase"]
    assert any(e["flight_status"] == "survey_initial_look_around" for e in phase_events)
    assert phase_events[-1]["flight_status"] == "survey_outbound_discovery"


@pytest.mark.asyncio
async def test_us1_enclosed_start_triggers_impassable_start_hold():
    """T012 [US1]: Enclosed start across all 8 headings transitions to impassable_start and holds safely at origin."""
    swarm_id = str(uuid.uuid4())
    survey_id = str(uuid.uuid4())
    drone = _FakeDrone()
    pub = _RecordingPublisher(swarm_id=swarm_id)
    analyzer = _HeadingScriptAnalyzer(open_headings=set())
    analyzer.get_heading = lambda: drone.heading_deg
    cam = _StubCamera(lambda: _dummy_jpeg())

    config = CorridorSurveyConfig(
        survey_id=survey_id,
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        project_id="default-theater",
        drone_id="drone-1",
        entry_altitude_m=2.2,
        target_distance_m=20.0,
        snapshot_interval_s=0.01,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl = CorridorSurveyController(
        config=config,
        camera=cam,
        analyzer=analyzer,
        drone=drone,
        telemetry_publisher=pub,
    )
    ok, instr = await ctrl.run_initial_look_around()
    assert ok is False
    assert instr is None
    assert ctrl.phase == SurveyPhase.IMPASSABLE_START
    assert ctrl.completion_reason == "impassable_start"
    assert drone.action.hold_calls >= 1
    phase_events = [e for e in pub.events if e.get("survey_event_type") == "corridor_phase"]
    assert phase_events[-1]["flight_status"] == "survey_impassable_start"


@pytest.mark.asyncio
async def test_us1_edge_server_staging_hold_cancellation_and_telemetry(monkeypatch: pytest.MonkeyPatch):
    """T012/T019 [US1]: Edge POST /corridor-survey/start cancels pre-existing tasks on staging drones and publishes survey_staging_hold."""
    swarm_id = str(uuid.uuid4())
    survey_id = str(uuid.uuid4())
    pub = _RecordingPublisher(swarm_id=swarm_id)
    fake_drone = _FakeDrone()
    fake_cam = _StubCamera(lambda: _dummy_jpeg())
    cancelled_flags = {"drone-2": False, "nav": False}

    async def _sleep_forever(key: str):
        try:
            await asyncio.sleep(60.0)
        except asyncio.CancelledError:
            cancelled_flags[key] = True
            raise

    old_nav = asyncio.create_task(_sleep_forever("nav"))
    old_v2 = asyncio.create_task(_sleep_forever("drone-2"))
    await asyncio.sleep(0)  # Let tasks enter try/await before cancellation

    monkeypatch.setattr(edge_server, "_telemetry_publisher", pub)
    monkeypatch.setattr(edge_server, "_drone", fake_drone)
    monkeypatch.setattr(edge_server, "_camera", fake_cam)
    monkeypatch.setattr(edge_server, "_inference", None)
    monkeypatch.setattr(edge_server, "_nav_task", old_nav)
    edge_server._vision_tasks.clear()
    edge_server._vision_tasks["drone-2"] = old_v2
    edge_server._corridor_controllers.clear()
    edge_server._corridor_tasks.clear()

    app = edge_server.create_edge_app()
    # Prevent actual background survey loop from requiring full analyzer timing during endpoint check
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        res = await client.post(
            "/corridor-survey/start",
            json={
                "survey_id": survey_id,
                "command_id": str(uuid.uuid4()),
                "swarm_id": swarm_id,
                "project_id": "default-theater",
                "drone_id": "drone-1",
                "staging_hold_drone_ids": ["drone-2", "drone-3"],
                "entry_altitude_m": 2.5,
                "target_distance_m": 20.0,
                "distance_defaulted": False,
                "return_to_origin": True,
                "corridor_descriptor": "corridor",
                "intelligence_focus": ["vehicle"],
                "min_altitude_m": 1.2,
                "max_altitude_m": 8.0,
                "cruise_speed_ms": 1.5,
                "look_around_steps": 8,
                "snapshot_interval_s": 0.4,
                "guidance_timeout_s": 5.0,
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "accepted"
        assert body["drone_id"] == "drone-1"
        assert body["staging_hold_drone_ids"] == ["drone-2", "drone-3"]

        await asyncio.sleep(0.05)
        assert cancelled_flags["nav"] is True
        assert cancelled_flags["drone-2"] is True

        staging_events = [
            e["raw_event"]
            for e in pub.events
            if "raw_event" in e and e["raw_event"].flight_status == "survey_staging_hold"
        ]
        assert {e.drone_id for e in staging_events} == {"drone-2", "drone-3"}

        status_res = await client.get(f"/corridor-survey/{survey_id}/status")
        assert status_res.status_code == 200
        assert status_res.json()["survey_id"] == survey_id

        telem_res = await client.get("/telemetry")
        assert telem_res.status_code == 200
        assert telem_res.json()["active_corridor_survey"]["survey_id"] == survey_id

    for t in list(edge_server._corridor_tasks.values()):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    edge_server._corridor_controllers.clear()
    edge_server._corridor_tasks.clear()


@pytest.mark.asyncio
async def test_us2_adaptive_3d_flight_overhang_clamping_fork_and_findings():
    """T021 [US2]: Rolls through turn + overhang within [min_altitude_m, max_altitude_m], logs fork & mission findings without HITL pause."""
    swarm_id = str(uuid.uuid4())
    survey_id = str(uuid.uuid4())
    drone = _FakeDrone()
    pub = _RecordingPublisher(swarm_id=swarm_id)

    class _AdaptiveAnalyzer:
        def __init__(self) -> None:
            self.calls = 0

        def reset_temporal_state(self) -> None:
            return None

        def analyze_frame(self, frame, intelligence_focus=None) -> CorridorFrameAnalysis:
            self.calls += 1
            if self.calls <= 8:
                is_open = int(round(drone.heading_deg)) % 360 == 0
                return CorridorFrameAnalysis(
                    visual_confidence=0.95,
                    blur_score=180.0,
                    brightness_score=130.0,
                    is_frozen=False,
                    corridor_open=is_open,
                    is_dead_end=not is_open,
                    primary_branch=CorridorBranchCandidate(0.0, 0.0, 0.9, 3.0, 3.0) if is_open else None,
                    analysis_latency_ms=15.0,
                )
            # Mid-flight: step 1 curves right + huge low overhang (-5.0 m request clamps to min_altitude_m=1.2m)
            # + fork branch + mission target finding (no HITL pause!)
            if self.calls == 9:
                return CorridorFrameAnalysis(
                    visual_confidence=0.92,
                    blur_score=175.0,
                    brightness_score=130.0,
                    is_frozen=False,
                    corridor_open=True,
                    is_dead_end=False,
                    primary_branch=CorridorBranchCandidate(25.0, -5.0, 0.88, 3.2, 2.0),
                    secondary_branches=[CorridorBranchCandidate(-55.0, 0.0, 0.72, 2.5, 2.8)],
                    structural_tags=["curve_right", "low_overhang", "intersection"],
                    target_findings=[{"label": "vehicle", "confidence": 0.91, "azimuth_offset_deg": 4.0}],
                    hazards=[],
                    analysis_latency_ms=22.0,
                )
            # Next steps continue straight within envelope
            return CorridorFrameAnalysis(
                visual_confidence=0.93,
                blur_score=175.0,
                brightness_score=130.0,
                is_frozen=False,
                corridor_open=True,
                is_dead_end=False,
                primary_branch=CorridorBranchCandidate(0.0, 0.5, 0.90, 3.2, 3.0),
                structural_tags=[],
                analysis_latency_ms=14.0,
            )

    analyzer = _AdaptiveAnalyzer()
    cam = _StubCamera(lambda: _dummy_jpeg())
    config = CorridorSurveyConfig(
        survey_id=survey_id,
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        drone_id="drone-1",
        entry_altitude_m=2.5,
        target_distance_m=6.0,
        min_altitude_m=1.2,
        max_altitude_m=2.6,
        segment_step_m=2.5,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl = CorridorSurveyController(
        config=config,
        camera=cam,
        analyzer=analyzer,
        drone=drone,
        telemetry_publisher=pub,
    )
    ok, _ = await ctrl.run_initial_look_around()
    assert ok is True

    while True:
        res = await ctrl.step_outbound()
        assert ctrl.rel_z_m >= 1.2 - 1e-6
        assert ctrl.rel_z_m <= 2.6 + 1e-6
        if res != "continue":
            break

    assert res == "distance_reached"
    assert ctrl.surveyed_distance_m == pytest.approx(6.0, rel=0.05)
    assert len(ctrl.unexplored_branches) == 1
    assert ctrl.finding_count >= 2  # 1 target_interest + 1 side_branch without HITL pause
    assert any(b.rel_z_m == pytest.approx(1.2) for b in ctrl.breadcrumbs)


@pytest.mark.asyncio
async def test_us2_turn_look_around_guidance_timeout_and_degraded_visual_failsafe():
    """T021 [US2]: Executes turn_look_around at corners, triggers 5s timeout failsafe (`SC-004`), and pauses/returns on degraded feed (`FR-015`)."""
    import time

    swarm_id = str(uuid.uuid4())
    survey_id = str(uuid.uuid4())

    # 1. Guidance outage timeout -> boundary_hold -> failsafe return (`SC-004`, `SC-007`)
    drone = _FakeDrone()
    pub = _RecordingPublisher(swarm_id=swarm_id)
    analyzer = _HeadingScriptAnalyzer(open_headings={0})
    analyzer.get_heading = lambda: drone.heading_deg
    cfg = CorridorSurveyConfig(
        survey_id=survey_id,
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        target_distance_m=20.0,
        guidance_timeout_s=0.05,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl = CorridorSurveyController(
        config=cfg,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=analyzer,
        drone=drone,
        telemetry_publisher=pub,
    )
    await ctrl.run_initial_look_around()
    ctrl._last_guidance_mono = time.monotonic() - 0.1
    outcome = await ctrl.step_outbound()
    assert outcome == "guidance_timeout_failsafe"
    assert ctrl.phase == SurveyPhase.BOUNDARY_HOLD
    assert drone.action.hold_calls >= 1

    # 2. Degraded visual recapture -> pause at boundary_hold then visual_degraded failsafe (`FR-015`)
    class _DegradedAnalyzer:
        def reset_temporal_state(self):
            return None

        def analyze_frame(self, frame, intelligence_focus=None):
            return CorridorFrameAnalysis(
                visual_confidence=0.12,
                blur_score=4.0,
                brightness_score=5.0,
                is_frozen=False,
                corridor_open=False,
                is_dead_end=False,
                structural_tags=["dark"],
                analysis_latency_ms=5.0,
            )

    deg_cfg = CorridorSurveyConfig(
        survey_id=survey_id,
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        target_distance_m=20.0,
        guidance_timeout_s=5.0,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl_deg = CorridorSurveyController(
        config=deg_cfg,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_DegradedAnalyzer(),
        drone=_FakeDrone(),
        telemetry_publisher=_RecordingPublisher(swarm_id=swarm_id),
    )
    ctrl_deg.phase = SurveyPhase.OUTBOUND_DISCOVERY
    assert await ctrl_deg.step_outbound() == "recapture"
    assert ctrl_deg.phase == SurveyPhase.BOUNDARY_HOLD
    assert await ctrl_deg.step_outbound() == "visual_degraded"

    # 3. Turn look-around recovers 45-degree L-turn without declaring dead end
    class _CornerAnalyzer:
        def __init__(self, dr):
            self.dr = dr

        def reset_temporal_state(self):
            return None

        def analyze_frame(self, frame, intelligence_focus=None):
            is_open = int(round(self.dr.heading_deg)) % 360 == 45
            return CorridorFrameAnalysis(
                visual_confidence=0.95,
                blur_score=190.0,
                brightness_score=140.0,
                is_frozen=False,
                corridor_open=is_open,
                is_dead_end=not is_open,
                primary_branch=CorridorBranchCandidate(0.0, 0.0, 0.89, 3.0, 3.0) if is_open else None,
                structural_tags=[] if is_open else ["dead_end"],
                analysis_latency_ms=10.0,
            )

    corner_drone = _FakeDrone()
    corner_pub = _RecordingPublisher(swarm_id=swarm_id)
    corner_cfg = CorridorSurveyConfig(
        survey_id=survey_id,
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        target_distance_m=20.0,
        guidance_timeout_s=5.0,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl_corner = CorridorSurveyController(
        config=corner_cfg,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_CornerAnalyzer(corner_drone),
        drone=corner_drone,
        telemetry_publisher=corner_pub,
    )
    ctrl_corner.anchor_origin()
    ctrl_corner.phase = SurveyPhase.OUTBOUND_DISCOVERY
    ctrl_corner.heading_deg = 0.0
    step_outcome = await ctrl_corner.step_outbound()
    assert step_outcome == "continue"
    assert ctrl_corner.heading_deg == pytest.approx(45.0)
    assert any(
        e.get("survey_event_type") == "corridor_phase"
        and e.get("flight_status") == "survey_turn_look_around"
        for e in corner_pub.events
    )


@pytest.mark.asyncio
async def test_us3_completion_dead_end_endurance_far_hold_and_return_retracing():
    """T026 [US3]: Covers 20m distance completion, 12m dead-end return, dynamic battery reserve, far-end hold, and blocked return hold."""
    swarm_id = str(uuid.uuid4())

    class _StraightCorridorAnalyzer:
        def __init__(
            self,
            dead_end_after_calls: int | None = None,
            block_on_return: bool = False,
            drone_ref: _FakeDrone | None = None,
        ) -> None:
            self.calls = 0
            self.dead_end_after_calls = dead_end_after_calls
            self.block_on_return = block_on_return
            self.drone_ref = drone_ref
            self.returning = False

        def reset_temporal_state(self) -> None:
            return None

        def analyze_frame(self, frame, intelligence_focus=None) -> CorridorFrameAnalysis:
            self.calls += 1
            if self.returning and self.block_on_return:
                return CorridorFrameAnalysis(
                    visual_confidence=0.95,
                    blur_score=180.0,
                    brightness_score=130.0,
                    is_frozen=False,
                    corridor_open=False,
                    is_dead_end=True,
                    structural_tags=["dead_end"],
                    analysis_latency_ms=10.0,
                )
            facing_forward = (
                self.drone_ref is None
                or min(abs(self.drone_ref.heading_deg - 0.0), 360.0 - abs(self.drone_ref.heading_deg)) < 60.0
            )
            if (
                facing_forward
                and self.dead_end_after_calls is not None
                and self.calls >= self.dead_end_after_calls
            ):
                return CorridorFrameAnalysis(
                    visual_confidence=0.95,
                    blur_score=180.0,
                    brightness_score=130.0,
                    is_frozen=False,
                    corridor_open=False,
                    is_dead_end=True,
                    structural_tags=["dead_end"],
                    analysis_latency_ms=10.0,
                )
            return CorridorFrameAnalysis(
                visual_confidence=0.95,
                blur_score=180.0,
                brightness_score=130.0,
                is_frozen=False,
                corridor_open=True,
                is_dead_end=False,
                primary_branch=CorridorBranchCandidate(0.0, 0.0, 0.90, 3.0, 3.0),
                analysis_latency_ms=10.0,
            )

    # 1. Full 20m completion + reverse return to origin
    drone1 = _FakeDrone()
    pub1 = _RecordingPublisher(swarm_id=swarm_id)
    cfg1 = CorridorSurveyConfig(
        survey_id=str(uuid.uuid4()),
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        target_distance_m=20.0,
        segment_step_m=4.0,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl1 = CorridorSurveyController(
        config=cfg1,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_StraightCorridorAnalyzer(),
        drone=drone1,
        telemetry_publisher=pub1,
    )
    reason1 = await ctrl1.run()
    assert reason1 == "distance_reached"
    assert ctrl1.phase == SurveyPhase.COMPLETED
    assert ctrl1.status == "completed"
    assert ctrl1.surveyed_distance_m == pytest.approx(20.0)
    assert ctrl1.rel_x_m == pytest.approx(0.0)
    assert ctrl1.rel_y_m == pytest.approx(0.0)
    assert any(s["phase"] == "returning" for s in pub1.snapshots)

    # 2. Early 12m dead-end termination + reverse return
    drone2 = _FakeDrone()
    an2 = _StraightCorridorAnalyzer(dead_end_after_calls=12, drone_ref=drone2)
    ctrl2 = CorridorSurveyController(
        config=cfg1,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=an2,
        drone=drone2,
        telemetry_publisher=_RecordingPublisher(swarm_id=swarm_id),
    )
    reason2 = await ctrl2.run()
    assert reason2 == "dead_end"
    assert ctrl2.phase == SurveyPhase.COMPLETED
    assert ctrl2.surveyed_distance_m == pytest.approx(12.0)

    # 3. Dynamic battery safe-return endurance reserve on 500m order (`FR-009`, `FR-021`)
    drone3 = _FakeDrone()
    drone3.battery_pct = 24.0
    cfg3 = CorridorSurveyConfig(
        survey_id=str(uuid.uuid4()),
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        target_distance_m=500.0,
        segment_step_m=4.0,
        min_battery_reserve_pct=20.0,
        battery_drain_pct_per_meter=0.5,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl3 = CorridorSurveyController(
        config=cfg3,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_StraightCorridorAnalyzer(),
        drone=drone3,
        telemetry_publisher=_RecordingPublisher(swarm_id=swarm_id),
    )
    reason3 = await ctrl3.run()
    assert reason3 == "endurance_reserve"
    assert ctrl3.phase == SurveyPhase.COMPLETED
    assert ctrl3.surveyed_distance_m < 20.0

    # 4. return_to_origin=False holds safely at far end
    cfg4 = CorridorSurveyConfig(
        survey_id=str(uuid.uuid4()),
        command_id=str(uuid.uuid4()),
        swarm_id=swarm_id,
        target_distance_m=8.0,
        return_to_origin=False,
        segment_step_m=4.0,
        yaw_settle_s=0.0,
        step_sleep_s=0.0,
    )
    ctrl4 = CorridorSurveyController(
        config=cfg4,
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_StraightCorridorAnalyzer(),
        drone=_FakeDrone(),
        telemetry_publisher=_RecordingPublisher(swarm_id=swarm_id),
    )
    reason4 = await ctrl4.run()
    assert reason4 == "far_end_hold"
    assert ctrl4.phase == SurveyPhase.COMPLETED_HOLDING

    # 5. Blocked return triggers return_blocked_hold (`FR-010`)
    an5 = _StraightCorridorAnalyzer(block_on_return=True)
    drone5 = _FakeDrone()
    ctrl5 = CorridorSurveyController(
        config=cfg4.__class__(**{**cfg4.__dict__, "return_to_origin": True}),
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=an5,
        drone=drone5,
        telemetry_publisher=_RecordingPublisher(swarm_id=swarm_id),
    )
    await ctrl5.run_initial_look_around()
    await ctrl5.step_outbound()
    an5.returning = True
    await ctrl5.run_return_leg("distance_reached")
    assert ctrl5.phase == SurveyPhase.RETURN_BLOCKED_HOLD
    assert ctrl5.completion_reason == "return_blocked"
    assert drone5.action.hold_calls >= 1


@pytest.mark.asyncio
async def test_us3_recall_vs_emergency_abort_and_edge_endpoints(monkeypatch: pytest.MonkeyPatch):
    """T026/T029 [US3]: Differentiates recall (reverse return) vs emergency_abort (action.hold in place) over HTTP & controller."""
    swarm_id = str(uuid.uuid4())
    survey_id_recall = str(uuid.uuid4())
    survey_id_abort = str(uuid.uuid4())
    pub = _RecordingPublisher(swarm_id=swarm_id)

    class _OpenAnalyzer:
        def reset_temporal_state(self):
            return None

        def analyze_frame(self, frame, intelligence_focus=None):
            return CorridorFrameAnalysis(
                visual_confidence=0.95,
                blur_score=180.0,
                brightness_score=130.0,
                is_frozen=False,
                corridor_open=True,
                is_dead_end=False,
                primary_branch=CorridorBranchCandidate(0.0, 0.0, 0.9, 3.0, 3.0),
                analysis_latency_ms=8.0,
            )

    drone_r = _FakeDrone()
    ctrl_r = CorridorSurveyController(
        config=CorridorSurveyConfig(
            survey_id=survey_id_recall,
            command_id=str(uuid.uuid4()),
            swarm_id=swarm_id,
            target_distance_m=20.0,
            segment_step_m=4.0,
            yaw_settle_s=0.0,
            step_sleep_s=0.0,
        ),
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_OpenAnalyzer(),
        drone=drone_r,
        telemetry_publisher=pub,
    )
    await ctrl_r.run_initial_look_around()
    await ctrl_r.step_outbound()

    drone_a = _FakeDrone()
    ctrl_a = CorridorSurveyController(
        config=CorridorSurveyConfig(
            survey_id=survey_id_abort,
            command_id=str(uuid.uuid4()),
            swarm_id=swarm_id,
            target_distance_m=20.0,
            segment_step_m=4.0,
            yaw_settle_s=0.0,
            step_sleep_s=0.0,
        ),
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=_OpenAnalyzer(),
        drone=drone_a,
        telemetry_publisher=pub,
    )
    await ctrl_a.run_initial_look_around()
    await ctrl_a.step_outbound()

    monkeypatch.setattr(edge_server, "_telemetry_publisher", pub)
    edge_server._corridor_controllers.clear()
    edge_server._corridor_tasks.clear()
    edge_server._corridor_controllers[survey_id_recall] = ctrl_r
    edge_server._corridor_controllers[survey_id_abort] = ctrl_a

    app = edge_server.create_edge_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        r_recall = await client.post(f"/corridor-survey/{survey_id_recall}/recall", json={"rationale": "Operator recall"})
        assert r_recall.status_code == 200
        assert r_recall.json()["phase"] == "returning"
        assert ctrl_r._recall_requested is True

        r_abort = await client.post(
            f"/corridor-survey/{survey_id_abort}/emergency-abort",
            json={"rationale": "Immediate obstacle hazard"},
        )
        assert r_abort.status_code == 200
        assert r_abort.json()["phase"] == "emergency_hold"
        assert ctrl_a.phase == SurveyPhase.EMERGENCY_HOLD
        assert drone_a.action.hold_calls >= 1

        r_missing = await client.post(f"/corridor-survey/{uuid.uuid4()}/recall", json={})
        assert r_missing.status_code == 404

    edge_server._corridor_controllers.clear()


@pytest.mark.asyncio
async def test_us3_live_battery_depletion_and_recall_during_initial_look_around():
    """T046/Review Hardening: Refreshes live mid-flight battery reserve and cleanly completes recall during initial look-around."""
    swarm_id = str(uuid.uuid4())

    class _DepletingBatteryAnalyzer:
        def __init__(self, drone_ref: _FakeDrone) -> None:
            self.drone_ref = drone_ref
            self.outbound_calls = 0

        def reset_temporal_state(self) -> None:
            return None

        def analyze_frame(self, frame, intelligence_focus=None) -> CorridorFrameAnalysis:
            if self.outbound_calls >= 1:
                self.drone_ref.battery_pct = 20.5
            return CorridorFrameAnalysis(
                visual_confidence=0.95,
                blur_score=180.0,
                brightness_score=130.0,
                is_frozen=False,
                corridor_open=True,
                is_dead_end=False,
                primary_branch=CorridorBranchCandidate(0.0, 0.0, 0.9, 3.0, 3.0),
                analysis_latency_ms=8.0,
            )

    drone_b = _FakeDrone()
    drone_b.battery_pct = 90.0
    an_b = _DepletingBatteryAnalyzer(drone_b)
    pub_b = _RecordingPublisher(swarm_id=swarm_id)
    ctrl_b = CorridorSurveyController(
        config=CorridorSurveyConfig(
            survey_id=str(uuid.uuid4()),
            command_id=str(uuid.uuid4()),
            swarm_id=swarm_id,
            target_distance_m=200.0,
            segment_step_m=4.0,
            min_battery_reserve_pct=20.0,
            battery_drain_pct_per_meter=0.5,
            yaw_settle_s=0.0,
            step_sleep_s=0.0,
        ),
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=an_b,
        drone=drone_b,
        telemetry_publisher=pub_b,
    )
    ok, _ = await ctrl_b.run_initial_look_around()
    assert ok is True
    assert await ctrl_b.step_outbound() == "continue"
    an_b.outbound_calls = 1
    assert await ctrl_b.step_outbound() == "continue"
    # Battery dropped to 20.5 <= 20 + 8*0.5 = 24% -> live reserve check stops outbound leg
    assert await ctrl_b.step_outbound() == "endurance_reserve"

    # Recall arriving during initial_look_around must complete cleanly in SurveyPhase.COMPLETED with final report
    drone_i = _FakeDrone()
    pub_i = _RecordingPublisher(swarm_id=swarm_id)

    class _RecallDuringSweepAnalyzer:
        def __init__(self) -> None:
            self.calls = 0
            self.ctrl_ref: CorridorSurveyController | None = None

        def reset_temporal_state(self) -> None:
            return None

        def analyze_frame(self, frame, intelligence_focus=None) -> CorridorFrameAnalysis:
            self.calls += 1
            return CorridorFrameAnalysis(
                visual_confidence=0.95,
                blur_score=180.0,
                brightness_score=130.0,
                is_frozen=False,
                corridor_open=True,
                is_dead_end=False,
                primary_branch=CorridorBranchCandidate(0.0, 0.0, 0.9, 3.0, 3.0),
                analysis_latency_ms=8.0,
            )

    an_i = _RecallDuringSweepAnalyzer()
    ctrl_i = CorridorSurveyController(
        config=CorridorSurveyConfig(
            survey_id=str(uuid.uuid4()),
            command_id=str(uuid.uuid4()),
            swarm_id=swarm_id,
            target_distance_m=20.0,
            yaw_settle_s=0.02,
            step_sleep_s=0.0,
        ),
        camera=_StubCamera(lambda: _dummy_jpeg()),
        analyzer=an_i,
        drone=drone_i,
        telemetry_publisher=pub_i,
    )

    async def _recall_shortly():
        await asyncio.sleep(0.01)
        await ctrl_i.recall(rationale="Abort during origin sweep", commander_id="commander-alpha")

    run_task = asyncio.create_task(ctrl_i.run())
    recall_task = asyncio.create_task(_recall_shortly())
    reason_i = await asyncio.gather(run_task, recall_task)
    assert reason_i[0] == "operator_recall"
    assert ctrl_i.phase == SurveyPhase.COMPLETED
    assert any(e.get("survey_event_type") == "corridor_report" for e in pub_i.events)
    override_evts = [e for e in pub_i.events if e.get("survey_event_type") == "corridor_override"]
    assert override_evts[-1]["payload"]["commander_id"] == "commander-alpha"



