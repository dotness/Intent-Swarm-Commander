"""Hermetic unit tests for CorridorVisualAnalyzer (`FR-004`, `FR-006`, `FR-011`, `FR-015`, `FR-016`, `SC-007`)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.edge.vision.corridor_analyzer import CorridorVisualAnalyzer


def _make_open_corridor_frame(
    *,
    width: int = 320,
    height: int = 240,
    azimuth_shift: float = 0.0,
    overhang_top: bool = False,
) -> np.ndarray:
    """Render a deterministic textured 3D perspective open corridor image.

    `azimuth_shift` in [-0.6, +0.6] moves the open corridor vanishing portal left or right.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    # Textured side walls & ceiling framing
    img[:, :] = (48, 52, 58)
    # High-frequency textured brick stripes on left/right walls so edges exist cleanly
    for y in range(0, height, 12):
        cv2.line(img, (0, y), (width - 1, y), (95, 100, 110), 1)
    for x in range(0, width, 18):
        cv2.line(img, (x, 0), (x, height - 1), (80, 86, 94), 1)

    cx = int(width * (0.5 + azimuth_shift * 0.55))
    cy = int(height * (0.64 if overhang_top else 0.48))
    portal_w = int(width * 0.28)
    portal_h = int(height * (0.26 if overhang_top else 0.42))

    # Carve open far corridor portal (smooth illuminated open depth band)
    x1 = max(4, cx - portal_w // 2)
    x2 = min(width - 4, cx + portal_w // 2)
    y1 = max(4, cy - portal_h // 2)
    y2 = min(height - 4, cy + portal_h // 2)
    cv2.rectangle(img, (x1, y1), (x2, y2), (165, 178, 185), -1)
    # Perspective guide lines converging toward portal corners
    cv2.line(img, (0, 0), (x1, y1), (200, 200, 200), 2)
    cv2.line(img, (width - 1, 0), (x2, y1), (200, 200, 200), 2)
    cv2.line(img, (0, height - 1), (x1, y2), (200, 200, 200), 2)
    cv2.line(img, (width - 1, height - 1), (x2, y2), (200, 200, 200), 2)

    if overhang_top:
        # Solid beam hanging across upper ceiling band with warning stripes
        beam_bottom = int(height * 0.44)
        cv2.rectangle(img, (0, 0), (width - 1, beam_bottom), (36, 40, 46), -1)
        for sx in range(0, width, 24):
            cv2.rectangle(img, (sx, beam_bottom - 14), (sx + 12, beam_bottom), (0, 175, 235), -1)
    return img


def _make_dead_end_wall_frame(width: int = 320, height: int = 240) -> np.ndarray:
    """Render a solid textured dead-end wall across the entire forward view."""
    img = np.full((height, width, 3), (72, 62, 58), dtype=np.uint8)
    for row_idx, y in enumerate(range(0, height, 18)):
        cv2.line(img, (0, y), (width - 1, y), (145, 130, 125), 2)
        offset = 14 if row_idx % 2 == 0 else 0
        for x in range(offset, width, 28):
            cv2.line(img, (x, y), (x, min(height - 1, y + 18)), (145, 130, 125), 2)
    return img


def test_us1_visual_quality_gates_detect_dark_blur_and_frozen():
    """T011 [US1]: Dark, blurry, and frozen frames fail confidence gate and emit quality tags."""
    analyzer = CorridorVisualAnalyzer()

    dark_frame = np.full((240, 320, 3), 6, dtype=np.uint8)
    dark_res = analyzer.analyze_frame(dark_frame)
    assert dark_res.visual_confidence < 0.4
    assert "dark" in dark_res.structural_tags
    assert dark_res.corridor_open is False

    base_open = _make_open_corridor_frame()
    blurry = cv2.GaussianBlur(base_open, (35, 35), 12.0)
    blur_res = analyzer.analyze_frame(blurry)
    assert blur_res.visual_confidence < 0.45
    assert "blur" in blur_res.structural_tags
    assert blur_res.corridor_open is False

    analyzer_freeze = CorridorVisualAnalyzer(freeze_repeat_limit=2)
    f1 = analyzer_freeze.analyze_frame(base_open)
    assert f1.is_frozen is False
    f2 = analyzer_freeze.analyze_frame(base_open.copy())
    f3 = analyzer_freeze.analyze_frame(base_open.copy())
    assert f3.is_frozen is True
    assert "frozen" in f3.structural_tags
    assert f3.corridor_open is False


def test_us1_open_passage_vs_enclosed_wall_detection():
    """T011 [US1]: Distinguishes open corridor passage (azimuth/clearance) from enclosed wall dead end."""
    analyzer = CorridorVisualAnalyzer()

    open_frame = _make_open_corridor_frame(azimuth_shift=0.0)
    open_res = analyzer.analyze_frame(open_frame)
    assert open_res.corridor_open is True
    assert open_res.is_dead_end is False
    assert open_res.primary_branch is not None
    assert abs(open_res.primary_branch.azimuth_offset_deg) <= 20.0
    assert open_res.primary_branch.estimated_width_m >= 1.5
    assert open_res.primary_branch.estimated_height_m >= 1.5

    wall_frame = _make_dead_end_wall_frame()
    wall_res = analyzer.analyze_frame(wall_frame)
    assert wall_res.corridor_open is False
    assert wall_res.is_dead_end is True
    assert "dead_end" in wall_res.structural_tags


def _make_slope_up_frame(width: int = 320, height: int = 240) -> np.ndarray:
    """Render an upward ramp / lower obstruction forcing upward vertical climb clearance."""
    img = _make_open_corridor_frame(width=width, height=height, azimuth_shift=0.0, overhang_top=False)
    # Dark raised step/ramp blocking lower band while upper half stays clear & open
    step_top = int(height * 0.56)
    cv2.rectangle(img, (0, step_top), (width - 1, height - 1), (34, 38, 42), -1)
    for y in range(step_top, height, 10):
        cv2.line(img, (0, y), (width - 1, y), (88, 92, 98), 1)
    # Carve high elevated continuation portal in upper center
    cv2.rectangle(img, (int(width * 0.36), int(height * 0.08)), (int(width * 0.64), int(height * 0.42)), (178, 188, 194), -1)
    return img


def _make_fork_junction_frame(width: int = 320, height: int = 240) -> np.ndarray:
    """Render a T-junction/fork with left and right open portals separated by a center textured pillar."""
    img = _make_dead_end_wall_frame(width=width, height=height)
    # Left branch portal (col 0..1)
    cv2.rectangle(img, (10, int(height * 0.25)), (int(width * 0.28), int(height * 0.78)), (170, 180, 188), -1)
    # Right branch portal (col 3..4)
    cv2.rectangle(img, (int(width * 0.72), int(height * 0.25)), (width - 10, int(height * 0.78)), (168, 178, 186), -1)
    return img


def test_us2_curve_l_turn_overhang_slope_fork_and_sub_500ms_latency():
    """T020 [US2]: Handles curve/L-turn steering, low-overhang & slope_up elevation adjustment, multi-peak forks, and <=500ms latency."""
    analyzer = CorridorVisualAnalyzer()

    # Curve / L-turn right & left steering
    right_turn = analyzer.analyze_frame(_make_open_corridor_frame(azimuth_shift=0.68))
    assert right_turn.corridor_open is True
    assert right_turn.primary_branch is not None
    assert right_turn.primary_branch.azimuth_offset_deg > 18.0
    assert any(t in right_turn.structural_tags for t in ("turn_right", "curve_right"))

    left_bend = analyzer.analyze_frame(_make_open_corridor_frame(azimuth_shift=-0.68))
    assert left_bend.corridor_open is True
    assert left_bend.primary_branch is not None
    assert left_bend.primary_branch.azimuth_offset_deg < -18.0
    assert any(t in left_bend.structural_tags for t in ("turn_left", "curve_left"))

    # Low overhang -> downward elevation adjustment
    overhang_res = analyzer.analyze_frame(_make_open_corridor_frame(overhang_top=True))
    assert overhang_res.corridor_open is True
    assert overhang_res.primary_branch is not None
    assert overhang_res.primary_branch.elevation_offset_m < 0.0
    assert "low_overhang" in overhang_res.structural_tags

    # Upward slope / raised floor -> upward elevation adjustment
    slope_res = analyzer.analyze_frame(_make_slope_up_frame())
    assert slope_res.corridor_open is True
    assert slope_res.primary_branch is not None
    assert slope_res.primary_branch.elevation_offset_m > 0.0
    assert "slope_up" in slope_res.structural_tags

    # Fork / intersection -> secondary branch detected
    fork_res = analyzer.analyze_frame(_make_fork_junction_frame())
    assert fork_res.corridor_open is True
    assert fork_res.primary_branch is not None
    assert len(fork_res.secondary_branches) >= 1
    assert "intersection" in fork_res.structural_tags

    # Latency budget SC-007 (<= 500 ms per frame)
    for _ in range(5):
        res = analyzer.analyze_frame(_make_open_corridor_frame(azimuth_shift=0.25))
        assert res.analysis_latency_ms <= 500.0


def test_us2_yolo_and_cached_target_matcher_classify_hazards_vs_mission_interest():
    """T020 [US2]: Discriminates interior non-target hazards from intelligence_focus targets using YoloE + EdgeTargetMatcher."""
    import json
    from types import SimpleNamespace
    from src.edge.vision.inference import Detection
    from src.edge.vision.target_matcher import EdgeTargetMatcher

    class _FakeYolo:
        _model = object()

        def detect(self, frame, target_class=None):
            return [
                Detection(class_name="truck", confidence=0.92, bbox=(20, 40, 95, 160), center=(57, 100)),
                Detection(class_name="pole", confidence=0.88, bbox=(120, 30, 195, 220), center=(157, 125)),
            ]

    class _FakeGemini:
        def __init__(self):
            self.models = self

        def generate_content(self, *, model, contents, config=None):
            detected = json.loads(contents.splitlines()[-2].split("Input: ")[1])["detected_class"]
            is_match = detected == "truck"
            return SimpleNamespace(
                text=json.dumps({
                    "is_ordered_target": is_match,
                    "confidence": 0.94,
                    "rationale": "Semantic truck -> military vehicle match" if is_match else "Static pole hazard",
                })
            )

    matcher = EdgeTargetMatcher(client=_FakeGemini())
    analyzer = CorridorVisualAnalyzer(
        inference=_FakeYolo(),
        target_matcher=matcher,
        mission_id="cmd-us2",
    )
    frame = _make_open_corridor_frame(azimuth_shift=0.0)
    res = analyzer.analyze_frame(frame, intelligence_focus=["military vehicle"])
    assert len(res.target_findings) == 1
    assert res.target_findings[0]["label"] == "truck"
    assert res.target_findings[0]["matches_mission_interest"] is True
    assert len(res.hazards) == 1
    assert res.hazards[0]["label"] == "pole"
    assert res.corridor_open is True


def test_us4_virtual_cam_corridor_scene_renders_match_edge_analyzer():
    """T042 [US4]: Verifies scripts/virtual_cam_server.py corridor_scene geometries and MQTT pose updates parse accurately in CorridorVisualAnalyzer."""
    import uuid
    from scripts.virtual_cam_server import _FrameProvider, render_corridor_scene_frame

    analyzer = CorridorVisualAnalyzer()

    # 1. Straight passage open ahead (0 deg), closed behind/sideways (90 deg)
    f_straight_open = render_corridor_scene_frame(scenario="straight_20m", rel_y_m=0.0, heading_deg=0.0)
    r_straight = analyzer.analyze_frame(f_straight_open)
    assert r_straight.corridor_open is True
    assert r_straight.primary_branch is not None

    f_straight_wall = render_corridor_scene_frame(scenario="straight_20m", rel_y_m=0.0, heading_deg=90.0)
    assert analyzer.analyze_frame(f_straight_wall).corridor_open is False

    # 2. L-turn right opening at y=8.2m when facing slightly right
    f_lturn = render_corridor_scene_frame(scenario="l_turn_20m", rel_y_m=8.2, heading_deg=45.0)
    r_lturn = analyzer.analyze_frame(f_lturn)
    assert r_lturn.corridor_open is True
    assert r_lturn.primary_branch is not None and r_lturn.primary_branch.azimuth_offset_deg > 10.0

    # 3. Low overhang at y=9m forces downward elevation adjustment
    f_overhang = render_corridor_scene_frame(scenario="s_bend_overhang_20m", rel_x_m=0.0, rel_y_m=9.0, rel_z_m=2.5, heading_deg=0.0)
    r_overhang = analyzer.analyze_frame(f_overhang)
    assert r_overhang.corridor_open is True
    assert "low_overhang" in r_overhang.structural_tags
    assert r_overhang.primary_branch is not None and r_overhang.primary_branch.elevation_offset_m < 0.0

    # 4. Dead end at y=11.5m returns solid wall; returning 180 deg sees open passage
    assert analyzer.analyze_frame(render_corridor_scene_frame(scenario="dead_end_12m", rel_y_m=11.5, heading_deg=0.0)).is_dead_end is True
    assert analyzer.analyze_frame(render_corridor_scene_frame(scenario="dead_end_12m", rel_y_m=11.5, heading_deg=180.0)).corridor_open is True

    # 5. Fork junction yields secondary branch + intersection tag
    f_fork = render_corridor_scene_frame(scenario="branch_junction_20m", rel_y_m=8.0, heading_deg=0.0)
    r_fork = analyzer.analyze_frame(f_fork)
    assert r_fork.corridor_open is True
    assert len(r_fork.secondary_branches) >= 1
    assert "intersection" in r_fork.structural_tags

    # 6. Enclosed start blocks all headings
    for deg in (0, 90, 180, 270):
        assert analyzer.analyze_frame(render_corridor_scene_frame(scenario="enclosed_start", heading_deg=deg)).corridor_open is False

    # 7. MQTT telemetry pose sync updates _FrameProvider pose automatically without HTTP /pose calls
    prov = _FrameProvider(media_path="scripts/virtual_cam_server.py", fps=5.0, initial_mode="clear")
    prov._media_path = ""
    prov._static_jpeg = None
    prov._mode = "corridor_scene"
    prov._scenario = "straight_20m"
    prov.update_from_mqtt_telemetry(
        {
            "metric_type": "alert",
            "lat": 47.39775,
            "lon": 8.54560,
            "alt_m": 502.5,
            "heading_deg": 0.0,
            "extra": {
                "survey_event_type": "corridor_phase",
                "survey_id": str(uuid.uuid4()),
                "rel_x_m": 0.0,
                "rel_y_m": 0.0,
                "rel_z_m": 2.5,
            },
        }
    )
    prov.update_from_mqtt_telemetry(
        {
            "metric_type": "navigation",
            "lat": 47.39784,  # ~10m North
            "lon": 8.54560,
            "alt_m": 502.1,
            "heading_deg": 45.0,
        }
    )
    pose = prov.status()["pose"]
    assert pose["rel_y_m"] > 8.0
    assert pose["rel_z_m"] == pytest.approx(2.1, abs=0.05)
    assert pose["heading_deg"] == pytest.approx(45.0)


