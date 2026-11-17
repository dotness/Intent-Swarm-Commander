"""Virtual HTTP MJPEG camera server for multi-drone headless simulation.

Supports isolated per-drone channels keyed by drone_id:
  - GET  /stream/<drone_id>  (default /stream -> drone-1)
  - POST /feed/<drone_id>    (default /feed   -> drone-1)
  - GET  /feed/<drone_id>    (default /feed   -> drone-1 + channel list)
  - GET  /health
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time

import cv2
import numpy as np
import ultralytics

_DRONE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _default_media_path() -> str:
    env_path = os.getenv("VIRTUAL_VIDEO_PATH", "").strip()
    if env_path:
        return env_path
    return str(Path(ultralytics.__file__).resolve().parent / "assets" / "bus.jpg")


def _is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _make_clear_jpeg(width: int = 640, height: int = 480) -> bytes:
    """Create a plain clear-sky/tarmac JPEG frame with zero COCO objects."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[: height // 2, :] = (210, 175, 130)  # Sky (BGR)
    frame[height // 2 :, :] = (90, 95, 90)     # Empty tarmac
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode clear frame")
    return buf.tobytes()


class _FrameProvider:
    """Thread-safe frame / JPEG provider supporting live feed switching."""

    def __init__(self, media_path: str, fps: float, initial_mode: str = "target") -> None:
        self._lock = threading.Lock()
        self.fps = max(1.0, fps)
        self._clear_jpeg = _make_clear_jpeg()
        self._mode = initial_mode
        self._media_path = media_path
        self._version = 0
        self._static_jpeg: bytes | None = None
        self._load_target_asset(media_path)

    def _load_target_asset(self, media_path: str) -> None:
        if _is_image_path(media_path):
            img = cv2.imread(media_path)
            if img is None:
                raise RuntimeError(f"Failed to load image asset: {media_path}")
            ok, buf = cv2.imencode(".jpg", img)
            if not ok:
                raise RuntimeError(f"Failed to encode image asset: {media_path}")
            self._static_jpeg = buf.tobytes()
        else:
            if not Path(media_path).exists():
                raise RuntimeError(f"Video asset does not exist: {media_path}")
            self._static_jpeg = None

    def set_feed(self, mode: str, path: str | None = None) -> dict:
        if mode not in ("clear", "target"):
            raise ValueError(f"Invalid feed mode: {mode}")
        with self._lock:
            if path:
                self._load_target_asset(path)
                self._media_path = path
            self._mode = mode
            self._version += 1
            return {"mode": self._mode, "media_path": self._media_path, "version": self._version}

    def status(self) -> dict:
        with self._lock:
            return {"mode": self._mode, "media_path": self._media_path, "version": self._version}

    def iter_jpegs(self):
        interval = 1.0 / self.fps
        cap = None
        cap_version = -1
        try:
            while True:
                with self._lock:
                    mode = self._mode
                    media_path = self._media_path
                    static_jpeg = self._static_jpeg
                    version = self._version

                if mode == "clear":
                    if cap is not None:
                        cap.release()
                        cap = None
                    yield self._clear_jpeg
                    time.sleep(interval)
                    continue

                if static_jpeg is not None:
                    if cap is not None:
                        cap.release()
                        cap = None
                    yield static_jpeg
                    time.sleep(interval)
                    continue

                if cap is None or cap_version != version:
                    if cap is not None:
                        cap.release()
                    cap = cv2.VideoCapture(media_path)
                    if not cap.isOpened():
                        raise RuntimeError(f"Failed to open video asset: {media_path}")
                    cap_version = version

                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(interval)
                        continue
                ok, buf = cv2.imencode(".jpg", frame)
                if ok:
                    yield buf.tobytes()
                time.sleep(interval)
        finally:
            if cap is not None:
                cap.release()


class _ChannelRegistry:
    """Thread-safe registry of per-drone _FrameProvider channels."""

    def __init__(self, default_media: str, fps: float, default_mode: str) -> None:
        self._lock = threading.Lock()
        self._default_media = default_media
        self._fps = fps
        self._channels: dict[str, _FrameProvider] = {
            "drone-1": _FrameProvider(media_path=default_media, fps=fps, initial_mode=default_mode),
        }

    def get(self, drone_id: str) -> _FrameProvider:
        if not _DRONE_ID_RE.match(drone_id):
            raise ValueError(f"Invalid drone_id: {drone_id}")
        with self._lock:
            if drone_id not in self._channels:
                self._channels[drone_id] = _FrameProvider(
                    media_path=self._default_media,
                    fps=self._fps,
                    initial_mode="clear",
                )
            return self._channels[drone_id]

    def summary(self) -> dict[str, dict]:
        with self._lock:
            return {did: prov.status() for did, prov in self._channels.items()}


def _parse_channel_path(path: str, prefix: str) -> str | None:
    clean = path.split("?", 1)[0].rstrip("/")
    if clean == prefix:
        return "drone-1"
    if clean.startswith(prefix + "/"):
        return clean[len(prefix) + 1 :]
    return None


def run_server(host: str = "0.0.0.0", port: int = 8091) -> None:
    media_path = _default_media_path()
    fps = float(os.getenv("VIRTUAL_CAM_FPS", "5.0"))
    initial_mode = os.getenv("VIRTUAL_CAM_MODE", "target")
    registry = _ChannelRegistry(default_media=media_path, fps=fps, default_mode=initial_mode)

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, code: int, data: dict) -> None:
            payload = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            clean = self.path.split("?", 1)[0]
            if clean == "/health":
                self._send_json(200, {"status": "ok", "channels": registry.summary()})
                return

            feed_drone = _parse_channel_path(clean, "/feed")
            if feed_drone is not None:
                try:
                    prov = registry.get(feed_drone)
                    self._send_json(200, {"drone_id": feed_drone, **prov.status(), "channels": registry.summary()})
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                return

            stream_drone = _parse_channel_path(clean, "/stream")
            if stream_drone is None and clean in ("/video", "/"):
                stream_drone = "drone-1"

            if stream_drone is not None:
                try:
                    prov = registry.get(stream_drone)
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return

                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                try:
                    for jpeg in prov.iter_jpegs():
                        header = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                        )
                        self.wfile.write(header + jpeg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            clean = self.path.split("?", 1)[0]
            feed_drone = _parse_channel_path(clean, "/feed")
            if feed_drone is not None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    prov = registry.get(feed_drone)
                    body = json.loads(raw.decode("utf-8"))
                    res = prov.set_feed(
                        mode=str(body.get("mode", "target")),
                        path=body.get("path"),
                    )
                    self._send_json(200, {"drone_id": feed_drone, **res})
                except Exception as exc:
                    self._send_json(400, {"error": str(exc)})
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[virtual_cam] Streaming {media_path} (drone-1 mode={initial_mode}) at {fps} fps on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    run_server(
        host=os.getenv("VIRTUAL_CAM_HOST", "0.0.0.0"),
        port=int(os.getenv("VIRTUAL_CAM_PORT", "8091")),
    )
