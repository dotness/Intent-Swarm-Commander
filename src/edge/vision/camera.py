"""Camera stream parsing with OpenCV.

Captures frames from the onboard camera on the Raspberry Pi 5
and provides them to the YOLO-E inference pipeline.
"""

import logging
import os
import threading
from typing import Generator

import cv2

logger = logging.getLogger(__name__)


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
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._reader_running = False
        self._reader_thread: threading.Thread | None = None

    def _reader_loop(self) -> None:
        fail_count = 0
        while self._reader_running and self._capture is not None:
            ret, frame = self._capture.read()
            if not ret:
                fail_count += 1
                if (
                    fail_count >= 10
                    and isinstance(self.device_id, str)
                    and self.device_id.startswith(("http://", "https://"))
                ):
                    logger.warning("Camera stream %s disconnected; reconnecting", self.device_id)
                    self._capture.release()
                    self._capture = cv2.VideoCapture(self.device_id)
                    if self._capture.isOpened():
                        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    fail_count = 0
                continue
            fail_count = 0
            with self._frame_lock:
                self._latest_frame = frame

    def open(self) -> bool:
        """Open the camera device or virtual video stream for capture."""
        if self._capture is not None and self._capture.isOpened():
            return True

        self._capture = cv2.VideoCapture(self.device_id)
        if not self._capture.isOpened():
            logger.error("Failed to open camera source %s", self.device_id)
            return False

        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if isinstance(self.device_id, int):
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._reader_running = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        logger.info("Camera opened: source=%s resolution=%dx%d", self.device_id, self.width, self.height)
        return True

    def read_frame(self):
        """Read the latest frame from the camera without stale MJPEG buffering."""
        if self._capture is None:
            return None

        with self._frame_lock:
            frame = self._latest_frame
        if frame is not None:
            return frame

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
        self._reader_running = False
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None
        with self._frame_lock:
            self._latest_frame = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            logger.info("Camera source %s released", self.device_id)
