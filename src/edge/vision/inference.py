"""YOLO-E inference pipeline for target classification.

Runs the YOLO-E model on frames captured by the camera to detect
and classify target objects in real-time on the Raspberry Pi 5.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# YOLO-E (via ultralytics) imported conditionally
try:
    from ultralytics import YOLO

    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("YOLO/ultralytics not available — running in simulation mode")


@dataclass
class Detection:
    """A single object detection result."""

    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    center: tuple[int, int]  # center_x, center_y


class YoloEInference:
    """YOLO-E inference engine for the Raspberry Pi 5.

    Parameters
    ----------
    model_path:
        Path to the YOLO-E weights file. Defaults to yolov8n for dev.
    confidence_threshold:
        Minimum confidence to accept a detection (default 0.5).
    """

    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.5):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._model = None

    def load(self) -> bool:
        """Load the YOLO-E model into memory."""
        if not YOLO_AVAILABLE:
            logger.info("Simulated YOLO-E model loaded (path=%s)", self.model_path)
            return True

        try:
            self._model = YOLO(self.model_path)
            logger.info("YOLO-E model loaded from %s", self.model_path)
            return True
        except Exception as e:
            logger.error("Failed to load YOLO-E model: %s", e)
            return False

    def detect(self, frame, target_class: str | None = None) -> list[Detection]:
        """Run inference on a single frame.

        Parameters
        ----------
        frame:
            The image frame (numpy array from OpenCV).
        target_class:
            If specified, only return detections matching this class name.

        Returns
        -------
        List of Detection objects above the confidence threshold.
        """
        if not YOLO_AVAILABLE or self._model is None:
            if os.environ.get("SIMULATION_MODE", "false").lower() != "true":
                raise RuntimeError("YOLO model absent and SIMULATION_MODE is not true.")
            # Simulation mode: return empty detections
            logger.debug("Simulated inference — no detections")
            return []

        results = self._model(frame, verbose=False)
        detections: list[Detection] = []

        for result in results:
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < self.confidence_threshold:
                    continue

                cls_id = int(box.cls[0])
                cls_name = result.names[cls_id]

                # Filter by target class if specified
                if target_class and cls_name.lower() != target_class.lower():
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

                detections.append(Detection(
                    class_name=cls_name,
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                    center=(center_x, center_y),
                ))

        if detections:
            logger.info(
                "YOLO-E detected %d object(s): %s",
                len(detections),
                [(d.class_name, f"{d.confidence:.2f}") for d in detections],
            )

        return detections
