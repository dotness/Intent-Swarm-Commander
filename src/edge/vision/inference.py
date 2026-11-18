"""YOLO-E inference pipeline for target classification.

Runs the YOLO-E model on frames captured by the camera to detect
and classify target objects in real-time on the Raspberry Pi 5.
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Literal

import cv2
from ultralytics import YOLOWorld

logger = logging.getLogger(__name__)

DEFAULT_DETECTION_CLASSES: list[str] = [
    "person",
    "car",
    "truck",
    "bus",
    "bench",
    "street lamp",
    "lamp post",
    "pole",
    "tree",
    "traffic light",
    "wall",
]


@dataclass
class Detection:
    """A single object detection result."""

    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    center: tuple[int, int]  # center_x, center_y


@dataclass
class CorridorDetection:
    """Detection enriched with forward-corridor occupancy and proximity metrics."""

    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]
    center: tuple[int, int]
    area_ratio: float
    in_forward_corridor: bool
    detection_id: str = field(default_factory=lambda: str(uuid.uuid4()))


def compute_corridor_occupancy(
    detections: list[Detection],
    frame_width: int,
    frame_height: int,
    corridor_half_width_ratio: float = 0.18,
    min_area_ratio: float = 0.02,
) -> list[CorridorDetection]:
    """Compute forward-corridor overlap and frame-area ratio for each detection."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    frame_area = float(w * h)
    corr_x1 = w * (0.5 - corridor_half_width_ratio)
    corr_x2 = w * (0.5 + corridor_half_width_ratio)

    results: list[CorridorDetection] = []
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        bw = max(0, x2 - x1)
        bh = max(0, y2 - y1)
        area_ratio = float(bw * bh) / frame_area
        overlaps_corridor = (x2 >= corr_x1) and (x1 <= corr_x2)
        in_corridor = overlaps_corridor and (area_ratio >= min_area_ratio)
        results.append(
            CorridorDetection(
                class_name=det.class_name,
                confidence=det.confidence,
                bbox=det.bbox,
                center=det.center,
                area_ratio=area_ratio,
                in_forward_corridor=in_corridor,
            )
        )
    return results


def select_clearest_lateral_side(
    detections: list[Detection],
    frame_width: int,
    frame_height: int,
) -> Literal["left", "right"]:
    """Choose the lateral side (left or right) with lower obstacle occupancy."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    mid_x = w / 2.0
    half_area = max(1.0, mid_x * h)

    left_occ = 0.0
    right_occ = 0.0
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        bh = max(0, y2 - y1)
        if bh == 0:
            continue
        lw = max(0.0, min(float(x2), mid_x) - max(float(x1), 0.0))
        rw = max(0.0, min(float(x2), float(w)) - max(float(x1), mid_x))
        left_occ += (lw * bh) / half_area
        right_occ += (rw * bh) / half_area

    return "left" if left_occ < right_occ else "right"


class YoloEInference:
    """YOLO-E inference engine for the Raspberry Pi 5.

    Parameters
    ----------
    model_path:
        Path to the YOLO-E weights file. Defaults to yolov8n for dev.
    confidence_threshold:
        Minimum confidence to accept a detection (default 0.5).
    """

    def __init__(self, model_path: str | None = None, confidence_threshold: float = 0.4):
        self.model_path = model_path or os.getenv("EDGE_YOLO_MODEL", "yolov8s-worldv2.pt")
        self.confidence_threshold = confidence_threshold
        self._model = None
        self._active_classes: list[str] = list(DEFAULT_DETECTION_CLASSES)

    def set_target_vocabulary(self, target_class: str | None) -> None:
        """Ensure the ordered target class is included in the open-vocabulary detector."""
        classes = list(DEFAULT_DETECTION_CLASSES)
        if target_class and target_class.strip():
            norm = target_class.strip().lower()
            if norm not in {c.lower() for c in classes}:
                classes.append(target_class.strip())
        if classes != self._active_classes:
            self._active_classes = classes
            if self._model is not None and hasattr(self._model, "set_classes"):
                self._model.set_classes(self._active_classes)

    def load(self) -> bool:
        """Load the open-vocabulary YOLO-World model into memory."""

        try:
            self._model = YOLOWorld(self.model_path)
            if hasattr(self._model, "set_classes"):
                self._model.set_classes(self._active_classes)
            logger.info("YOLO-World model loaded from %s", self.model_path)
            return True
        except Exception as e:
            logger.error("Failed to load YOLO-World model: %s", e)
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

    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError("cv2.imencode('.jpg') returned False")
    return bytes(buf.tobytes())
