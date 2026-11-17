"""Camera stream parsing with OpenCV.

Captures frames from the onboard camera on the Raspberry Pi 5
and provides them to the YOLO-E inference pipeline.
"""

import logging
import os
from typing import Generator

logger = logging.getLogger(__name__)

import cv2


def _resolve_camera_source(device_id: int | str | None) -> int | str:
    raw = os.getenv("CAMERA_SOURCE", "0") if device_id is None else device_id
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.isdigit():
            return int(stripped)
        return stripped
    return raw


class CameraStream:
    """Manages the camera capture lifecycle on the Raspberry Pi 5."""

    def __init__(self, device_id: int | str | None = None, width: int = 640, height: int = 480):
        self.device_id: int | str = _resolve_camera_source(device_id)
        self.width = width
        self.height = height
        self._capture = None

    def open(self) -> bool:
        """Open the camera device or virtual video stream for capture."""
        if self._capture is not None and self._capture.isOpened():
            return True

        self._capture = cv2.VideoCapture(self.device_id)
        if not self._capture.isOpened():
            logger.error("Failed to open camera source %s", self.device_id)
            return False

        if isinstance(self.device_id, int):
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        logger.info("Camera opened: source=%s resolution=%dx%d", self.device_id, self.width, self.height)
        return True

    def read_frame(self):
        """Read a single frame from the camera.

        Returns the frame as a numpy array, or None if capture is unavailable.
        """
        if self._capture is None:
            return None

        ret, frame = self._capture.read()
        if not ret:
            logger.warning("Failed to read frame from camera")
            return None

        return frame

    def frames(self) -> Generator:
        """Yield frames continuously from the camera."""
        while True:
            frame = self.read_frame()
            if frame is None:
                break
            yield frame

    def close(self) -> None:
        """Release the camera device."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            logger.info("Camera source %s released", self.device_id)
