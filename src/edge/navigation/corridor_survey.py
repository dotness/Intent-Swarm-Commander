"""Edge 3D corridor path discovery state machine, breadcrumb navigation, failsafe timer, and overrides."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
import math
import time
from typing import Any
import uuid

from src.edge.telemetry.publisher import encode_corridor_frame_jpeg
from src.edge.vision.corridor_analyzer import CorridorFrameAnalysis, CorridorVisualAnalyzer
from src.uservice.telemetry.models.contract.events import corridor_phase_to_flight_status

logger = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_000.0


def _norm_heading(heading_deg: float) -> float:
    h = float(heading_deg) % 360.0
    return 0.0 if h >= 360.0 or h < 0.0 else h


def enu_offset_to_latlon(
    origin_lat: float,
    origin_lon: float,
    rel_x_east_m: float,
    rel_y_north_m: float,
) -> tuple[float, float]:
    """Convert local ENU meters relative to mission origin into WGS84 (lat, lon)."""
    dlat = (float(rel_y_north_m) / _EARTH_RADIUS_M) * (180.0 / math.pi)
    cos_lat = max(0.05, math.cos(math.radians(float(origin_lat))))
    dlon = (float(rel_x_east_m) / (_EARTH_RADIUS_M * cos_lat)) * (180.0 / math.pi)
    return float(origin_lat) + dlat, float(origin_lon) + dlon


def latlon_to_enu_offset(
    origin_lat: float,
    origin_lon: float,
    lat: float,
    lon: float,
) -> tuple[float, float]:
    """Convert WGS84 (lat, lon) into local ENU meters (rel_x_east_m, rel_y_north_m) from origin."""
    cos_lat = max(0.05, math.cos(math.radians(float(origin_lat))))
    north_m = math.radians(float(lat) - float(origin_lat)) * _EARTH_RADIUS_M
    east_m = math.radians(float(lon) - float(origin_lon)) * _EARTH_RADIUS_M * cos_lat
    return east_m, north_m


def distance_3d_m(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Compute cumulative 3D Euclidean segment distance sqrt(dx^2 + dy^2 + dz^2)."""
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2)


class SurveyPhase(str, Enum):
    """Canonical 11-state 3D corridor discovery phase matching data-model.md."""

    INITIALIZING = "initializing"
    INITIAL_LOOK_AROUND = "initial_look_around"
    IMPASSABLE_START = "impassable_start"
    OUTBOUND_DISCOVERY = "outbound_discovery"
    BOUNDARY_HOLD = "boundary_hold"
    TURN_LOOK_AROUND = "turn_look_around"
    RETURNING = "returning"
    RETURN_BLOCKED_HOLD = "return_blocked_hold"
    EMERGENCY_HOLD = "emergency_hold"
    COMPLETED = "completed"
    COMPLETED_HOLDING = "completed_holding"


@dataclass
class CorridorSurveyConfig:
    """Runtime parameters governing an edge corridor survey."""

    survey_id: str
    command_id: str
    swarm_id: str
    project_id: str = "default-theater"
    drone_id: str = "drone-1"
    staging_hold_drone_ids: list[str] = field(default_factory=list)
    entry_altitude_m: float = 2.5
    target_distance_m: float = 20.0
    distance_defaulted: bool = False
    return_to_origin: bool = True
    corridor_descriptor: str = "corridor"
    intelligence_focus: list[str] = field(default_factory=list)
    min_altitude_m: float = 1.2
    max_altitude_m: float = 8.0
    cruise_speed_ms: float = 1.5
    look_around_steps: int = 8
    snapshot_interval_s: float = 0.4
    guidance_timeout_s: float = 5.0
    segment_step_m: float = 2.5
    cleared_segment_m: float = 4.0
    yaw_settle_s: float = 0.35
    step_sleep_s: float = 0.35
    min_visual_confidence: float = 0.40
    min_battery_reserve_pct: float = 20.0
    battery_drain_pct_per_meter: float = 0.45


@dataclass
class PathBreadcrumb3D:
    """Verified 3D relative breadcrumb for outbound tracking and reverse-path return."""

    index: int
    rel_x_m: float
    rel_y_m: float
    rel_z_m: float
    heading_deg: float
    cumulative_distance_m: float
    estimated_width_m: float | None
    estimated_height_m: float | None
    snapshot_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "rel_x_m": round(self.rel_x_m, 3),
            "rel_y_m": round(self.rel_y_m, 3),
            "rel_z_m": round(self.rel_z_m, 3),
            "heading_deg": round(_norm_heading(self.heading_deg), 2),
            "cumulative_distance_m": round(self.cumulative_distance_m, 3),
            "estimated_width_m": self.estimated_width_m,
            "estimated_height_m": self.estimated_height_m,
            "snapshot_id": self.snapshot_id,
        }


@dataclass
class EdgeTrajectoryInstruction:
    """Edge-authored 3D incremental guidance command linked to triggering snapshots."""

    instruction_id: str
    action: str
    target_rel_x_m: float
    target_rel_y_m: float
    target_rel_z_m: float
    commanded_heading_deg: float
    cleared_distance_m: float
    speed_ms: float
    trigger_snapshot_ids: list[str]
    rationale: str
    analysis_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction_id": self.instruction_id,
            "action": self.action,
            "target_rel_x_m": round(self.target_rel_x_m, 3),
            "target_rel_y_m": round(self.target_rel_y_m, 3),
            "target_rel_z_m": round(self.target_rel_z_m, 3),
            "commanded_heading_deg": round(_norm_heading(self.commanded_heading_deg), 2),
            "cleared_distance_m": round(self.cleared_distance_m, 3),
            "speed_ms": round(self.speed_ms, 3),
            "trigger_snapshot_ids": list(self.trigger_snapshot_ids),
            "rationale": self.rationale,
            "analysis_latency_ms": round(self.analysis_latency_ms, 2),
        }


class CorridorSurveyController:
    """Autonomous 3D corridor path discovery controller decoupled from Point-A-to-B FlightController."""

    def __init__(
        self,
        *,
        config: CorridorSurveyConfig,
        camera: Any,
        analyzer: CorridorVisualAnalyzer,
        drone: Any,
        telemetry_publisher: Any = None,
        telemetry_state: dict[str, Any] | None = None,
    ) -> None:
        if drone is None:
            raise ValueError("CorridorSurveyController requires an attached drone controller")
        self.config = config
        self.camera = camera
        self.analyzer = analyzer
        self.drone = drone
        self.telemetry_publisher = telemetry_publisher
        self.telemetry_state = telemetry_state

        self.phase: SurveyPhase = SurveyPhase.INITIALIZING
        self.status: str = "dispatched"
        self.completion_reason: str | None = None

        self.origin_lat: float = 47.39775
        self.origin_lon: float = 8.54560
        self.origin_abs_alt_m: float = 500.0
        self.ground_alt_m: float = 500.0

        self.rel_x_m: float = 0.0
        self.rel_y_m: float = 0.0
        self.rel_z_m: float = float(config.entry_altitude_m)
        self.heading_deg: float = 0.0
        self.battery_pct: float = 100.0
        self.surveyed_distance_m: float = 0.0
        self.cleared_horizon_m: float = 0.0

        self.snapshot_count: int = 0
        self.decision_count: int = 0
        self.finding_count: int = 0
        self.breadcrumbs: list[PathBreadcrumb3D] = []
        self.structural_features: list[str] = []
        self.unexplored_branches: list[dict[str, Any]] = []
        self.last_instruction: EdgeTrajectoryInstruction | None = None

        self._running: bool = False
        self._recall_requested: bool = False
        self._emergency_abort_requested: bool = False
        self._outbound_stop_reason: str | None = None
        self._last_guidance_mono: float = time.monotonic()
        self._consecutive_degraded: int = 0
        self._origin_anchored: bool = False

    def _read_pose_snapshot(self) -> tuple[float, float, float, float, float, float]:
        """Read current (lat, lon, abs_alt_m, rel_alt_m, heading_deg, battery_pct) from drone or telemetry_state."""
        drone_lat = float(getattr(self.drone, "lat", self.origin_lat))
        drone_lon = float(getattr(self.drone, "lon", self.origin_lon))
        drone_abs_alt = float(getattr(self.drone, "abs_alt", self.origin_abs_alt_m))
        drone_rel_alt = float(getattr(self.drone, "rel_alt", self.rel_z_m))
        drone_heading = float(getattr(self.drone, "heading_deg", self.heading_deg))
        drone_battery = float(getattr(self.drone, "battery_pct", self.battery_pct))

        if self.telemetry_state is not None:
            pos = self.telemetry_state.get("position") or {}
            raw_lat = pos.get("lat")
            raw_lon = pos.get("lon")
            gps_valid = (
                raw_lat is not None
                and raw_lon is not None
                and not (float(raw_lat) == 0.0 and float(raw_lon) == 0.0)
            )
            lat = float(raw_lat) if gps_valid else drone_lat
            lon = float(raw_lon) if gps_valid else drone_lon
            raw_alt = pos.get("alt")
            abs_alt = float(raw_alt) if (raw_alt is not None and float(raw_alt) != 0.0) else drone_abs_alt
            raw_rel = pos.get("rel_alt")
            rel_alt = float(raw_rel) if raw_rel is not None else drone_rel_alt
            raw_hdg = self.telemetry_state.get("heading")
            heading = _norm_heading(float(raw_hdg) if raw_hdg is not None else drone_heading)
            raw_bat = self.telemetry_state.get("battery")
            battery = max(0.0, min(100.0, float(raw_bat) if raw_bat is not None else drone_battery))
            return lat, lon, abs_alt, rel_alt, heading, battery

        return (
            drone_lat,
            drone_lon,
            drone_abs_alt,
            drone_rel_alt,
            _norm_heading(drone_heading),
            max(0.0, min(100.0, drone_battery)),
        )

    def anchor_origin(self) -> dict[str, Any]:
        """Anchor local 3D ENU coordinate frame at current mission start coordinates."""
        if self._origin_anchored:
            return {
                "lat": self.origin_lat,
                "lon": self.origin_lon,
                "abs_alt_m": self.origin_abs_alt_m,
                "ground_alt_m": self.ground_alt_m,
            }
        lat, lon, abs_alt, rel_alt, heading, battery = self._read_pose_snapshot()
        self.origin_lat = lat
        self.origin_lon = lon
        self.origin_abs_alt_m = abs_alt
        self.ground_alt_m = abs_alt - rel_alt
        self.rel_x_m = 0.0
        self.rel_y_m = 0.0
        self.rel_z_m = self.clamp_altitude_m(self.config.entry_altitude_m)
        self.heading_deg = heading
        self.battery_pct = battery
        self._origin_anchored = True
        return {
            "lat": lat,
            "lon": lon,
            "abs_alt_m": abs_alt,
            "ground_alt_m": self.ground_alt_m,
        }

    def clamp_altitude_m(self, target_alt_m: float) -> float:
        """Strictly constrain 3D vertical altitude target within configured [min_altitude_m, max_altitude_m] (`FR-021`)."""
        return round(
            max(self.config.min_altitude_m, min(self.config.max_altitude_m, float(target_alt_m))),
            3,
        )

    def _safe_return_reserve_pct(self) -> float:
        """Compute dynamic safe-return battery reserve proportional to discovered 3D path length (`FR-009`, `FR-021`)."""
        return self.config.min_battery_reserve_pct + (
            self.surveyed_distance_m * self.config.battery_drain_pct_per_meter
        )

    async def _ensure_airborne_at_entry(self) -> None:
        """Arm and ascend/hold safely at configured `entry_altitude_m` at origin."""
        entry_alt = self.clamp_altitude_m(self.config.entry_altitude_m)
        self.rel_z_m = entry_alt
        if self.drone is None or not hasattr(self.drone, "action"):
            return
        armed = bool(getattr(self.drone, "armed", False))
        in_air = bool(getattr(self.drone, "in_air", False))
        if self.telemetry_state is not None:
            armed = bool(self.telemetry_state.get("armed", armed))
            in_air = bool(self.telemetry_state.get("in_air", in_air))
        if not armed:
            await self.drone.action.set_takeoff_altitude(entry_alt)
            await self.drone.action.arm()
            await self.drone.action.takeoff()
            if self.config.yaw_settle_s > 0:
                await asyncio.sleep(min(2.0, self.config.yaw_settle_s * 2.0))
        elif not in_air:
            await self.drone.action.set_takeoff_altitude(entry_alt)
            await self.drone.action.takeoff()
            if self.config.yaw_settle_s > 0:
                await asyncio.sleep(min(2.0, self.config.yaw_settle_s * 2.0))

    async def _move_relative_3d(
        self,
        rel_x_m: float,
        rel_y_m: float,
        rel_z_m: float,
        heading_deg: float,
    ) -> None:
        """Command MAVSDK goto_location in local ENU coordinates anchored to mission origin."""
        clamped_z = self.clamp_altitude_m(rel_z_m)
        target_heading = _norm_heading(heading_deg)
        lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, rel_x_m, rel_y_m)
        abs_alt = self.ground_alt_m + clamped_z
        if self.drone is not None and hasattr(self.drone, "action"):
            await self.drone.action.goto_location(lat, lon, abs_alt, target_heading)
        if self.config.yaw_settle_s > 0 and self.telemetry_state is not None:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                _, _, _, _, live_hdg, _ = self._read_pose_snapshot()
                err = abs(((live_hdg - target_heading + 180.0) % 360.0) - 180.0)
                if err <= 10.0:
                    break
                await asyncio.sleep(0.05)
        self.rel_x_m = float(rel_x_m)
        self.rel_y_m = float(rel_y_m)
        self.rel_z_m = float(clamped_z)
        self.heading_deg = target_heading

    async def _emit_phase_transition(
        self,
        to_phase: SurveyPhase,
        reason: str,
        *,
        status: str | None = None,
    ) -> None:
        from_phase = self.phase
        self.phase = to_phase
        if status is not None:
            self.status = status
        flight_status = corridor_phase_to_flight_status(to_phase.value)
        if self.telemetry_state is not None:
            self.telemetry_state["status"] = flight_status

        if self.telemetry_publisher is None:
            return
        lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, self.rel_x_m, self.rel_y_m)
        await self.telemetry_publisher.publish_corridor_event(
            survey_event_type="corridor_phase",
            flight_status=flight_status,
            lat=lat,
            lon=lon,
            alt_m=self.ground_alt_m + self.rel_z_m,
            heading_deg=self.heading_deg,
            speed_ms=self.config.cruise_speed_ms if to_phase == SurveyPhase.OUTBOUND_DISCOVERY else 0.0,
            battery_pct=self.battery_pct,
            mission_id=self.config.command_id,
            drone_id=self.config.drone_id,
            payload={
                "survey_id": self.config.survey_id,
                "from_phase": from_phase.value,
                "to_phase": to_phase.value,
                "flight_status": flight_status,
                "reason": reason,
                "rel_x_m": round(self.rel_x_m, 3),
                "rel_y_m": round(self.rel_y_m, 3),
                "rel_z_m": round(self.rel_z_m, 3),
                "heading_deg": round(self.heading_deg, 2),
                "cumulative_distance_m": round(self.surveyed_distance_m, 3),
                "staging_hold_drone_ids": list(self.config.staging_hold_drone_ids),
            },
        )

    async def _capture_and_analyze(
        self,
        *,
        phase: SurveyPhase,
        heading_deg: float,
    ) -> tuple[str, CorridorFrameAnalysis]:
        """Read one camera frame, run sub-500ms analysis, upload/publish full snapshot (`FR-020`)."""
        raw_frame = None
        for _ in range(3):
            raw_frame = await asyncio.to_thread(self.camera.read_frame)
            if raw_frame is not None:
                break
            await asyncio.sleep(0.02)
        if raw_frame is None:
            return (
                str(uuid.uuid4()),
                CorridorFrameAnalysis(
                    visual_confidence=0.0,
                    blur_score=0.0,
                    brightness_score=0.0,
                    is_frozen=False,
                    corridor_open=False,
                    is_dead_end=False,
                    structural_tags=["camera_unavailable"],
                    analysis_latency_ms=0.0,
                ),
            )
        analysis = await asyncio.to_thread(
            self.analyzer.analyze_frame,
            raw_frame,
            intelligence_focus=self.config.intelligence_focus,
        )
        raw_jpeg = await asyncio.to_thread(encode_corridor_frame_jpeg, raw_frame)

        self.snapshot_count += 1
        snap_id = str(uuid.uuid4())
        lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, self.rel_x_m, self.rel_y_m)

        findings_payload: list[dict[str, Any]] = []
        for tf in analysis.target_findings:
            self.finding_count += 1
            findings_payload.append({
                "finding_id": str(uuid.uuid4()),
                "finding_type": "target_interest",
                "label": str(tf["label"]),
                "confidence": float(tf["confidence"]),
                "matches_mission_interest": True,
                "rel_x_m": round(self.rel_x_m, 3),
                "rel_y_m": round(self.rel_y_m, 3),
                "rel_z_m": round(self.rel_z_m, 3),
                "heading_deg": round(_norm_heading(heading_deg + float(tf.get("azimuth_offset_deg", 0.0))), 2),
                "cumulative_distance_m": round(self.surveyed_distance_m, 3),
                "details": tf,
            })
        for hz in analysis.hazards:
            self.finding_count += 1
            findings_payload.append({
                "finding_id": str(uuid.uuid4()),
                "finding_type": "hazard" if hz.get("in_forward_corridor") else "obstacle",
                "label": str(hz["label"]),
                "confidence": float(hz["confidence"]),
                "matches_mission_interest": False,
                "rel_x_m": round(self.rel_x_m, 3),
                "rel_y_m": round(self.rel_y_m, 3),
                "rel_z_m": round(self.rel_z_m, 3),
                "heading_deg": round(_norm_heading(heading_deg + float(hz.get("azimuth_offset_deg", 0.0))), 2),
                "cumulative_distance_m": round(self.surveyed_distance_m, 3),
                "details": hz,
            })

        for sec in analysis.secondary_branches:
            sec_heading = _norm_heading(heading_deg + float(sec.azimuth_offset_deg))
            branch_rec = {
                "relative_pose": {
                    "rel_x_m": round(self.rel_x_m, 3),
                    "rel_y_m": round(self.rel_y_m, 3),
                    "rel_z_m": round(self.rel_z_m, 3),
                },
                "heading_deg": round(sec_heading, 2),
                "snapshot_id": snap_id,
                "estimated_width_m": sec.estimated_width_m,
            }
            self.unexplored_branches.append(branch_rec)
            self.finding_count += 1
            findings_payload.append({
                "finding_id": str(uuid.uuid4()),
                "finding_type": "side_branch",
                "label": "unexplored_branch",
                "confidence": min(1.0, max(0.0, float(sec.openness_score))),
                "matches_mission_interest": False,
                "rel_x_m": round(self.rel_x_m, 3),
                "rel_y_m": round(self.rel_y_m, 3),
                "rel_z_m": round(self.rel_z_m, 3),
                "heading_deg": round(sec_heading, 2),
                "cumulative_distance_m": round(self.surveyed_distance_m, 3),
                "details": branch_rec,
            })

        for tag in analysis.structural_tags:
            if tag not in self.structural_features:
                self.structural_features.append(tag)

        if self.telemetry_publisher is not None:
            est_w = analysis.primary_branch.estimated_width_m if analysis.primary_branch else None
            est_h = analysis.primary_branch.estimated_height_m if analysis.primary_branch else None
            await self.telemetry_publisher.publish_corridor_snapshot(
                survey_id=self.config.survey_id,
                sequence_num=self.snapshot_count,
                phase=phase.value,
                rel_x_m=self.rel_x_m,
                rel_y_m=self.rel_y_m,
                rel_z_m=self.rel_z_m,
                heading_deg=heading_deg,
                cumulative_distance_m=self.surveyed_distance_m,
                visual_confidence=analysis.visual_confidence,
                corridor_open=analysis.corridor_open,
                analysis_latency_ms=analysis.analysis_latency_ms,
                estimated_width_m=est_w,
                estimated_height_m=est_h,
                structural_tags=analysis.structural_tags,
                findings=findings_payload,
                snapshot_id=snap_id,
                snapshot_bytes=raw_jpeg,
                lat=lat,
                lon=lon,
                alt_m=self.ground_alt_m + self.rel_z_m,
                speed_ms=self.config.cruise_speed_ms if phase == SurveyPhase.OUTBOUND_DISCOVERY else 0.0,
                battery_pct=self.battery_pct,
                mission_id=self.config.command_id,
                drone_id=self.config.drone_id,
            )

        return snap_id, analysis

    async def _emit_trajectory_decision(
        self,
        *,
        action: str,
        from_phase: SurveyPhase,
        to_phase: SurveyPhase,
        target_rel_x_m: float,
        target_rel_y_m: float,
        target_rel_z_m: float,
        commanded_heading_deg: float,
        cleared_distance_m: float,
        speed_ms: float,
        trigger_snapshot_ids: list[str],
        analysis_latency_ms: float | None,
        rationale: str,
        breadcrumb: PathBreadcrumb3D | None = None,
    ) -> EdgeTrajectoryInstruction:
        self.decision_count += 1
        decision_id = str(uuid.uuid4())
        clamped_z = self.clamp_altitude_m(target_rel_z_m)
        cmd_heading = _norm_heading(commanded_heading_deg)
        instr = EdgeTrajectoryInstruction(
            instruction_id=decision_id,
            action=action,
            target_rel_x_m=target_rel_x_m,
            target_rel_y_m=target_rel_y_m,
            target_rel_z_m=clamped_z,
            commanded_heading_deg=cmd_heading,
            cleared_distance_m=cleared_distance_m,
            speed_ms=speed_ms,
            trigger_snapshot_ids=list(trigger_snapshot_ids),
            rationale=rationale,
            analysis_latency_ms=float(analysis_latency_ms or 0.0),
        )
        self.last_instruction = instr
        self._last_guidance_mono = time.monotonic()

        if self.telemetry_publisher is not None:
            lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, self.rel_x_m, self.rel_y_m)
            await self.telemetry_publisher.publish_corridor_event(
                survey_event_type="corridor_trajectory",
                flight_status=corridor_phase_to_flight_status(to_phase.value),
                lat=lat,
                lon=lon,
                alt_m=self.ground_alt_m + self.rel_z_m,
                heading_deg=cmd_heading,
                speed_ms=speed_ms,
                battery_pct=self.battery_pct,
                mission_id=self.config.command_id,
                drone_id=self.config.drone_id,
                payload={
                    "survey_id": self.config.survey_id,
                    "decision_id": decision_id,
                    "sequence_num": self.decision_count,
                    "action": action,
                    "from_phase": from_phase.value,
                    "to_phase": to_phase.value,
                    "target_rel_x_m": round(target_rel_x_m, 3),
                    "target_rel_y_m": round(target_rel_y_m, 3),
                    "target_rel_z_m": round(clamped_z, 3),
                    "commanded_heading_deg": round(cmd_heading, 2),
                    "cleared_distance_m": round(cleared_distance_m, 3),
                    "speed_ms": round(speed_ms, 3),
                    "trigger_snapshot_ids": list(trigger_snapshot_ids),
                    "analysis_latency_ms": analysis_latency_ms,
                    "rationale": rationale,
                    "breadcrumb": breadcrumb.to_dict() if breadcrumb is not None else None,
                },
            )
        return instr

    async def _emit_final_report(self) -> None:
        if self.telemetry_publisher is None:
            return
        lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, self.rel_x_m, self.rel_y_m)
        await self.telemetry_publisher.publish_corridor_event(
            survey_event_type="corridor_report",
            flight_status=corridor_phase_to_flight_status(self.phase.value),
            lat=lat,
            lon=lon,
            alt_m=self.ground_alt_m + self.rel_z_m,
            heading_deg=self.heading_deg,
            speed_ms=0.0,
            battery_pct=self.battery_pct,
            mission_id=self.config.command_id,
            drone_id=self.config.drone_id,
            payload={
                "survey_id": self.config.survey_id,
                "status": self.status,
                "completion_reason": self.completion_reason or "distance_reached",
                "surveyed_distance_m": round(self.surveyed_distance_m, 3),
                "requested_distance_m": round(self.config.target_distance_m, 3),
                "distance_defaulted": bool(self.config.distance_defaulted),
                "discovered_path": [b.to_dict() for b in self.breadcrumbs],
                "structural_features": list(self.structural_features),
                "unexplored_branches": list(self.unexplored_branches),
                "snapshot_count": self.snapshot_count,
                "decision_count": self.decision_count,
                "finding_count": self.finding_count,
            },
        )

    async def run_initial_look_around(self) -> tuple[bool, EdgeTrajectoryInstruction | None]:
        """Execute mandatory 8-heading 360-degree sweep while hovering at origin before any advance (`FR-002`, `FR-003`, `SC-002`)."""
        if hasattr(self.analyzer, "reset_temporal_state"):
            self.analyzer.reset_temporal_state()
        self.anchor_origin()
        await self._ensure_airborne_at_entry()
        await self._emit_phase_transition(
            SurveyPhase.INITIAL_LOOK_AROUND,
            "Hovering at origin for mandatory 360-deg visual sweep before corridor entry",
            status="active",
        )

        steps = max(4, int(self.config.look_around_steps))
        step_deg = 360.0 / float(steps)
        candidates: list[tuple[float, float, str, CorridorFrameAnalysis]] = []

        for idx in range(steps):
            if self._emergency_abort_requested or self._recall_requested:
                return False, None
            sweep_heading = _norm_heading(idx * step_deg)
            await self._move_relative_3d(0.0, 0.0, self.rel_z_m, sweep_heading)
            if self.config.yaw_settle_s > 0:
                await asyncio.sleep(self.config.yaw_settle_s)
            snap_id, analysis = await self._capture_and_analyze(
                phase=SurveyPhase.INITIAL_LOOK_AROUND,
                heading_deg=sweep_heading,
            )
            if (
                analysis.corridor_open
                and analysis.visual_confidence >= self.config.min_visual_confidence
                and analysis.primary_branch is not None
            ):
                best_heading = _norm_heading(sweep_heading + analysis.primary_branch.azimuth_offset_deg)
                candidates.append((analysis.primary_branch.openness_score, best_heading, snap_id, analysis))

        if not candidates:
            if self.drone is not None and hasattr(self.drone, "action"):
                await self.drone.action.hold()
            self.completion_reason = "impassable_start"
            await self._emit_phase_transition(
                SurveyPhase.IMPASSABLE_START,
                "All 360-deg headings blocked or below confidence; holding safely at origin",
                status="impassable_start",
            )
            await self._emit_final_report()
            return False, None

        candidates.sort(key=lambda item: item[0], reverse=True)
        _, chosen_heading, trigger_snap_id, best_analysis = candidates[0]
        assert best_analysis.primary_branch is not None
        target_alt = self.clamp_altitude_m(self.rel_z_m + best_analysis.primary_branch.elevation_offset_m)
        rad = math.radians(chosen_heading)
        step_m = min(self.config.cleared_segment_m, self.config.target_distance_m)
        target_x = step_m * math.sin(rad)
        target_y = step_m * math.cos(rad)
        self.cleared_horizon_m = step_m

        origin_bc = PathBreadcrumb3D(
            index=1,
            rel_x_m=0.0,
            rel_y_m=0.0,
            rel_z_m=self.rel_z_m,
            heading_deg=chosen_heading,
            cumulative_distance_m=0.0,
            estimated_width_m=best_analysis.primary_branch.estimated_width_m,
            estimated_height_m=best_analysis.primary_branch.estimated_height_m,
            snapshot_id=trigger_snap_id,
        )
        self.breadcrumbs.append(origin_bc)

        prev_phase = self.phase
        await self._emit_phase_transition(
            SurveyPhase.OUTBOUND_DISCOVERY,
            f"Validated open heading {chosen_heading:.1f} deg; clearing initial segment ({step_m:.1f}m)",
        )
        instr = await self._emit_trajectory_decision(
            action="initial_trajectory",
            from_phase=prev_phase,
            to_phase=SurveyPhase.OUTBOUND_DISCOVERY,
            target_rel_x_m=target_x,
            target_rel_y_m=target_y,
            target_rel_z_m=target_alt,
            commanded_heading_deg=chosen_heading,
            cleared_distance_m=step_m,
            speed_ms=self.config.cruise_speed_ms,
            trigger_snapshot_ids=[trigger_snap_id],
            analysis_latency_ms=best_analysis.analysis_latency_ms,
            rationale=f"Initial 360-deg look-around cleared heading {chosen_heading:.1f} deg.",
            breadcrumb=origin_bc,
        )
        await self._move_relative_3d(0.0, 0.0, target_alt, chosen_heading)
        return True, instr

    async def step_outbound(self) -> str:
        """Execute a single outbound continuous 3D rolling flight & snapshot analysis tick."""
        if self._emergency_abort_requested:
            return "emergency_abort"
        if self._recall_requested:
            return "operator_recall"

        # Refresh live battery reserve telemetry before continuing (`FR-009`, `FR-021`)
        _, _, _, _, _, live_battery = self._read_pose_snapshot()
        self.battery_pct = live_battery
        if self.battery_pct <= self._safe_return_reserve_pct():
            self._outbound_stop_reason = "endurance_reserve"
            return "endurance_reserve"

        if self.surveyed_distance_m >= self.config.target_distance_m:
            self._outbound_stop_reason = "distance_reached" if self.config.return_to_origin else "far_end_hold"
            return self._outbound_stop_reason

        # Real guidance watchdog timeout: hold at cleared boundary and reverse-return (`SC-004`, `SC-007`)
        if (time.monotonic() - self._last_guidance_mono) >= self.config.guidance_timeout_s:
            if hasattr(self.drone, "action"):
                await self.drone.action.hold()
            if self.phase != SurveyPhase.BOUNDARY_HOLD:
                await self._emit_phase_transition(
                    SurveyPhase.BOUNDARY_HOLD,
                    "Cleared segment boundary guidance timeout reached; holding before failsafe return",
                )
            self._outbound_stop_reason = "guidance_timeout_failsafe"
            return "guidance_timeout_failsafe"

        snap_id, analysis = await self._capture_and_analyze(
            phase=self.phase,
            heading_deg=self.heading_deg,
        )

        # Degraded visual failsafe: pause -> recapture -> failsafe return (`FR-015`)
        if analysis.visual_confidence < self.config.min_visual_confidence:
            self._consecutive_degraded += 1
            if self.drone is not None and hasattr(self.drone, "action"):
                await self.drone.action.hold()
            if self.phase != SurveyPhase.BOUNDARY_HOLD:
                await self._emit_phase_transition(
                    SurveyPhase.BOUNDARY_HOLD,
                    "Degraded visual snapshot; pausing to recapture before advancing",
                )
            if self._consecutive_degraded >= 2 or (
                time.monotonic() - self._last_guidance_mono
            ) >= self.config.guidance_timeout_s:
                self._outbound_stop_reason = "visual_degraded"
                return "visual_degraded"
            if self.config.step_sleep_s > 0:
                await asyncio.sleep(self.config.step_sleep_s)
            return "recapture"

        self._consecutive_degraded = 0

        if analysis.is_dead_end or not analysis.corridor_open or analysis.primary_branch is None:
            # Corner check: run localized turn_look_around before declaring dead end
            sweep_angles = [self.heading_deg, _norm_heading(self.heading_deg + 45.0), _norm_heading(self.heading_deg - 45.0)]
            if self.phase != SurveyPhase.TURN_LOOK_AROUND:
                await self._emit_phase_transition(
                    SurveyPhase.TURN_LOOK_AROUND,
                    "Checking side angles at apparent passage termination before declaring dead end",
                )
            best_turn: tuple[float, float, str, CorridorFrameAnalysis] | None = None
            for ang in sweep_angles:
                await self._move_relative_3d(self.rel_x_m, self.rel_y_m, self.rel_z_m, ang)
                t_snap_id, t_ana = await self._capture_and_analyze(
                    phase=SurveyPhase.TURN_LOOK_AROUND,
                    heading_deg=ang,
                )
                if (
                    t_ana.corridor_open
                    and t_ana.visual_confidence >= self.config.min_visual_confidence
                    and t_ana.primary_branch is not None
                ):
                    cand_score = t_ana.primary_branch.openness_score
                    if best_turn is None or cand_score > best_turn[0]:
                        best_turn = (
                            cand_score,
                            _norm_heading(ang + t_ana.primary_branch.azimuth_offset_deg),
                            t_snap_id,
                            t_ana,
                        )

            if best_turn is None:
                self._outbound_stop_reason = "dead_end"
                return "dead_end"

            _, next_heading, snap_id, analysis = best_turn

        else:
            next_heading = _norm_heading(self.heading_deg + analysis.primary_branch.azimuth_offset_deg)

        assert analysis.primary_branch is not None
        branch = analysis.primary_branch

        # If returning from hold, transition cleanly back to outbound_discovery
        from_phase = self.phase
        if self.phase != SurveyPhase.OUTBOUND_DISCOVERY:
            await self._emit_phase_transition(
                SurveyPhase.OUTBOUND_DISCOVERY,
                "Validated corridor continuation received; resuming rolling 3D flight",
            )

        remaining = max(0.2, self.config.target_distance_m - self.surveyed_distance_m)
        step_dist = min(self.config.segment_step_m, remaining)
        requested_z = self.rel_z_m + branch.elevation_offset_m
        next_z = self.clamp_altitude_m(requested_z)
        rad = math.radians(next_heading)
        # Project 3D step so horizontal + vertical delta sums to 3D path increment
        dz = next_z - self.rel_z_m
        horiz = math.sqrt(max(0.0, step_dist ** 2 - dz ** 2))
        next_x = self.rel_x_m + horiz * math.sin(rad)
        next_y = self.rel_y_m + horiz * math.cos(rad)

        actual_step_3d = distance_3d_m(
            (self.rel_x_m, self.rel_y_m, self.rel_z_m),
            (next_x, next_y, next_z),
        )
        new_cumulative = self.surveyed_distance_m + actual_step_3d
        self.cleared_horizon_m = max(self.cleared_horizon_m, new_cumulative + self.config.cleared_segment_m)

        action_name = "branch_select" if analysis.secondary_branches else (
            "altitude_adjust" if abs(dz) >= 0.1 else "trajectory_update"
        )
        next_bc = PathBreadcrumb3D(
            index=len(self.breadcrumbs) + 1,
            rel_x_m=next_x,
            rel_y_m=next_y,
            rel_z_m=next_z,
            heading_deg=next_heading,
            cumulative_distance_m=new_cumulative,
            estimated_width_m=branch.estimated_width_m,
            estimated_height_m=branch.estimated_height_m,
            snapshot_id=snap_id,
        )

        rationale_parts = [f"heading={next_heading:.1f}deg", f"z={next_z:.2f}m"]
        if requested_z != next_z:
            rationale_parts.append(
                f"clamped altitude to [{self.config.min_altitude_m}, {self.config.max_altitude_m}]"
            )
        if analysis.secondary_branches:
            rationale_parts.append(f"logged {len(analysis.secondary_branches)} unexplored side branch(es)")

        await self._emit_trajectory_decision(
            action=action_name,
            from_phase=from_phase,
            to_phase=SurveyPhase.OUTBOUND_DISCOVERY,
            target_rel_x_m=next_x,
            target_rel_y_m=next_y,
            target_rel_z_m=next_z,
            commanded_heading_deg=next_heading,
            cleared_distance_m=self.config.cleared_segment_m,
            speed_ms=self.config.cruise_speed_ms,
            trigger_snapshot_ids=[snap_id],
            analysis_latency_ms=analysis.analysis_latency_ms,
            rationale="; ".join(rationale_parts),
            breadcrumb=next_bc,
        )

        await self._move_relative_3d(next_x, next_y, next_z, next_heading)
        self.breadcrumbs.append(next_bc)
        self.surveyed_distance_m = new_cumulative
        if self.config.step_sleep_s > 0:
            await asyncio.sleep(self.config.step_sleep_s)

        if self.surveyed_distance_m >= self.config.target_distance_m - 1e-6:
            self._outbound_stop_reason = "distance_reached" if self.config.return_to_origin else "far_end_hold"
            return self._outbound_stop_reason
        return "continue"

    async def run_return_leg(self, reason: str) -> None:
        """Retrace verified 3D corridor breadcrumbs in reverse back to origin with return snapshot monitoring (`FR-009`, `FR-010`, `SC-005`)."""
        if not self.config.return_to_origin and reason not in (
            "operator_recall",
            "dead_end",
            "guidance_timeout_failsafe",
            "visual_degraded",
            "endurance_reserve",
        ):
            self.completion_reason = "far_end_hold"
            if self.drone is not None and hasattr(self.drone, "action"):
                await self.drone.action.hold()
            await self._emit_phase_transition(
                SurveyPhase.COMPLETED_HOLDING,
                "Target distance reached with return_to_origin=false; holding safely at far end",
                status="completed",
            )
            await self._emit_final_report()
            return

        prev_phase = self.phase
        if prev_phase != SurveyPhase.RETURNING:
            await self._emit_phase_transition(
                SurveyPhase.RETURNING,
                f"Starting reverse-path 3D breadcrumb return ({reason})",
                status="active",
            )
        action_tag = "failsafe_return" if reason in ("guidance_timeout_failsafe", "visual_degraded") else (
            "operator_recall" if reason == "operator_recall" else "return_start"
        )
        reverse_wps = list(reversed(self.breadcrumbs))
        first_target = reverse_wps[0] if reverse_wps else PathBreadcrumb3D(
            index=1,
            rel_x_m=0.0,
            rel_y_m=0.0,
            rel_z_m=self.rel_z_m,
            heading_deg=_norm_heading(self.heading_deg + 180.0),
            cumulative_distance_m=0.0,
            estimated_width_m=None,
            estimated_height_m=None,
            snapshot_id=str(uuid.uuid4()),
        )
        await self._emit_trajectory_decision(
            action=action_tag,
            from_phase=prev_phase,
            to_phase=SurveyPhase.RETURNING,
            target_rel_x_m=first_target.rel_x_m,
            target_rel_y_m=first_target.rel_y_m,
            target_rel_z_m=first_target.rel_z_m,
            commanded_heading_deg=_norm_heading(first_target.heading_deg + 180.0),
            cleared_distance_m=self.surveyed_distance_m,
            speed_ms=self.config.cruise_speed_ms,
            trigger_snapshot_ids=[first_target.snapshot_id],
            analysis_latency_ms=0.0,
            rationale=f"Reverse return initiated due to {reason}.",
        )

        for bc in reverse_wps:
            if self._emergency_abort_requested:
                return
            dx = bc.rel_x_m - self.rel_x_m
            dy = bc.rel_y_m - self.rel_y_m
            ret_heading = _norm_heading(math.degrees(math.atan2(dx, dy))) if (abs(dx) + abs(dy)) > 1e-4 else _norm_heading(bc.heading_deg + 180.0)
            await self._move_relative_3d(self.rel_x_m, self.rel_y_m, self.rel_z_m, ret_heading)
            snap_id, analysis = await self._capture_and_analyze(
                phase=SurveyPhase.RETURNING,
                heading_deg=ret_heading,
            )

            # Check for return passage blockage (`FR-010`) — verify across slight yaw offsets before halting
            if analysis.is_dead_end and not analysis.corridor_open:
                recovered = False
                for probe_hdg in (ret_heading, _norm_heading(ret_heading + 35.0), _norm_heading(ret_heading - 35.0)):
                    await self._move_relative_3d(self.rel_x_m, self.rel_y_m, self.rel_z_m, probe_hdg)
                    p_snap, p_ana = await self._capture_and_analyze(
                        phase=SurveyPhase.RETURNING,
                        heading_deg=probe_hdg,
                    )
                    if p_ana.corridor_open and not p_ana.is_dead_end:
                        snap_id, analysis, ret_heading = p_snap, p_ana, probe_hdg
                        recovered = True
                        break
                if not recovered:
                    self.completion_reason = "return_blocked"
                    if self.drone is not None and hasattr(self.drone, "action"):
                        await self.drone.action.hold()
                    await self._emit_phase_transition(
                        SurveyPhase.RETURN_BLOCKED_HOLD,
                        "Return corridor completely blocked; holding safely and alerting operator",
                        status="aborted",
                    )
                    await self._emit_final_report()
                    return

            # Minor obstacle bypass within verified corridor clearance
            target_x, target_y, target_z = bc.rel_x_m, bc.rel_y_m, bc.rel_z_m
            if analysis.primary_branch is not None:
                target_z = self.clamp_altitude_m(target_z + analysis.primary_branch.elevation_offset_m)
                if analysis.hazards and any(hz.get("in_forward_corridor") for hz in analysis.hazards):
                    perp_rad = math.radians(ret_heading + (90.0 if analysis.primary_branch.azimuth_offset_deg >= 0 else -90.0))
                    target_x += 0.35 * math.sin(perp_rad)
                    target_y += 0.35 * math.cos(perp_rad)

            await self._emit_trajectory_decision(
                action="return_segment",
                from_phase=SurveyPhase.RETURNING,
                to_phase=SurveyPhase.RETURNING,
                target_rel_x_m=target_x,
                target_rel_y_m=target_y,
                target_rel_z_m=target_z,
                commanded_heading_deg=ret_heading,
                cleared_distance_m=bc.cumulative_distance_m,
                speed_ms=self.config.cruise_speed_ms,
                trigger_snapshot_ids=[snap_id],
                analysis_latency_ms=analysis.analysis_latency_ms,
                rationale=f"Retracing breadcrumb #{bc.index} toward origin.",
            )
            await self._move_relative_3d(target_x, target_y, target_z, ret_heading)
            if self.config.step_sleep_s > 0:
                await asyncio.sleep(self.config.step_sleep_s)

        await self._move_relative_3d(0.0, 0.0, self.clamp_altitude_m(self.config.entry_altitude_m), self.heading_deg)
        if self.drone is not None and hasattr(self.drone, "action"):
            await self.drone.action.hold()
        self.completion_reason = reason
        final_status = "aborted" if reason == "operator_recall" else "completed"
        await self._emit_phase_transition(
            SurveyPhase.COMPLETED,
            f"Reverse-path return completed ({reason})",
            status=final_status,
        )
        await self._emit_final_report()

    async def recall(self, rationale: str | None = None, commander_id: str = "commander") -> dict[str, Any]:
        """Tier-1 operator override: end outbound discovery and autonomously return along verified 3D breadcrumbs (`FR-018`)."""
        self._recall_requested = True
        self._outbound_stop_reason = "operator_recall"
        prev_phase = self.phase
        await self._emit_phase_transition(
            SurveyPhase.RETURNING,
            rationale or "Operator recall command received; initiating reverse-path return",
            status="aborted",
        )
        if self.telemetry_publisher is not None:
            lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, self.rel_x_m, self.rel_y_m)
            await self.telemetry_publisher.publish_corridor_event(
                survey_event_type="corridor_override",
                flight_status=corridor_phase_to_flight_status(SurveyPhase.RETURNING.value),
                lat=lat,
                lon=lon,
                alt_m=self.ground_alt_m + self.rel_z_m,
                heading_deg=self.heading_deg,
                speed_ms=self.config.cruise_speed_ms,
                battery_pct=self.battery_pct,
                mission_id=self.config.command_id,
                drone_id=self.config.drone_id,
                payload={
                    "command_source": "operator_corridor_override",
                    "decision_authority": "commander",
                    "survey_id": self.config.survey_id,
                    "override_type": "recall",
                    "commander_id": commander_id or "commander",
                    "from_phase": prev_phase.value,
                    "to_phase": SurveyPhase.RETURNING.value,
                    "rationale": rationale or "Operator initiated safe reverse-path recall.",
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        return {"status": "recalling", "survey_id": self.config.survey_id, "phase": self.phase.value}

    async def emergency_abort(self, rationale: str | None = None, commander_id: str = "commander") -> dict[str, Any]:
        """Tier-2 operator override: immediate MAVSDK action.hold() in place with preserved intelligence (`FR-018`)."""
        self._emergency_abort_requested = True
        self._running = False
        self.completion_reason = "operator_emergency_abort"
        prev_phase = self.phase
        if self.drone is not None and hasattr(self.drone, "action"):
            await self.drone.action.hold()
        await self._emit_phase_transition(
            SurveyPhase.EMERGENCY_HOLD,
            rationale or "Operator Emergency Abort invoked; holding immediately in place",
            status="aborted",
        )
        await self._emit_trajectory_decision(
            action="operator_emergency_abort",
            from_phase=prev_phase,
            to_phase=SurveyPhase.EMERGENCY_HOLD,
            target_rel_x_m=self.rel_x_m,
            target_rel_y_m=self.rel_y_m,
            target_rel_z_m=self.rel_z_m,
            commanded_heading_deg=self.heading_deg,
            cleared_distance_m=0.0,
            speed_ms=0.0,
            trigger_snapshot_ids=[],
            analysis_latency_ms=0.0,
            rationale=rationale or "Operator invoked immediate in-place emergency abort.",
        )
        if self.telemetry_publisher is not None:
            lat, lon = enu_offset_to_latlon(self.origin_lat, self.origin_lon, self.rel_x_m, self.rel_y_m)
            await self.telemetry_publisher.publish_corridor_event(
                survey_event_type="corridor_override",
                flight_status=corridor_phase_to_flight_status(SurveyPhase.EMERGENCY_HOLD.value),
                lat=lat,
                lon=lon,
                alt_m=self.ground_alt_m + self.rel_z_m,
                heading_deg=self.heading_deg,
                speed_ms=0.0,
                battery_pct=self.battery_pct,
                mission_id=self.config.command_id,
                drone_id=self.config.drone_id,
                payload={
                    "command_source": "operator_corridor_override",
                    "decision_authority": "commander",
                    "survey_id": self.config.survey_id,
                    "override_type": "emergency_abort",
                    "commander_id": commander_id or "commander",
                    "from_phase": prev_phase.value,
                    "to_phase": SurveyPhase.EMERGENCY_HOLD.value,
                    "rationale": rationale or "Operator invoked immediate in-place emergency abort.",
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        await self._emit_final_report()
        return {"status": "aborted", "survey_id": self.config.survey_id, "phase": self.phase.value}

    async def run(self, max_ticks: int = 200) -> str | None:
        """Run full end-to-end 3D corridor survey lifecycle."""
        self._running = True
        try:
            ok, _ = await self.run_initial_look_around()
            if not ok:
                if self._recall_requested and not self._emergency_abort_requested:
                    await self.run_return_leg("operator_recall")
                return self.completion_reason

            for _ in range(max_ticks):
                if not self._running or self._emergency_abort_requested:
                    return self.completion_reason
                outcome = await self.step_outbound()
                if outcome in ("continue", "holding", "recapture"):
                    continue
                if outcome == "emergency_abort":
                    return self.completion_reason
                await self.run_return_leg(outcome)
                return self.completion_reason

            await self.run_return_leg("distance_reached")
            return self.completion_reason
        except asyncio.CancelledError:
            raise

    def get_status_summary(self) -> dict[str, Any]:
        """Return live survey status snapshot for Edge API and `/telemetry`."""
        return {
            "survey_id": self.config.survey_id,
            "command_id": self.config.command_id,
            "swarm_id": self.config.swarm_id,
            "drone_id": self.config.drone_id,
            "staging_hold_drone_ids": list(self.config.staging_hold_drone_ids),
            "phase": self.phase.value,
            "status": self.status,
            "flight_status": corridor_phase_to_flight_status(self.phase.value),
            "surveyed_distance_m": round(self.surveyed_distance_m, 3),
            "requested_distance_m": round(self.config.target_distance_m, 3),
            "rel_pose": {
                "rel_x_m": round(self.rel_x_m, 3),
                "rel_y_m": round(self.rel_y_m, 3),
                "rel_z_m": round(self.rel_z_m, 3),
            },
            "heading_deg": round(self.heading_deg, 2),
            "snapshot_count": self.snapshot_count,
            "decision_count": self.decision_count,
            "finding_count": self.finding_count,
            "completion_reason": self.completion_reason,
            "last_instruction": self.last_instruction.to_dict() if self.last_instruction else None,
        }
