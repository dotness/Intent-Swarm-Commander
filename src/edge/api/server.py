"""Edge communication API — receives target commands from the Swarm backend.

This lightweight HTTP server runs on the Raspberry Pi 5 and accepts
target_object_class assignments from the central Command Post.
"""

import asyncio
import logging
import os
import math
from dataclasses import dataclass
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from src.edge.vision.camera import CameraStream
from src.edge.vision.inference import YoloEInference
from src.edge.navigation.flight_controller import FlightController

try:
    from mavsdk import System as MavSystem
    MAVSDK_AVAILABLE = True
except ImportError:
    MAVSDK_AVAILABLE = False
    logger.warning("MAVSDK not available on edge")

# FastAPI imported conditionally for the edge server
try:
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    if os.environ.get("SIMULATION_MODE", "false").lower() != "true":
        raise RuntimeError("FastAPI is required for the edge server.")
    logger.warning("FastAPI not available on edge — using stub")

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
_telemetry_task = None

_telemetry_state = {
    "status": "idle",
    "battery": 100,
    "position": {"lat": 0.0, "lon": 0.0, "alt": 0.0},
    "heading": 0.0,
    "speed": 0.0
}

async def telemetry_loop():
    if not MAVSDK_AVAILABLE or not _drone:
        return
    try:
        async def update_pos():
            async for pos in _drone.telemetry.position():
                _telemetry_state["position"]["lat"] = pos.latitude_deg
                _telemetry_state["position"]["lon"] = pos.longitude_deg
                _telemetry_state["position"]["alt"] = pos.absolute_altitude_m
        
        async def update_battery():
            async for bat in _drone.telemetry.battery():
                _telemetry_state["battery"] = int(bat.remaining_percent * 100)
                
        async def update_heading():
            async for head in _drone.telemetry.heading():
                _telemetry_state["heading"] = head.heading_deg

        await asyncio.gather(update_pos(), update_battery(), update_heading())
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Telemetry loop error: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _camera, _inference, _drone, _telemetry_task
    
    _camera = CameraStream()
    _camera.open()
    
    _inference = YoloEInference()
    _inference.load()
    
    if MAVSDK_AVAILABLE:
        _drone = MavSystem()
        mav_url = os.environ.get("MAVSDK_URL", "udp://:14540")
        try:
            await _drone.connect(system_address=mav_url)
            logger.info("Server connected to drone via MAVSDK at %s", mav_url)
            _telemetry_task = asyncio.create_task(telemetry_loop())
        except Exception as e:
            logger.error("Failed to connect to drone: %s", e)
    
    yield
    
    if _flight_controller:
        _flight_controller.stop()
    if _flight_task:
        _flight_task.cancel()
    if _telemetry_task:
        _telemetry_task.cancel()
    if _camera:
        _camera.close()

def create_edge_app() -> "FastAPI":
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for the edge server")

    app = FastAPI(title="ISC Edge Node", version="0.1.0", lifespan=lifespan)

    class TargetRequest(BaseModel):
        target_object_class: str = Field(description="YOLO-E class to identify")
        command_id: str = Field(description="Originating swarm command ID")
        confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    @app.post("/target")
    async def assign_target(body: TargetRequest):
        global _current_assignment, _flight_controller, _flight_task
        _current_assignment = TargetAssignment(
            target_object_class=body.target_object_class,
            command_id=body.command_id,
            confidence_threshold=body.confidence_threshold,
        )
        logger.info("Target assigned: class='%s'", body.target_object_class)
        
        # Stop existing flight task if running
        if _flight_controller:
            _flight_controller.stop()
        if _flight_task:
            _flight_task.cancel()
            
        # Start new flight controller
        if _camera and _inference:
            _flight_controller = FlightController(_camera, _inference, body.target_object_class, drone=_drone)
            
            async def run_flight():
                _flight_controller._running = True
                if MAVSDK_AVAILABLE and _flight_controller.drone:
                    _flight_controller._telemetry_task = asyncio.create_task(_flight_controller._telemetry_loop())
                try:
                    await _flight_controller._navigation_loop()
                except asyncio.CancelledError:
                    pass
            _flight_task = asyncio.create_task(run_flight())

        return {"status": "accepted", "target": body.target_object_class}

    @app.get("/target")
    async def get_target():
        if _current_assignment is None:
            return {"status": "idle", "target": None}
        return {
            "status": "active",
            "target": _current_assignment.target_object_class,
            "command_id": _current_assignment.command_id,
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "node": "edge"}

    @app.get("/telemetry")
    async def telemetry():
        _telemetry_state["status"] = "active" if _current_assignment else "idle"
        if _flight_controller and _flight_controller.state.status != "searching":
            _telemetry_state["status"] = _flight_controller.state.status
        return _telemetry_state

    return app

def run_edge_server(host: str = "0.0.0.0", port: int = 8090) -> None:
    app = create_edge_app()
    logger.info("Starting edge server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
