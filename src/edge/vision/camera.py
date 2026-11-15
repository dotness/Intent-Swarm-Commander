"""Camera stream parsing with OpenCV.

Captures frames from the onboard camera on the Raspberry Pi 5
and provides them to the YOLO-E inference pipeline.
"""

import logging
from typing import Generator

logger = logging.getLogger(__name__)

import cv2


class CameraStream:
    """Manages the camera capture lifecycle on the Raspberry Pi 5."""

    def __init__(self, device_id: int = 0, width: int = 640, height: int = 480):
        self.device_id = device_id
        self.width = width
        self.height = height
        self._capture = None

    def open(self) -> bool:
        """Open the camera device for capture."""

        self._capture = cv2.VideoCapture(self.device_id)
        if not self._capture.isOpened():
            logger.error("Failed to open camera device %d", self.device_id)
            return False

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        logger.info("Camera opened: device=%d resolution=%dx%d", self.device_id, self.width, self.height)
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
            logger.info("Camera device %d released", self.device_id)
