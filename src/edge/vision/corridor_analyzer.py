"""Sub-500 ms 3D edge corridor visual analyzer combining OpenCV 5x3 clearance geometry with YOLO-World/LLM intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

import cv2
import numpy as np

from src.edge.vision.inference import (
    Detection,
    YoloEInference,
    compute_corridor_occupancy,
)
from src.edge.vision.target_matcher import EdgeTargetMatcher


@dataclass
class CorridorBranchCandidate:
    """Navigable 3D passage candidate extracted from the 5x3 spatial occupancy grid."""

    azimuth_offset_deg: float
    elevation_offset_m: float
    openness_score: float
    estimated_width_m: float
    estimated_height_m: float


@dataclass
class CorridorFrameAnalysis:
    """Structured single-snapshot 3D corridor navigability and intelligence analysis."""

    visual_confidence: float
    blur_score: float
    brightness_score: float
    is_frozen: bool
    corridor_open: bool
    is_dead_end: bool
    primary_branch: CorridorBranchCandidate | None = None
    secondary_branches: list[CorridorBranchCandidate] = field(default_factory=list)
    structural_tags: list[str] = field(default_factory=list)
    target_findings: list[dict[str, Any]] = field(default_factory=list)
    hazards: list[dict[str, Any]] = field(default_factory=list)
    analysis_latency_ms: float = 0.0


def _decode_bgr_frame(frame: Any) -> np.ndarray:
    """Decode raw JPEG bytes or validate a BGR numpy frame for OpenCV processing."""
    if isinstance(frame, (bytes, bytearray)):
        arr = np.frombuffer(bytes(frame), dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError("Failed to decode JPEG corridor frame bytes")
        return decoded
    if frame is None or not isinstance(frame, np.ndarray) or frame.ndim != 3:
        raise ValueError("Corridor frame must be a valid 3-channel BGR numpy array or JPEG bytes")
    return frame


class CorridorVisualAnalyzer:
    """Deterministic sub-500 ms 3D corridor perception and obstacle/target analyzer."""

    _SECTOR_ANGLES_DEG: tuple[float, ...] = (-48.0, -24.0, 0.0, 24.0, 48.0)

    def __init__(
        self,
        *,
        inference: YoloEInference | None = None,
        target_matcher: EdgeTargetMatcher | None = None,
        mission_id: str | None = None,
        min_blur_score: float = 25.0,
        min_brightness: float = 24.0,
        max_brightness: float = 245.0,
        freeze_repeat_limit: int = 5,
        openness_threshold: float = 0.50,
    ) -> None:
        self.inference = inference
        self.target_matcher = target_matcher
        self.mission_id = mission_id
        self.min_blur_score = float(min_blur_score)
        self.min_brightness = float(min_brightness)
        self.max_brightness = float(max_brightness)
        self.freeze_repeat_limit = max(2, int(freeze_repeat_limit))
        self.openness_threshold = float(openness_threshold)
        self._prev_thumb: np.ndarray | None = None
        self._frozen_streak: int = 0
        self._prev_estimated_width_m: float | None = None

    def reset_temporal_state(self) -> None:
        """Reset frozen-frame and width-trend buffers at survey start."""
        self._prev_thumb = None
        self._frozen_streak = 0
        self._prev_estimated_width_m = None

    def _evaluate_frame_quality(self, gray: np.ndarray) -> tuple[float, float, float, bool, list[str]]:
        """Evaluate luminance, Laplacian sharpness, and inter-frame freeze."""
        brightness = float(np.mean(gray))
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        std_dev = float(np.std(gray))

        thumb = cv2.resize(gray, (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
        is_frozen = False
        if self._prev_thumb is not None:
            mad = float(np.mean(np.abs(thumb - self._prev_thumb)))
            if mad < 0.08:
                self._frozen_streak += 1
            else:
                self._frozen_streak = 0
            is_frozen = self._frozen_streak >= self.freeze_repeat_limit
        self._prev_thumb = thumb

        tags: list[str] = []
        lum_conf = 1.0
        if brightness < self.min_brightness:
            tags.append("dark")
            lum_conf = max(0.0, brightness / max(self.min_brightness * 1.4, 1.0)) * 0.35
        elif brightness > self.max_brightness:
            tags.append("overexposed")
            lum_conf = max(0.0, (255.0 - brightness) / max(255.0 - self.max_brightness + 5.0, 1.0)) * 0.35

        sharp_conf = 1.0
        if blur_score < self.min_blur_score or std_dev < 4.0:
            tags.append("blur")
            ratio = min(blur_score / max(self.min_blur_score, 1.0), 1.0)
            sharp_conf = min(0.32, ratio * 0.32)

        if is_frozen:
            tags.append("frozen")
            return 0.15, blur_score, brightness, True, tags

        composite = min(lum_conf, sharp_conf)
        if not tags:
            composite = max(0.65, min(1.0, 0.70 + 0.30 * min(1.0, blur_score / (self.min_blur_score * 4.0))))
        return float(composite), blur_score, brightness, False, tags

    def _compute_grid_scores(self, gray: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute 3x5 spatial openness scores (plus crouched low-clearance band) and cell mean luminances."""
        h, w = gray.shape
        # Rows: [0]=upper/ceiling, [1]=middle/cruise, [2]=lower/floor, [3]=low-clearance/belly band
        row_bounds = [
            (0, int(h * 0.36)),
            (int(h * 0.34), int(h * 0.68)),
            (int(h * 0.64), h),
            (int(h * 0.46), int(h * 0.84)),
        ]
        col_w = w / 5.0

        cell_smooth = np.zeros((4, 5), dtype=np.float32)
        cell_lum = np.zeros((4, 5), dtype=np.float32)

        for r, (y1, y2) in enumerate(row_bounds):
            ch = max(4, y2 - y1)
            for c in range(5):
                x1 = int(round(c * col_w))
                x2 = int(round((c + 1) * col_w))
                cw = max(4, x2 - x1)
                patch_edges = edges[y1:y2, x1:x2]
                patch_gray = gray[y1:y2, x1:x2]

                # Evaluate 3x3 overlapping sub-windows (corners + center) so low/narrow crouched portals aren't clipped by band borders
                best_sub_smooth = 0.0
                best_sub_lum = float(np.mean(patch_gray))
                sub_h = max(4, int(ch * 0.46))
                sub_w = max(4, int(cw * 0.50))
                y_offsets = (0, max(0, (ch - sub_h) // 2), max(0, ch - sub_h))
                x_offsets = (0, max(0, (cw - sub_w) // 2), max(0, cw - sub_w))
                for ry in y_offsets:
                    for rx in x_offsets:
                        se = patch_edges[ry : ry + sub_h, rx : rx + sub_w]
                        sg = patch_gray[ry : ry + sub_h, rx : rx + sub_w]
                        ed = float(np.count_nonzero(se)) / float(max(1, se.size))
                        sm = max(0.0, 1.0 - (ed / 0.082))
                        sl = float(np.mean(sg))
                        if sm * max(0.3, sl / 120.0) > best_sub_smooth * max(0.3, best_sub_lum / 120.0):
                            best_sub_smooth = sm
                            best_sub_lum = sl

                whole_ed = float(np.count_nonzero(patch_edges)) / float(max(1, patch_edges.size))
                whole_sm = max(0.0, 1.0 - (whole_ed / 0.082))
                cell_smooth[r, c] = 0.20 * whole_sm + 0.80 * best_sub_smooth
                cell_lum[r, c] = 0.25 * float(np.mean(patch_gray)) + 0.75 * best_sub_lum

        # Penalize dark solid ceiling/floor slabs compared to brighter open portal regions
        ref_bright = max(float(np.percentile(cell_lum[:3, :], 85)), 70.0)
        grid = np.zeros((4, 5), dtype=np.float32)
        for r in range(4):
            for c in range(5):
                lum = float(cell_lum[r, c])
                dark_gap = max(0.0, ref_bright - lum)
                lum_factor = 1.0 if dark_gap < 38.0 else max(0.08, 1.0 - (dark_gap - 38.0) / 55.0)
                if lum < 55.0 and dark_gap > 35.0:
                    lum_factor = min(lum_factor, 0.15)
                grid[r, c] = float(cell_smooth[r, c]) * lum_factor

        return grid, cell_lum

    def _find_column_peaks(self, col_scores: np.ndarray) -> list[int]:
        """Identify separated navigable azimuth peak indices across the 5 horizontal sectors."""
        threshold = self.openness_threshold
        local_peaks: list[int] = []
        for idx in range(5):
            val = float(col_scores[idx])
            if val < threshold:
                continue
            left_ok = idx == 0 or val >= float(col_scores[idx - 1])
            right_ok = idx == 4 or val >= float(col_scores[idx + 1])
            if left_ok and right_ok:
                # Merge flat plateau neighbors by keeping highest or middle
                if local_peaks and idx - local_peaks[-1] == 1 and abs(val - float(col_scores[local_peaks[-1]])) < 0.08:
                    continue
                local_peaks.append(idx)

        # Suppress peaks that belong to the same unsplit opening (no brick/wall valley between them)
        filtered: list[int] = []
        for p in local_peaks:
            if not filtered:
                filtered.append(p)
                continue
            prev = filtered[-1]
            valley = float(np.min(col_scores[prev : p + 1]))
            if p - prev >= 2 and valley < threshold * 0.72:
                filtered.append(p)
            elif float(col_scores[p]) > float(col_scores[prev]):
                filtered[-1] = p
        return filtered

    def _build_branch_candidate(
        self,
        col_idx: int,
        grid: np.ndarray,
        col_scores: np.ndarray,
    ) -> CorridorBranchCandidate:
        """Estimate azimuth offset, vertical elevation offset, width, and headroom for a peak sector."""
        # Refine azimuth using local 3-column weighted interpolation
        left = max(0, col_idx - 1)
        right = min(4, col_idx + 1)
        weights = np.maximum(0.0, col_scores[left : right + 1] - (self.openness_threshold * 0.5))
        if float(np.sum(weights)) > 1e-6:
            angles = np.array([self._SECTOR_ANGLES_DEG[i] for i in range(left, right + 1)], dtype=np.float32)
            azimuth = float(np.sum(angles * weights) / np.sum(weights))
        else:
            azimuth = float(self._SECTOR_ANGLES_DEG[col_idx])

        top_score = float(grid[0, col_idx])
        mid_score = float(grid[1, col_idx])
        bot_score = float(max(grid[2, col_idx], grid[3, col_idx]))

        # Vertical elevation adaptation for low overhangs and slopes (`FR-006`, `FR-021`)
        elevation_offset_m = 0.0
        if top_score < 0.38 and (bot_score >= 0.45 or mid_score >= 0.45):
            elevation_offset_m = -0.55
        elif float(grid[2, col_idx]) < 0.35 and (top_score >= 0.48 or mid_score >= 0.48):
            elevation_offset_m = 0.55

        # Estimate contiguous open column span around col_idx
        span_cols = 0
        for c in range(col_idx, -1, -1):
            if float(col_scores[c]) >= self.openness_threshold * 0.85:
                span_cols += 1
            else:
                break
        for c in range(col_idx + 1, 5):
            if float(col_scores[c]) >= self.openness_threshold * 0.85:
                span_cols += 1
            else:
                break
        open_rows = sum(1 for r in range(3) if float(grid[r, col_idx]) >= self.openness_threshold * 0.78)
        est_width_m = round(max(1.2, 1.3 + span_cols * 0.9), 2)
        est_height_m = round(max(1.0, 1.1 + open_rows * 0.95), 2)

        return CorridorBranchCandidate(
            azimuth_offset_deg=round(azimuth, 2),
            elevation_offset_m=round(elevation_offset_m, 2),
            openness_score=round(float(col_scores[col_idx]), 3),
            estimated_width_m=est_width_m,
            estimated_height_m=est_height_m,
        )

    def _classify_detections(
        self,
        bgr: np.ndarray,
        intelligence_focus: list[str] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Run YOLO-World + cached EdgeTargetMatcher to classify targets vs. corridor hazards (`FR-016`)."""
        target_findings: list[dict[str, Any]] = []
        hazards: list[dict[str, Any]] = []
        if self.inference is None or getattr(self.inference, "_model", None) is None:
            return target_findings, hazards

        detections: list[Detection] = self.inference.detect(bgr, target_class=None)
        if not detections:
            return target_findings, hazards

        h, w = bgr.shape[:2]
        occ_list = compute_corridor_occupancy(detections, frame_width=w, frame_height=h, min_area_ratio=0.01)
        focus_items = [str(f).strip() for f in (intelligence_focus or []) if str(f).strip()]
        focus_lower = {f.lower() for f in focus_items}

        for det, occ in zip(detections, occ_list):
            det_class_low = det.class_name.strip().lower()
            matched_target = det_class_low in focus_lower
            matched_rationale = "Direct class match with intelligence_focus" if matched_target else "Physical interior object"

            if not matched_target and self.target_matcher is not None and focus_items:
                for focus_cls in focus_items:
                    cls_res = self.target_matcher.classify(
                        mission_id=self.mission_id,
                        target_class=focus_cls,
                        detected_class=det.class_name,
                    )
                    if cls_res.is_ordered_target:
                        matched_target = True
                        matched_rationale = cls_res.rationale
                        break
                    matched_rationale = cls_res.rationale

            rel_az = round(((det.center[0] / max(1, w)) - 0.5) * 96.0, 2)
            item = {
                "label": det.class_name,
                "confidence": round(float(det.confidence), 3),
                "bbox": list(det.bbox),
                "in_forward_corridor": bool(occ.in_forward_corridor),
                "area_ratio": round(float(occ.area_ratio), 4),
                "azimuth_offset_deg": rel_az,
                "matches_mission_interest": bool(matched_target),
                "rationale": matched_rationale,
            }
            if matched_target:
                target_findings.append(item)
            else:
                hazards.append(item)

        return target_findings, hazards

    def analyze_frame(
        self,
        frame: Any,
        intelligence_focus: list[str] | None = None,
    ) -> CorridorFrameAnalysis:
        """Analyze one camera snapshot within <=500 ms and return 3D passage geometry + findings."""
        t0 = time.perf_counter()
        bgr = _decode_bgr_frame(frame)
        if bgr.shape[1] != 320 or bgr.shape[0] != 240:
            bgr_resized = cv2.resize(bgr, (320, 240), interpolation=cv2.INTER_AREA)
        else:
            bgr_resized = bgr

        gray = cv2.cvtColor(bgr_resized, cv2.COLOR_BGR2GRAY)
        visual_confidence, blur_score, brightness_score, is_frozen, quality_tags = self._evaluate_frame_quality(gray)

        if is_frozen or "dark" in quality_tags or "blur" in quality_tags or "overexposed" in quality_tags:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return CorridorFrameAnalysis(
                visual_confidence=round(visual_confidence, 3),
                blur_score=round(blur_score, 2),
                brightness_score=round(brightness_score, 2),
                is_frozen=is_frozen,
                corridor_open=False,
                is_dead_end=False,
                primary_branch=None,
                secondary_branches=[],
                structural_tags=quality_tags,
                target_findings=[],
                hazards=[],
                analysis_latency_ms=latency_ms,
            )

        edges = cv2.Canny(gray, 55, 145)
        grid, _ = self._compute_grid_scores(gray, edges)

        # Weight middle and lower-mid flight corridor bands heavily for passability
        col_scores = (
            0.22 * grid[0, :] + 0.48 * grid[1, :] + 0.30 * np.maximum(grid[2, :], grid[3, :])
        )
        # Allow a clean high-clearance peak in mid, lower-mid crouch, or upper-slope band to surface cleanly
        peak_per_col = np.maximum(
            np.maximum(grid[1, :], 0.90 * grid[3, :]),
            np.maximum(0.85 * grid[2, :], 0.85 * grid[0, :]),
        )
        effective_col_scores = np.maximum(col_scores, 0.86 * peak_per_col)

        peaks = self._find_column_peaks(effective_col_scores)
        tags: list[str] = list(quality_tags)
        target_findings, hazards = self._classify_detections(bgr_resized, intelligence_focus)

        if not peaks:
            if "dead_end" not in tags:
                tags.append("dead_end")
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return CorridorFrameAnalysis(
                visual_confidence=round(visual_confidence, 3),
                blur_score=round(blur_score, 2),
                brightness_score=round(brightness_score, 2),
                is_frozen=False,
                corridor_open=False,
                is_dead_end=True,
                primary_branch=None,
                secondary_branches=[],
                structural_tags=tags,
                target_findings=target_findings,
                hazards=hazards,
                analysis_latency_ms=latency_ms,
            )

        candidates = [self._build_branch_candidate(p, grid, effective_col_scores) for p in peaks]
        # Rank primary continuation: combine openness score and gentle preference for central alignment
        candidates.sort(
            key=lambda b: (b.openness_score - 0.0025 * abs(b.azimuth_offset_deg)),
            reverse=True,
        )
        primary = candidates[0]
        secondary = candidates[1:]

        # Structural geometry tags
        if abs(primary.azimuth_offset_deg) >= 34.0:
            tags.append("turn_right" if primary.azimuth_offset_deg > 0 else "turn_left")
        elif abs(primary.azimuth_offset_deg) >= 14.0:
            tags.append("curve_right" if primary.azimuth_offset_deg > 0 else "curve_left")

        if primary.elevation_offset_m < -0.2:
            tags.append("low_overhang")
        elif primary.elevation_offset_m > 0.2:
            tags.append("slope_up")

        if secondary:
            tags.append("intersection")

        if self._prev_estimated_width_m is not None:
            if primary.estimated_width_m <= self._prev_estimated_width_m - 0.7:
                tags.append("narrowing")
            elif primary.estimated_width_m >= self._prev_estimated_width_m + 0.7:
                tags.append("widening")
        self._prev_estimated_width_m = primary.estimated_width_m

        # Avoid non-target hazards blocking direct forward lane if space exists
        blocking_center_hazards = [
            hz for hz in hazards if hz.get("in_forward_corridor") and float(hz.get("area_ratio", 0.0)) > 0.06
        ]
        corridor_open = True
        is_dead_end = False
        if blocking_center_hazards:
            # Steer around hazard toward clearer side if primary was centered
            if abs(primary.azimuth_offset_deg) < 15.0:
                left_score = float(effective_col_scores[0] + effective_col_scores[1])
                right_score = float(effective_col_scores[3] + effective_col_scores[4])
                if max(left_score, right_score) >= self.openness_threshold:
                    steer_deg = -26.0 if left_score > right_score else 26.0
                    primary.azimuth_offset_deg = steer_deg
                    tags.append("hazard_bypass")
                elif max(float(hz.get("area_ratio", 0.0)) for hz in blocking_center_hazards) >= 0.45:
                    corridor_open = False
                    is_dead_end = True
                    tags.append("dead_end")

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return CorridorFrameAnalysis(
            visual_confidence=round(visual_confidence, 3),
            blur_score=round(blur_score, 2),
            brightness_score=round(brightness_score, 2),
            is_frozen=False,
            corridor_open=corridor_open,
            is_dead_end=is_dead_end,
            primary_branch=primary if corridor_open else None,
            secondary_branches=secondary if corridor_open else [],
            structural_tags=tags,
            target_findings=target_findings,
            hazards=hazards,
            analysis_latency_ms=latency_ms,
        )
