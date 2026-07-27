"""Camera stream parsing with OpenCV.

Captures frames from the onboard camera on the Raspberry Pi 5
and provides them to the YOLO-E inference pipeline.
"""

import logging
import os
from typing import Generator

logger = logging.getLogger(__name__)

# OpenCV imported conditionally — only available on edge nodes
try:
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV not available — running in simulation mode")


class CameraStream:
    """Manages the camera capture lifecycle on the Raspberry Pi 5."""

    def __init__(self, device_id: int = 0, width: int = 640, height: int = 480):
        self.device_id = device_id
        self.width = width
        self.height = height
        self._capture = None

    def open(self) -> bool:
        """Open the camera device for capture."""
        if not OPENCV_AVAILABLE:
            logger.info("Simulated camera opened (device=%d)", self.device_id)
            return True

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

        Returns the frame as a numpy array, or None if capture failed.
        """
        if not OPENCV_AVAILABLE or self._capture is None:
            if os.environ.get("SIMULATION_MODE", "false").lower() != "true":
                raise RuntimeError("Camera hardware absent and SIMULATION_MODE is not true.")
            
            # Consume ROS 2 topic when in simulation mode
            try:
                import rclpy
                from rclpy.node import Node
                from sensor_msgs.msg import Image
                import numpy as np
                import cv2
                
                # Single-frame spin logic for MVP (a dedicated background thread would be better for high FPS)
                if not rclpy.ok():
                    rclpy.init(args=None)
                    
                class CameraSubscriber(Node):
                    def __init__(self):
                        super().__init__('edge_camera_subscriber')
                        self.latest_frame = None
                        self.subscription = self.create_subscription(
                            Image,
                            '/camera/image_raw',
                            self.listener_callback,
                            10)
                            
                    def listener_callback(self, msg):
                        # Convert ROS Image to OpenCV format (bgr8)
                        self.latest_frame = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, -1))
                        # Gazebo usually outputs rgb8, convert to bgr8 for opencv
                        if msg.encoding == 'rgb8':
                            self.latest_frame = cv2.cvtColor(self.latest_frame, cv2.COLOR_RGB2BGR)

                node = CameraSubscriber()
                # Spin once to get the latest message
                rclpy.spin_once(node, timeout_sec=0.1)
                frame = node.latest_frame
                node.destroy_node()
                return frame
            except ImportError:
                logger.error("rclpy not installed, cannot receive simulation camera frames")
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
