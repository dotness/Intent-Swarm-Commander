"""YOLO-E inference pipeline for target classification.

Runs the YOLO-E model on frames captured by the camera to detect
and classify target objects in real-time on the Raspberry Pi 5.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from ultralytics import YOLO


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
        if self._model is None:
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


def crop_detection_jpeg(
    frame,
    bbox: tuple[int, int, int, int],
    padding_px: int = 12,
    quality: int = 85,
) -> bytes:
    """Crop the bounded target ROI from a raw camera frame and encode as JPEG bytes."""
    if isinstance(frame, (bytes, bytearray)) and bytes(frame).startswith(b"\xff\xd8\xff"):
        return bytes(frame)

    if frame is None or not hasattr(frame, "shape"):
        raise ValueError("Cannot crop detection JPEG from empty or invalid frame")

    h, w = int(frame.shape[0]), int(frame.shape[1])
    x1, y1, x2, y2 = bbox
    cx1 = max(0, min(w - 1, int(x1) - padding_px))
    cy1 = max(0, min(h - 1, int(y1) - padding_px))
    cx2 = max(cx1 + 1, min(w, int(x2) + padding_px))
    cy2 = max(cy1 + 1, min(h, int(y2) + padding_px))
    crop = frame[cy1:cy2, cx1:cx2]

    import cv2

    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError("cv2.imencode('.jpg') returned False")
    return bytes(buf.tobytes())
