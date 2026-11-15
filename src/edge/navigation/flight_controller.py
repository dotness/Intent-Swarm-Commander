"""Autonomous flight navigation logic.

Handles the decision loop: detect target → compute heading → adjust flight.
Uses MAVSDK for drone control when available.
"""

import asyncio
import logging
import os
import math
from dataclasses import dataclass

from src.edge.vision.camera import CameraStream
from src.edge.vision.inference import Detection, YoloEInference, crop_detection_jpeg

logger = logging.getLogger(__name__)

from mavsdk import System as MavSystem


@dataclass
class NavigationState:
    """Current state of the autonomous navigation loop."""

    target_class: str
    target_detected: bool = False
    target_confidence: float = 0.0
    target_center: tuple[int, int] = (0, 0)
    approach_distance_m: float = float("inf")
    status: str = "searching"  # searching | approaching | arrived | aborted


class FlightController:
    """Autonomous flight controller for the Raspberry Pi 5.

    Orchestrates the detect-and-approach loop:
    1. Capture frame from camera
    2. Run YOLO-E inference for target class
    3. If detected, compute bearing correction
    4. Send flight adjustment commands
    5. Repeat until within 5m of target or aborted
    """

    def __init__(
        self,
        camera: CameraStream,
        inference: YoloEInference,
        target_class: str,
        drone=None,
        telemetry_publisher=None,
        mission_id: str | None = None,
    ):
        self.camera = camera
        self.inference = inference
        self.target_class = target_class
        self.state = NavigationState(target_class=target_class)
        self._running = False
        self.drone = drone
        self.telemetry_publisher = telemetry_publisher
        self.mission_id = mission_id
        self._telemetry_task = None
        self.last_lat: float = 0.0
        self.last_lon: float = 0.0
        self.last_alt_m: float = 0.0
        # Active target coordinate (set externally from MAVSDK mission telemetry or order)
        self.target_lat = 0.0
        self.target_lon = 0.0

    async def start(self) -> NavigationState:
        """Begin the autonomous navigation loop.

        Returns the final NavigationState when the loop exits.
        """
        logger.info("Starting autonomous navigation — target: '%s'", self.target_class)
        self._running = True

        if self.camera._capture is None and not self.camera.open():
            self.state.status = "aborted"
            logger.error("Navigation aborted: camera failed to open")
            return self.state

        if self.inference._model is None and not self.inference.load():
            self.state.status = "aborted"
            logger.error("Navigation aborted: YOLO-E model failed to load")
            return self.state
            
        if self.drone is None:
            try:
                self.drone = MavSystem()
                mav_url = os.environ.get("MAVSDK_URL", "udp://:14540")
                await self.drone.connect(system_address=mav_url)
                logger.info("Connected to drone via MAVSDK at %s", mav_url)
            except Exception as e:
                logger.error("Failed to connect to drone: %s", e)
                
        if self.drone:
            self._telemetry_task = asyncio.create_task(self._telemetry_loop())

        try:
            await self._navigation_loop()
        finally:
            self.camera.close()

        return self.state

    async def _navigation_loop(self) -> None:
        """Core detect-and-approach loop."""
        max_iterations = 1000  # Safety bound
        iteration = 0

        while self._running and iteration < max_iterations:
            iteration += 1

            frame = self.camera.read_frame()
            if frame is None:
                logger.warning("No frame available — pausing")
                await asyncio.sleep(0.5)
                continue

            detections = self.inference.detect(frame, target_class=self.target_class)

            if detections:
                best = max(detections, key=lambda d: d.confidence)
                self.state.target_detected = True
                self.state.target_confidence = best.confidence
                self.state.target_center = best.center
                self.state.status = "approaching"

                logger.info(
                    "Target '%s' detected (confidence=%.2f) at center=%s",
                    best.class_name, best.confidence, best.center,
                )

                # Compute heading correction
                frame_center_x = self.camera.width // 2
                offset_x = best.center[0] - frame_center_x
                await self._apply_heading_correction(offset_x)

                if self.telemetry_publisher is not None:
                    snapshot_bytes: bytes | None = None
                    try:
                        snapshot_bytes = crop_detection_jpeg(frame, best.bbox)
                    except (ValueError, RuntimeError):
                        snapshot_bytes = None
                    await self.telemetry_publisher.publish_detection(
                        lat=self.last_lat,
                        lon=self.last_lon,
                        alt_m=self.last_alt_m,
                        target_class=best.class_name,
                        confidence=best.confidence,
                        bbox=best.bbox,
                        snapshot_bytes=snapshot_bytes,
                        mission_id=self.mission_id,
                        flight_status=self.state.status,
                    )

                if self.state.approach_distance_m <= 5.0:
                    self.state.status = "arrived"
                    logger.info("Target reached — within 5m")
                    break
            else:
                self.state.target_detected = False
                self.state.status = "searching"

            await asyncio.sleep(0.1)  # ~10 FPS processing rate

    async def _apply_heading_correction(self, offset_x: int) -> None:
        """Adjust drone heading based on target offset from frame center.

        Positive offset_x → target is right of center → yaw right.
        """
        if abs(offset_x) < 20:
            return  # Target is centered enough

        direction = "right" if offset_x > 0 else "left"
        logger.debug("Heading correction: %s (offset=%dpx)", direction, offset_x)

        if self.drone:
            # Map offset to degrees (simplified)
            yaw_deg = float(offset_x) * 0.1
            try:
                await self.drone.action.set_yaw(yaw_deg)
            except Exception as e:
                logger.error("Failed to set yaw: %s", e)
                
    async def _telemetry_loop(self):
        """Background task to update distance from telemetry."""
        if not self.drone:
            return
            
        try:
            async for position in self.drone.telemetry.position():
                if not self._running:
                    break

                self.last_lat = position.latitude_deg
                self.last_lon = position.longitude_deg
                self.last_alt_m = position.absolute_altitude_m

                if self.telemetry_publisher is not None:
                    from src.uservice.telemetry.models.contract.events import SwarmTelemetryEvent

                    nav_ev = SwarmTelemetryEvent(
                        project_id=self.telemetry_publisher.project_id,
                        swarm_id=self.telemetry_publisher.swarm_id,
                        drone_id=self.telemetry_publisher.drone_id,
                        metric_type="navigation",
                        lat=position.latitude_deg,
                        lon=position.longitude_deg,
                        alt_m=position.absolute_altitude_m,
                        flight_status=self.state.status,
                    )
                    await self.telemetry_publisher.publish_event(nav_ev)

                if self.target_lat == 0.0 and self.target_lon == 0.0:
                    continue
                
                # Approximate distance in meters
                dx = (position.longitude_deg - self.target_lon) * 111320 * math.cos(math.radians(position.latitude_deg))
                dy = (position.latitude_deg - self.target_lat) * 111320
                dist = math.sqrt(dx*dx + dy*dy)
                self.state.approach_distance_m = dist
        except Exception as e:
            logger.error("Telemetry loop failed: %s", e)

    def stop(self) -> None:
        """Stop the navigation loop gracefully."""
        self._running = False
        logger.info("Navigation stop requested")
