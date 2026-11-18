"""Hermetic unit tests for edge obstacle detection, LLM target matching, and lateral bypass."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from src.edge.navigation.flight_controller import FlightController
from src.edge.vision.inference import (
    Detection,
    compute_corridor_occupancy,
    select_clearest_lateral_side,
)
from src.edge.vision.target_matcher import EdgeTargetMatcher, TargetClassificationResult


class _FakeGeminiClient:
    """Hermetic stub for google-genai client in unit tests (Constitution VI)."""

    def __init__(self, mapping: dict[str, tuple[bool, float, str]]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []
        self.models = self

    def generate_content(self, *, model: str, contents: str, config=None):
        self.calls.append(contents)
        detected = ""
        for line in contents.splitlines():
            if line.startswith("Input: "):
                detected = json.loads(line[len("Input: "):]).get("detected_class", "").lower()
                break
        if detected in {k.lower() for k in self.mapping}:
            for key, (matched, conf, rationale) in self.mapping.items():
                if key.lower() == detected:
                    return SimpleNamespace(
                        text=json.dumps(
                            {
                                "is_ordered_target": matched,
                                "confidence": conf,
                                "rationale": rationale,
                            }
                        )
                    )
        return SimpleNamespace(
            text=json.dumps(
                {
                    "is_ordered_target": False,
                    "confidence": 0.95,
                    "rationale": "Default mismatch",
                }
            )
        )


class _FakeCamera:
    def __init__(self, frames: list[np.ndarray | None]) -> None:
        self._frames = list(frames)
        self._idx = 0
        self.width = 640
        self.height = 480
        self._capture = SimpleNamespace(isOpened=lambda: True)

    def open(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def read_frame(self):
        if self._idx < len(self._frames):
            frame = self._frames[self._idx]
            self._idx += 1
            return frame
        return self._frames[-1] if self._frames else None


class _FakeInference:
    def __init__(self, per_call_detections: list[list[Detection]]) -> None:
        self._batches = list(per_call_detections)
        self._idx = 0
        self._model = object()

    def load(self) -> bool:
        return True

    def detect(self, frame, target_class: str | None = None) -> list[Detection]:
        if self._idx < len(self._batches):
            dets = self._batches[self._idx]
            self._idx += 1
        else:
            dets = self._batches[-1] if self._batches else []
        if target_class is None:
            return dets
        return [d for d in dets if d.class_name.lower() == target_class.lower()]


class _FakeTelemetryPublisher:
    def __init__(self) -> None:
        self.project_id = "default-theater"
        self.swarm_id = "swarm-1"
        self.drone_id = "drone-1"
        self.events = []
        self.alerts = []

    async def publish_event(self, event, snapshot_local_path=None) -> bool:
        self.events.append(event)
        return True

    async def publish_detection(self, **kwargs):
        self.events.append(kwargs)
        return SimpleNamespace(event_id="det-evt-1")

    async def publish_avoidance_alert(self, **kwargs):
        self.alerts.append(kwargs)
        return SimpleNamespace(event_id="alert-evt-1")


def _make_fake_drone():
    drone = SimpleNamespace()
    drone.action = SimpleNamespace(
        goto_location=AsyncMock(),
        hold=AsyncMock(),
    )
    return drone


def test_corridor_occupancy_and_clearest_side():
    dets = [
        Detection("traffic light", 0.9, (250, 100, 350, 420), (300, 260)),
        Detection("person", 0.85, (20, 200, 80, 350), (50, 275)),
    ]
    corridor = compute_corridor_occupancy(dets, frame_width=640, frame_height=480)
    assert corridor[0].in_forward_corridor is True
    assert corridor[0].area_ratio > 0.015
    assert corridor[1].in_forward_corridor is False

    # Left has person + partial traffic light? Actually traffic light x=250..350 is mostly left of 320!
    # Right side has only x=320..350 of traffic light, so right side is clearer.
    assert select_clearest_lateral_side(dets, frame_width=640, frame_height=480) == "right"

    # Obstacle on right half -> left side is clearer
    right_dets = [Detection("pole", 0.9, (340, 80, 460, 440), (400, 260))]
    assert select_clearest_lateral_side(right_dets, frame_width=640, frame_height=480) == "left"


def test_edge_target_matcher_llm_cache_and_failsafe():
    fake_client = _FakeGeminiClient(
        {
            "truck": (True, 0.92, "Matches ordered military vehicle target"),
            "traffic light": (False, 0.96, "Lamp post / traffic light is an obstacle"),
            "van": (True, 0.55, "Ambiguous low-confidence match"),
        }
    )
    matcher = EdgeTargetMatcher(client=fake_client, cache_ttl_s=60.0)

    res_match = matcher.classify(
        mission_id="cmd-1",
        target_class="military vehicle",
        detected_class="truck",
    )
    assert isinstance(res_match, TargetClassificationResult)
    assert res_match.is_ordered_target is True
    assert res_match.evaluated_by == "edge_llm"

    # Second call for same tuple uses TTL cache
    res_cached = matcher.classify(
        mission_id="cmd-1",
        target_class="military vehicle",
        detected_class="truck",
    )
    assert res_cached.is_ordered_target is True
    assert len(fake_client.calls) == 1

    # Non-target obstacle
    res_obs = matcher.classify(
        mission_id="cmd-1",
        target_class="military vehicle",
        detected_class="traffic light",
    )
    assert res_obs.is_ordered_target is False

    # Fail-safe: confidence < 0.7 must be treated as non-target obstacle
    res_ambig = matcher.classify(
        mission_id="cmd-1",
        target_class="military vehicle",
        detected_class="van",
    )
    assert res_ambig.is_ordered_target is False


@pytest.mark.asyncio
async def test_flight_controller_bypasses_obstacle_and_resumes_with_latency_under_500ms():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    obstacle_det = Detection("traffic light", 0.89, (290, 80, 410, 420), (350, 250))
    # 2 frames with obstacle, then 4 clear frames to trigger resume -> searching
    batches = [[obstacle_det], [obstacle_det], [], [], [], []]

    fake_client = _FakeGeminiClient(
        {"traffic light": (False, 0.95, "Lamp post is not ordered target truck")}
    )
    matcher = EdgeTargetMatcher(client=fake_client)
    # Warm cache once so critical-zone loop measures steady-state <500ms reaction
    matcher.classify(mission_id="cmd-1", target_class="truck", detected_class="traffic light")

    drone = _make_fake_drone()
    pub = _FakeTelemetryPublisher()
    ctrl = FlightController(
        camera=_FakeCamera([frame] * 6),
        inference=_FakeInference(batches),
        target_class="truck",
        drone=drone,
        telemetry_publisher=pub,
        mission_id="cmd-1",
        target_matcher=matcher,
        loop_interval_s=0.01,
    )
    ctrl.last_lat = 47.3977
    ctrl.last_lon = 8.5456
    ctrl.last_alt_m = 505.0
    ctrl.last_heading_deg = 0.0
    ctrl._running = True

    t0 = time.perf_counter()
    await ctrl._navigation_loop(max_iterations=6)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 500.0
    assert drone.action.goto_location.await_count >= 1
    assert len(pub.alerts) >= 2
    bypass_alert = pub.alerts[0]
    assert bypass_alert["action"] == "obstacle_bypass"
    assert bypass_alert["obstacle_class"] == "traffic light"
    assert bypass_alert["bypass_direction"] in ("left", "right")
    assert any(a["action"] == "resume_route" for a in pub.alerts)
    assert ctrl.state.status == "searching"


@pytest.mark.asyncio
async def test_flight_controller_approaches_ordered_target_without_bypass():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    target_det = Detection("truck", 0.92, (260, 140, 380, 340), (320, 240))
    fake_client = _FakeGeminiClient(
        {"truck": (True, 0.96, "Matches ordered target truck")}
    )
    matcher = EdgeTargetMatcher(client=fake_client)
    drone = _make_fake_drone()
    pub = _FakeTelemetryPublisher()

    ctrl = FlightController(
        camera=_FakeCamera([frame, frame]),
        inference=_FakeInference([[target_det], [target_det]]),
        target_class="truck",
        drone=drone,
        telemetry_publisher=pub,
        mission_id="cmd-2",
        target_matcher=matcher,
        loop_interval_s=0.01,
    )
    ctrl.last_lat = 47.3977
    ctrl.last_lon = 8.5456
    ctrl.last_alt_m = 505.0
    ctrl._running = True

    await ctrl._navigation_loop(max_iterations=2)

    assert ctrl.state.status == "approaching"
    assert ctrl.state.target_detected is True
    assert len(pub.alerts) == 0


@pytest.mark.asyncio
async def test_flight_controller_obstructed_hold_on_blocked_corridor_and_frame_loss():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Full-width obstacle blocking both left and right corridors
    wall_det = Detection("wall", 0.91, (10, 40, 630, 460), (320, 250))
    fake_client = _FakeGeminiClient({"wall": (False, 0.99, "Wall obstacle")})
    drone = _make_fake_drone()
    pub = _FakeTelemetryPublisher()

    ctrl = FlightController(
        camera=_FakeCamera([frame]),
        inference=_FakeInference([[wall_det]]),
        target_class="truck",
        drone=drone,
        telemetry_publisher=pub,
        mission_id="cmd-3",
        target_matcher=EdgeTargetMatcher(client=fake_client),
        loop_interval_s=0.01,
    )
    ctrl.last_lat = 47.3977
    ctrl.last_lon = 8.5456
    ctrl.last_alt_m = 505.0
    ctrl._running = True

    await ctrl._navigation_loop(max_iterations=1)
    assert ctrl.state.status == "obstructed_hold"
    drone.action.hold.assert_awaited()
    assert pub.alerts[-1]["action"] == "obstructed_hold"

    # Perception loss hold
    drone2 = _make_fake_drone()
    pub2 = _FakeTelemetryPublisher()
    ctrl2 = FlightController(
        camera=_FakeCamera([None, None, None]),
        inference=_FakeInference([[]]),
        target_class="truck",
        drone=drone2,
        telemetry_publisher=pub2,
        mission_id="cmd-4",
        target_matcher=EdgeTargetMatcher(client=fake_client),
        loop_interval_s=0.01,
    )
    ctrl2._running = True
    await ctrl2._navigation_loop(max_iterations=3)
    assert ctrl2.state.status == "obstructed_hold"
    drone2.action.hold.assert_awaited()
    assert pub2.alerts[-1]["action"] == "obstructed_hold"
