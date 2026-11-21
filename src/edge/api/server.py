"""Edge communication API — receives target commands from the Swarm backend.

This lightweight HTTP server runs on the Raspberry Pi 5 and accepts
target_object_class assignments from the central Command Post.
"""

import asyncio
import logging
import os
import re
import uuid
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import Literal

logger = logging.getLogger(__name__)
_EDGE_DRONE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

from src.edge.vision.camera import CameraStream
from src.edge.vision.corridor_analyzer import CorridorVisualAnalyzer
from src.edge.vision.inference import YoloEInference
from src.edge.vision.target_matcher import EdgeTargetMatcher
from src.edge.navigation.corridor_survey import (
    CorridorSurveyConfig,
    CorridorSurveyController,
    SurveyPhase,
)
from src.edge.navigation.flight_controller import FlightController
from src.edge.telemetry.spool import EdgeSpool
from src.edge.telemetry.publisher import EdgeTelemetryPublisher
from src.uservice.analytics.operations.minio_store import MinioStore
from src.uservice.telemetry.models.contract.events import (
    SURVEY_STAGING_HOLD_STATUS,
    SwarmTelemetryEvent,
)

from mavsdk import System as MavSystem

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
import uvicorn

@dataclass
class TargetAssignment:
    target_object_class: str
    command_id: str
    confidence_threshold: float = 0.5

_current_assignment: TargetAssignment | None = None
_camera = None
_inference = None
_drone = None

_flight_controller = None
_flight_task = None
_nav_task = None
_vision_task = None
_vision_tasks: dict[str, asyncio.Task] = {}
_controllers: dict[str, FlightController] = {}
_cameras: dict[str, CameraStream] = {}
_corridor_controllers: dict[str, CorridorSurveyController] = {}
_corridor_tasks: dict[str, asyncio.Task] = {}
_telemetry_task = None
_connect_task = None
_edge_spool: EdgeSpool | None = None
_telemetry_publisher: EdgeTelemetryPublisher | None = None

_telemetry_state = {
    "status": "idle",
    "battery": 100,
    "position": {"lat": 0.0, "lon": 0.0, "alt": 0.0, "rel_alt": 0.0},
    "heading": 0.0,
    "speed": 0.0,
    "armed": False,
    "in_air": False,
}

async def _publish_loop_event(metric_type: str, lat: float, lon: float, alt_m: float) -> None:
    if _telemetry_publisher is None:
        return
    await _telemetry_publisher.publish_event(
        SwarmTelemetryEvent(
            project_id=_telemetry_publisher.project_id,
            swarm_id=_telemetry_publisher.swarm_id,
            drone_id=_telemetry_publisher.drone_id,
            metric_type=metric_type,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            heading_deg=float(_telemetry_state["heading"]) % 360.0,
            speed_ms=max(0.0, float(_telemetry_state["speed"])),
            battery_pct=max(0.0, min(100.0, float(_telemetry_state["battery"]))),
            flight_status=str(_telemetry_state["status"]),
        )
    )


async def telemetry_loop():
    if not _drone:
        return
    try:
        async def update_pos():
            async for pos in _drone.telemetry.position():
                _telemetry_state["position"]["lat"] = pos.latitude_deg
                _telemetry_state["position"]["lon"] = pos.longitude_deg
                _telemetry_state["position"]["alt"] = pos.absolute_altitude_m
                _telemetry_state["position"]["rel_alt"] = getattr(pos, "relative_altitude_m", 0.0)
                await _publish_loop_event(
                    "navigation",
                    float(pos.latitude_deg),
                    float(pos.longitude_deg),
                    float(pos.absolute_altitude_m),
                )

        async def update_battery():
            async for bat in _drone.telemetry.battery():
                raw_rem = float(bat.remaining_percent)
                pct = raw_rem * 100.0 if raw_rem <= 1.0 else raw_rem
                _telemetry_state["battery"] = max(0, min(100, int(pct)))
                cur_pos = _telemetry_state["position"]
                await _publish_loop_event(
                    "battery",
                    float(cur_pos["lat"]) if cur_pos else 0.0,
                    float(cur_pos["lon"]) if cur_pos else 0.0,
                    float(cur_pos["alt"]) if cur_pos else 0.0,
                )
                
        async def update_heading():
            async for head in _drone.telemetry.heading():
                _telemetry_state["heading"] = head.heading_deg

        tasks = [update_pos(), update_battery(), update_heading()]
        if hasattr(_drone.telemetry, "armed"):
            async def update_armed():
                async for armed_state in _drone.telemetry.armed():
                    _telemetry_state["armed"] = bool(armed_state)
            tasks.append(update_armed())

        if hasattr(_drone.telemetry, "in_air"):
            async def update_in_air():
                async for air_state in _drone.telemetry.in_air():
                    _telemetry_state["in_air"] = bool(air_state)
            tasks.append(update_in_air())

        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Telemetry loop error: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _camera, _inference, _drone, _telemetry_task, _connect_task, _edge_spool, _telemetry_publisher

    _camera = CameraStream()
    _camera.open()

    _inference = YoloEInference()
    _inference.load()

    _edge_spool = EdgeSpool()
    _telemetry_publisher = EdgeTelemetryPublisher(
        project_id=os.getenv("DEFAULT_PROJECT_ID", "default-theater"),
        swarm_id=os.getenv("SWARM_ID", "swarm-edge-1"),
        drone_id=os.getenv("DRONE_ID", "drone-1"),
        spool=_edge_spool,
        minio_store=MinioStore(),
    )
    _telemetry_publisher.start()

    _drone = MavSystem()
    mav_url = os.environ.get("MAVSDK_URL", "udp://:14540")

    async def connect_drone():
        global _telemetry_task
        for attempt in range(1, 15):
            try:
                await _drone.connect(system_address=mav_url)
                print(f"[edge] Connected to drone via MAVSDK at {mav_url}", flush=True)
                _telemetry_task = asyncio.create_task(telemetry_loop())
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[edge] MAVSDK connect attempt {attempt} failed: {e}", flush=True)
                await asyncio.sleep(2.0)

    _connect_task = asyncio.create_task(connect_drone())

    yield

    for ctrl in _controllers.values():
        ctrl.stop()
    for c_task in _corridor_tasks.values():
        c_task.cancel()
    for task in _vision_tasks.values():
        task.cancel()
    for cam in _cameras.values():
        cam.close()
    if _flight_controller:
        _flight_controller.stop()
    if _nav_task:
        _nav_task.cancel()
    if _vision_task:
        _vision_task.cancel()
    if _flight_task:
        _flight_task.cancel()
    if _telemetry_task:
        _telemetry_task.cancel()
    if _telemetry_publisher:
        await _telemetry_publisher.stop()
    if _edge_spool:
        _edge_spool.close()
    if _camera:
        _camera.close()

def create_edge_app() -> "FastAPI":
    app = FastAPI(title="ISC Edge Node", version="0.2.0", lifespan=lifespan)

    class TargetRequest(BaseModel):
        target_object_class: str = Field(description="YOLO-E class to identify")
        target_attributes: dict[str, str] | None = Field(
            default=None,
            description="Optional attributes for edge LLM target-vs-obstacle matching",
        )
        command_id: str = Field(description="Originating swarm command ID")
        confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
        detection_mode: Literal["report_only", "intercept"] = Field(
            default="report_only",
            description="'report_only' keeps waypoint navigation active; 'intercept' hands control to FlightController on detection",
        )
        drone_id: str | None = Field(
            default=None,
            description="Target drone channel (defaults to edge DRONE_ID env var)",
        )
        obstacle_avoidance_enabled: bool = Field(
            default=True,
            description="Enable edge-autonomous obstacle detection and dynamic lateral bypass",
        )

    @app.post("/target")
    async def assign_target(body: TargetRequest):
        global _current_assignment, _flight_controller, _vision_task, _nav_task
        default_drone_id = os.getenv("DRONE_ID", "drone-1")
        target_drone_id = (body.drone_id or default_drone_id).strip() or default_drone_id

        _current_assignment = TargetAssignment(
            target_object_class=body.target_object_class,
            command_id=body.command_id,
            confidence_threshold=body.confidence_threshold,
        )
        _telemetry_state.pop("last_avoidance_command", None)
        _telemetry_state["status"] = "searching"
        logger.info(
            "Target assigned: drone=%s class='%s' mode='%s'",
            target_drone_id,
            body.target_object_class,
            body.detection_mode,
        )

        # Stop only the previous vision task for this specific drone_id
        prev_ctrl = _controllers.get(target_drone_id)
        if prev_ctrl:
            prev_ctrl.stop()
        prev_task = _vision_tasks.get(target_drone_id)
        if prev_task and not prev_task.done():
            prev_task.cancel()
            try:
                await prev_task
            except asyncio.CancelledError:
                pass

        async def _cancel_nav_on_intercept() -> None:
            if _nav_task and not _nav_task.done():
                logger.info(
                    "Intercept triggered for drone=%s target='%s': cancelling waypoint navigation",
                    target_drone_id,
                    body.target_object_class,
                )
                _nav_task.cancel()

        # Select camera stream: reuse primary _camera for default drone_id or open per-drone stream
        cam = _camera if target_drone_id == default_drone_id else _cameras.get(target_drone_id)
        if cam is None and target_drone_id != default_drone_id:
            vcam_base = os.getenv("VIRTUAL_CAM_BASE_URL", "").strip()
            if vcam_base:
                cam = CameraStream(device_id=f"{vcam_base.rstrip('/')}/stream/{target_drone_id}")
                _cameras[target_drone_id] = cam

        if cam and _inference:
            _inference.confidence_threshold = body.confidence_threshold
            ctrl = FlightController(
                cam,
                _inference,
                body.target_object_class,
                drone=_drone if target_drone_id == default_drone_id else None,
                telemetry_publisher=_telemetry_publisher,
                mission_id=body.command_id,
                detection_mode=body.detection_mode,
                on_detect_intercept=_cancel_nav_on_intercept if target_drone_id == default_drone_id else None,
                drone_id=target_drone_id,
                target_attributes=body.target_attributes,
                obstacle_avoidance_enabled=body.obstacle_avoidance_enabled,
            )
            _controllers[target_drone_id] = ctrl
            if target_drone_id == default_drone_id:
                _flight_controller = ctrl

            pos_now = _telemetry_state.get("position") or {}
            ctrl.last_lat = float(pos_now.get("lat", 0.0))
            ctrl.last_lon = float(pos_now.get("lon", 0.0))
            ctrl.last_alt_m = float(pos_now.get("alt", 0.0))

            async def run_vision(controller=ctrl, stream=cam, d_id=target_drone_id):
                if d_id != default_drone_id and stream._capture is not None:
                    await asyncio.to_thread(stream.close)
                if stream._capture is None or not stream._capture.isOpened():
                    await asyncio.to_thread(stream.open)
                controller._running = True
                if controller.drone:
                    controller._telemetry_task = asyncio.create_task(controller._telemetry_loop())
                try:
                    await controller._navigation_loop()
                except asyncio.CancelledError:
                    pass
                finally:
                    if controller._telemetry_task:
                        controller._telemetry_task.cancel()
                    if d_id != default_drone_id:
                        stream.close()

            task = asyncio.create_task(run_vision())
            _vision_tasks[target_drone_id] = task
            if target_drone_id == default_drone_id:
                _vision_task = task

        resp = {"status": "accepted", "target": body.target_object_class}
        if body.drone_id is not None:
            resp["drone_id"] = target_drone_id
        return resp

    @app.post("/target/stop")
    async def stop_target(drone_id: str | None = None):
        targets_to_stop = [drone_id] if drone_id else list(_vision_tasks.keys())
        for d_id in targets_to_stop:
            ctrl = _controllers.get(d_id)
            if ctrl:
                ctrl.stop()
            t = _vision_tasks.pop(d_id, None)
            if t and not t.done():
                t.cancel()
        _telemetry_state.pop("last_avoidance_command", None)
        _telemetry_state["status"] = "idle"
        return {"status": "stopped", "stopped": targets_to_stop}

    @app.get("/target")
    async def get_target():
        if _current_assignment is None:
            return {"status": "idle", "target": None}
        return {
            "status": "active",
            "target": _current_assignment.target_object_class,
            "command_id": _current_assignment.command_id,
        }

    class ContextRequest(BaseModel):
        swarm_id: str
        project_id: str = "default-theater"

    class WaypointIn(BaseModel):
        lat: float
        lon: float
        alt_m: float = 15.0

    class NavigateRequest(BaseModel):
        command_id: str | None = None
        swarm_id: str | None = None
        project_id: str | None = None
        waypoints: list[WaypointIn] = Field(min_length=1)

    @app.post("/context")
    async def set_context(body: ContextRequest):
        if _telemetry_publisher is not None:
            _telemetry_publisher.swarm_id = body.swarm_id
            _telemetry_publisher.project_id = body.project_id
        logger.info("Updated telemetry context: project=%s swarm=%s", body.project_id, body.swarm_id)
        return {"status": "ok", "swarm_id": body.swarm_id, "project_id": body.project_id}

    @app.post("/navigate")
    async def navigate(body: NavigateRequest):
        global _nav_task
        if _telemetry_publisher is not None:
            if body.swarm_id:
                _telemetry_publisher.swarm_id = body.swarm_id
            if body.project_id:
                _telemetry_publisher.project_id = body.project_id

        if _nav_task and not _nav_task.done():
            _nav_task.cancel()
            try:
                await _nav_task
            except asyncio.CancelledError:
                pass

        async def run_navigate():
            if _drone is None:
                logger.error("Cannot navigate: _drone is not initialized")
                return
            _telemetry_state["status"] = "navigating"
            try:
                is_armed = bool(_telemetry_state.get("armed", False))
                rel_alt = float((_telemetry_state.get("position") or {}).get("rel_alt") or 0.0)
                takeoff_alt = max((wp.alt_m for wp in body.waypoints), default=15.0)
                if not is_armed:
                    await _drone.action.set_takeoff_altitude(max(5.0, float(takeoff_alt)))
                    await _drone.action.arm()
                    await _drone.action.takeoff()
                    await asyncio.sleep(6.0)
                else:
                    in_air = bool(_telemetry_state.get("in_air", False))
                    if not in_air or rel_alt < 2.0:
                        await _drone.action.set_takeoff_altitude(max(5.0, float(takeoff_alt)))
                        await _drone.action.takeoff()
                        await asyncio.sleep(6.0)

                for wp in body.waypoints:
                    pos_state = _telemetry_state.get("position") or {}
                    current_abs_alt = float(pos_state.get("alt") or 500.0)
                    current_rel_alt = float(pos_state.get("rel_alt") or 0.0)
                    ground_alt = current_abs_alt - current_rel_alt
                    target_abs_alt = ground_alt + float(wp.alt_m)
                    logger.info(
                        "Navigating to waypoint lat=%.6f lon=%.6f abs_alt=%.2f",
                        wp.lat,
                        wp.lon,
                        target_abs_alt,
                    )
                    await _drone.action.goto_location(wp.lat, wp.lon, target_abs_alt, 0.0)

                    # Wait up to 45s per waypoint to get close before next waypoint
                    for _ in range(45):
                        await asyncio.sleep(1.0)
                        cur = _telemetry_state.get("position") or {}
                        dlat = abs(float(cur.get("lat", 0.0)) - wp.lat)
                        dlon = abs(float(cur.get("lon", 0.0)) - wp.lon)
                        if dlat < 0.00008 and dlon < 0.00008:
                            break

                _telemetry_state["status"] = "holding"
            except asyncio.CancelledError:
                logger.info("Navigation task cancelled")
                raise
            except Exception as exc:
                logger.error("Navigation flight failed: %s", exc)
                _telemetry_state["status"] = "error"

        _nav_task = asyncio.create_task(run_navigate())
        return {
            "status": "accepted",
            "command_id": body.command_id,
            "waypoint_count": len(body.waypoints),
        }

    class CorridorSurveyStartRequest(BaseModel):
        survey_id: str
        command_id: str
        swarm_id: str
        project_id: str = "default-theater"
        drone_id: str = "drone-1"
        staging_hold_drone_ids: list[str] = Field(default_factory=list)
        entry_altitude_m: float = Field(default=2.5, ge=0.5, le=120.0)
        target_distance_m: float = Field(default=20.0, gt=0.0)
        distance_defaulted: bool = False
        return_to_origin: bool = True
        corridor_descriptor: str = "corridor"
        intelligence_focus: list[str] = Field(default_factory=list)
        min_altitude_m: float = Field(default=1.2, ge=0.5)
        max_altitude_m: float = Field(default=8.0, le=120.0)
        cruise_speed_ms: float = Field(default=1.5, ge=0.3, le=5.0)
        look_around_steps: int = Field(default=8, ge=4, le=16)
        snapshot_interval_s: float = Field(default=0.4, ge=0.1, le=5.0)
        guidance_timeout_s: float = Field(default=5.0, ge=1.0, le=60.0)

        @field_validator("survey_id")
        @classmethod
        def _validate_survey_uuid(cls, value: str) -> str:
            uuid.UUID(str(value))
            return str(value)

        @field_validator("drone_id")
        @classmethod
        def _validate_drone_id(cls, value: str) -> str:
            if not _EDGE_DRONE_ID_RE.match(value.strip()):
                raise ValueError(f"Invalid drone_id: {value!r}")
            return value.strip()

        @field_validator("staging_hold_drone_ids")
        @classmethod
        def _validate_staging_drone_ids(cls, values: list[str]) -> list[str]:
            cleaned: list[str] = []
            for item in values:
                trimmed = item.strip()
                if trimmed and not _EDGE_DRONE_ID_RE.match(trimmed):
                    raise ValueError(f"Invalid staging_hold drone_id: {item!r}")
                if trimmed:
                    cleaned.append(trimmed)
            return cleaned

    class CorridorOverrideBody(BaseModel):
        rationale: str | None = Field(default=None, max_length=500)
        commander_id: str = Field(default="commander", max_length=128)

    @app.post("/corridor-survey/start")
    async def start_corridor_survey(body: CorridorSurveyStartRequest):
        global _nav_task, _flight_controller, _vision_task
        if body.min_altitude_m >= body.max_altitude_m:
            raise HTTPException(
                status_code=422,
                detail=f"min_altitude_m ({body.min_altitude_m}) must be less than max_altitude_m ({body.max_altitude_m})",
            )

        default_drone_id = os.getenv("DRONE_ID", "drone-1")
        scout_drone_id = (body.drone_id or default_drone_id).strip() or default_drone_id
        scout_drone = _drone if scout_drone_id == default_drone_id else None
        if scout_drone is None:
            raise HTTPException(
                status_code=503,
                detail=f"No active flight controller attached for scout {scout_drone_id}",
            )
        staging_ids = [
            d.strip()
            for d in body.staging_hold_drone_ids
            if d and d.strip() and d.strip() != scout_drone_id
        ]

        if _telemetry_publisher is not None:
            _telemetry_publisher.swarm_id = body.swarm_id
            _telemetry_publisher.project_id = body.project_id

        # Cancel any prior navigation task
        if _nav_task and not _nav_task.done():
            _nav_task.cancel()
            try:
                await _nav_task
            except asyncio.CancelledError:
                pass

        # Stop pre-existing vision/controller tasks on scout + all staging hold drones (FR-019)
        for d_id in [scout_drone_id, *staging_ids]:
            prev_ctrl = _controllers.get(d_id)
            if prev_ctrl:
                prev_ctrl.stop()
            prev_vtask = _vision_tasks.pop(d_id, None)
            if prev_vtask and not prev_vtask.done():
                prev_vtask.cancel()
                try:
                    await prev_vtask
                except asyncio.CancelledError:
                    pass

        # Cancel any pre-existing active corridor survey on this scout drone
        for existing_sid, existing_ctrl in list(_corridor_controllers.items()):
            if existing_ctrl.config.drone_id == scout_drone_id:
                existing_task = _corridor_tasks.get(existing_sid)
                if existing_task and not existing_task.done():
                    existing_task.cancel()
                    try:
                        await existing_task
                    except asyncio.CancelledError:
                        pass

        # Publish explicit survey_staging_hold telemetry for every held staging drone (`FR-019`)
        if _telemetry_publisher is not None:
            cur_pos = _telemetry_state.get("position") or {}
            base_lat = float(cur_pos.get("lat") or 0.0)
            base_lon = float(cur_pos.get("lon") or 0.0)
            base_alt = float(cur_pos.get("alt") or body.entry_altitude_m)
            for staged_id in staging_ids:
                await _telemetry_publisher.publish_event(
                    SwarmTelemetryEvent(
                        project_id=body.project_id,
                        swarm_id=body.swarm_id,
                        drone_id=staged_id,
                        metric_type="alert",
                        lat=base_lat,
                        lon=base_lon,
                        alt_m=base_alt,
                        heading_deg=0.0,
                        speed_ms=0.0,
                        battery_pct=max(
                            0.0,
                            min(
                                100.0,
                                float(_telemetry_state["battery"])
                                if _telemetry_state.get("battery") is not None
                                else 100.0,
                            ),
                        ),
                        flight_status=SURVEY_STAGING_HOLD_STATUS,
                        mission_id=body.command_id,
                        extra={
                            "command_source": "edge_corridor_survey",
                            "decision_authority": "edge",
                            "survey_event_type": "corridor_phase",
                            "survey_id": body.survey_id,
                            "from_phase": SurveyPhase.INITIALIZING.value,
                            "to_phase": SurveyPhase.INITIALIZING.value,
                            "flight_status": SURVEY_STAGING_HOLD_STATUS,
                            "reason": f"Staging hold at entrance while {scout_drone_id} surveys corridor",
                            "rel_x_m": 0.0,
                            "rel_y_m": 0.0,
                            "rel_z_m": 0.0,
                            "heading_deg": 0.0,
                            "cumulative_distance_m": 0.0,
                            "staging_hold_drone_ids": staging_ids,
                        },
                    )
                )

        # Select camera stream for the lead scout drone
        cam = _camera if scout_drone_id == default_drone_id else _cameras.get(scout_drone_id)
        if cam is None and scout_drone_id != default_drone_id:
            vcam_base = os.getenv("VIRTUAL_CAM_BASE_URL", "").strip()
            if vcam_base:
                cam = CameraStream(device_id=f"{vcam_base.rstrip('/')}/stream/{scout_drone_id}")
                _cameras[scout_drone_id] = cam
        if cam is None:
            cam = _camera
        if cam is not None and (getattr(cam, "_capture", None) is None or not cam._capture.isOpened()):
            await asyncio.to_thread(cam.open)

        analyzer = CorridorVisualAnalyzer(
            inference=_inference,
            target_matcher=EdgeTargetMatcher(),
            mission_id=body.command_id,
        )
        config = CorridorSurveyConfig(
            survey_id=body.survey_id,
            command_id=body.command_id,
            swarm_id=body.swarm_id,
            project_id=body.project_id,
            drone_id=scout_drone_id,
            staging_hold_drone_ids=staging_ids,
            entry_altitude_m=body.entry_altitude_m,
            target_distance_m=body.target_distance_m,
            distance_defaulted=body.distance_defaulted,
            return_to_origin=body.return_to_origin,
            corridor_descriptor=body.corridor_descriptor,
            intelligence_focus=list(body.intelligence_focus),
            min_altitude_m=body.min_altitude_m,
            max_altitude_m=body.max_altitude_m,
            cruise_speed_ms=body.cruise_speed_ms,
            look_around_steps=body.look_around_steps,
            snapshot_interval_s=body.snapshot_interval_s,
            guidance_timeout_s=body.guidance_timeout_s,
        )
        ctrl = CorridorSurveyController(
            config=config,
            camera=cam,
            analyzer=analyzer,
            drone=scout_drone,
            telemetry_publisher=_telemetry_publisher,
            telemetry_state=_telemetry_state if scout_drone_id == default_drone_id else None,
        )
        _corridor_controllers[body.survey_id] = ctrl

        async def _run_survey() -> None:
            try:
                await ctrl.run()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.exception("Corridor survey %s failed: %s", body.survey_id, exc)

        _corridor_tasks[body.survey_id] = asyncio.create_task(_run_survey())
        return {
            "status": "accepted",
            "survey_id": body.survey_id,
            "drone_id": scout_drone_id,
            "staging_hold_drone_ids": staging_ids,
            "phase": SurveyPhase.INITIAL_LOOK_AROUND.value,
        }

    @app.get("/corridor-survey/{survey_id}/status")
    async def corridor_survey_status(survey_id: str):
        ctrl = _corridor_controllers.get(survey_id)
        if ctrl is None:
            raise HTTPException(status_code=404, detail=f"Corridor survey {survey_id} not found on edge node")
        return ctrl.get_status_summary()

    @app.post("/corridor-survey/{survey_id}/recall")
    async def recall_corridor_survey(survey_id: str, body: CorridorOverrideBody | None = None):
        ctrl = _corridor_controllers.get(survey_id)
        if ctrl is None:
            raise HTTPException(status_code=404, detail=f"Corridor survey {survey_id} not active on edge node")
        return await ctrl.recall(
            rationale=body.rationale if body is not None else None,
            commander_id=body.commander_id if body is not None else "commander",
        )

    @app.post("/corridor-survey/{survey_id}/emergency-abort")
    async def emergency_abort_corridor_survey(survey_id: str, body: CorridorOverrideBody | None = None):
        ctrl = _corridor_controllers.get(survey_id)
        if ctrl is None:
            raise HTTPException(status_code=404, detail=f"Corridor survey {survey_id} not active on edge node")
        return await ctrl.emergency_abort(
            rationale=body.rationale if body is not None else None,
            commander_id=body.commander_id if body is not None else "commander",
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "node": "edge"}

    @app.get("/telemetry")
    async def telemetry():
        if _flight_controller and _flight_controller.state.status in (
            "bypassing",
            "resuming",
            "obstructed_hold",
            "approaching",
            "arrived",
        ):
            _telemetry_state["status"] = _flight_controller.state.status
        elif _nav_task and not _nav_task.done():
            pass
        elif _flight_controller and _flight_controller.state.status != "searching":
            _telemetry_state["status"] = _flight_controller.state.status
        elif _current_assignment:
            _telemetry_state["status"] = "active"
        if _flight_controller:
            _telemetry_state["target_detected"] = bool(_flight_controller.state.target_detected)
            _telemetry_state["target_intercepted"] = bool(_flight_controller._intercepted)
            if _flight_controller.last_avoidance_command is not None:
                _telemetry_state["last_avoidance_command"] = _flight_controller.last_avoidance_command
        if _corridor_controllers:
            latest_ctrl = list(_corridor_controllers.values())[-1]
            summary = latest_ctrl.get_status_summary()
            _telemetry_state["active_corridor_survey"] = summary
            if latest_ctrl.phase not in (
                SurveyPhase.COMPLETED,
                SurveyPhase.COMPLETED_HOLDING,
                SurveyPhase.IMPASSABLE_START,
                SurveyPhase.EMERGENCY_HOLD,
            ):
                _telemetry_state["status"] = summary["flight_status"]
        return _telemetry_state

    @app.get("/spool/status")
    async def spool_status():
        if _edge_spool is None:
            return {"queued_rows": 0, "priority_queued_rows": 0, "routine_queued_rows": 0}
        return _edge_spool.get_status(os.getenv("SWARM_ID", "swarm-edge-1")).model_dump()

    return app

def run_edge_server(host: str = "0.0.0.0", port: int = 8090) -> None:
    app = create_edge_app()
    logger.info("Starting edge server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
