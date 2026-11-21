"""Virtual HTTP MJPEG camera server for multi-drone headless simulation & corridor E2E verification.

Supports isolated per-drone channels keyed by drone_id:
  - GET  /stream/<drone_id>  (default /stream -> drone-1)
  - POST /feed/<drone_id>    (supports mode = 'target' | 'clear' | 'corridor_scene')
  - GET  /feed/<drone_id>    (default /feed   -> drone-1 + channel list)
  - POST /pose/<drone_id>    (optional direct test pose override for corridor_scene)
  - GET  /health

When MQTT_BROKER_HOST is set and mode == 'corridor_scene', subscribes directly to local
Mosquitto telemetry (navigation & alert topics) to render pose-driven 3D corridor views in
real time while keeping src/edge/ 100% simulation-unaware.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any

import cv2
import numpy as np
import paho.mqtt.client as mqtt
import ultralytics

_DRONE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_EARTH_RADIUS_M = 6_371_000.0
_MAX_POST_BYTES = 65536
_ALLOWED_MEDIA_EXTS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp", ".mp4", ".avi", ".mkv"})
CORRIDOR_SCENARIOS = (
    "straight_20m",
    "l_turn_20m",
    "s_bend_overhang_20m",
    "dead_end_12m",
    "branch_junction_20m",
    "enclosed_start",
)


def _norm_heading(deg: float) -> float:
    h = float(deg) % 360.0
    return 0.0 if h >= 360.0 or h < 0.0 else h


def _angle_diff_deg(a: float, b: float) -> float:
    d = (float(a) - float(b) + 180.0) % 360.0 - 180.0
    return d


def _draw_textured_brick_wall(width: int = 640, height: int = 480) -> np.ndarray:
    """Render a solid textured brick/concrete wall across the full FOV (blocks passage cleanly)."""
    img = np.full((height, width, 3), (72, 62, 58), dtype=np.uint8)
    for row_idx, y in enumerate(range(0, height, 24)):
        cv2.line(img, (0, y), (width - 1, y), (145, 132, 126), 2)
        offset = 24 if row_idx % 2 == 0 else 0
        for x in range(offset, width, 48):
            cv2.line(img, (x, y), (x, min(height - 1, y + 24)), (145, 132, 126), 2)
    return img


def render_corridor_scene_frame(
    *,
    scenario: str,
    rel_x_m: float = 0.0,
    rel_y_m: float = 0.0,
    rel_z_m: float = 2.5,
    heading_deg: float = 0.0,
    target_object_asset: str | None = None,
    dynamic_return_block: bool = False,
    width: int = 640,
    height: int = 480,
) -> np.ndarray:
    """Deterministically render a 3D perspective corridor view from (rel_x, rel_y, rel_z, heading)."""
    if scenario == "enclosed_start":
        return _draw_textured_brick_wall(width, height)

    h_deg = _norm_heading(heading_deg)
    # Determine navigable passage center heading(s) & geometry based on scenario + 3D pose
    portals: list[tuple[float, float, bool]] = []  # (azimuth_shift_norm [-1..1], portal_y_norm, low_overhang)
    blocked = False
    is_returning_south = abs(_angle_diff_deg(h_deg, 180.0)) < 55.0 and rel_y_m > 2.0

    if dynamic_return_block and is_returning_south and rel_y_m < 8.0:
        blocked = True

    elif scenario == "straight_20m":
        expected_dir = 180.0 if is_returning_south else 0.0
        err = _angle_diff_deg(expected_dir, h_deg)
        if abs(err) > 55.0 or rel_y_m > 25.0:
            blocked = True
        else:
            portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))

    elif scenario == "dead_end_12m":
        if abs(_angle_diff_deg(h_deg, 180.0)) <= 70.0 and rel_y_m > 2.0:
            err = _angle_diff_deg(180.0, h_deg)
            portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))
        else:
            err = _angle_diff_deg(0.0, h_deg)
            if abs(err) > 40.0 or rel_y_m >= 11.2 or math.hypot(rel_x_m, rel_y_m) >= 12.0:
                blocked = True
            else:
                portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))

    elif scenario == "l_turn_20m":
        if is_returning_south and rel_x_m < 2.8:
            # Returning South down the first leg back to origin (including corner exit)
            err = _angle_diff_deg(180.0, h_deg)
            portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))
        elif rel_y_m < 8.5 and rel_x_m < 2.0:
            # First leg: heading North toward 10m corner
            if rel_y_m >= 8.0:
                # Approaching 90-degree right corner at (0, 10): East leg opens on right (+90 deg)
                err = _angle_diff_deg(90.0, h_deg)
                if abs(err) <= 65.0:
                    portals.append((max(-0.75, min(0.75, err / 60.0)), 0.48, False))
                else:
                    blocked = True
            else:
                err = _angle_diff_deg(0.0, h_deg)
                if abs(err) > 55.0:
                    blocked = True
                else:
                    portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))
        else:
            # Second leg: heading East along (x=0..15, y~10) or West returning toward corner
            target_dir = 270.0 if abs(_angle_diff_deg(h_deg, 270.0)) < 65.0 else 90.0
            err = _angle_diff_deg(target_dir, h_deg)
            if abs(err) > 65.0:
                blocked = True
            else:
                portals.append((max(-0.75, min(0.75, err / 60.0)), 0.48, False))

    elif scenario == "s_bend_overhang_20m":
        returning_leg = is_returning_south and rel_y_m > 2.0
        expected_dir = 180.0 if returning_leg else 0.0
        bend_bias = 28.0 * math.cos(math.pi * max(0.0, rel_y_m) / 10.0) if not returning_leg else 0.0
        target_dir = _norm_heading(expected_dir + bend_bias)
        err = _angle_diff_deg(target_dir, h_deg)
        low_overhang = 6.5 <= rel_y_m <= 13.5 and rel_z_m > 1.7
        if abs(err) > 60.0:
            blocked = True
        else:
            portals.append((max(-0.70, min(0.70, err / 55.0)), 0.64 if low_overhang else 0.48, low_overhang))

    elif scenario == "branch_junction_20m":
        if is_returning_south:
            err = _angle_diff_deg(180.0, h_deg)
            portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))
        elif 6.0 <= rel_y_m <= 10.5 and abs(_angle_diff_deg(0.0, h_deg)) <= 45.0:
            # T-junction / Y-fork at 8m showing left & right open portals around central pillar
            portals.append((-0.72, 0.50, False))
            portals.append((0.72, 0.50, False))
        else:
            expected_dir = 45.0 if rel_y_m > 10.5 else 0.0
            err = _angle_diff_deg(expected_dir, h_deg)
            if abs(err) > 60.0:
                blocked = True
            else:
                portals.append((max(-0.75, min(0.75, err / 55.0)), 0.48, False))

    else:
        blocked = True

    if blocked or not portals:
        return _draw_textured_brick_wall(width, height)

    # Render textured side walls & perspective grid surrounding the open portal(s)
    img = _draw_textured_brick_wall(width, height)
    has_overhang = any(o for _, _, o in portals)

    for shift, py_norm, low_overhang in portals:
        cx = int(width * (0.5 + shift * 0.55))
        cy = int(height * py_norm)
        pw = int(width * 0.28)
        ph = int(height * (0.28 if low_overhang else 0.44))
        x1 = max(8, cx - pw // 2)
        x2 = min(width - 8, cx + pw // 2)
        y1 = max(8, cy - ph // 2)
        y2 = min(height - 8, cy + ph // 2)
        cv2.rectangle(img, (x1, y1), (x2, y2), (168, 180, 188), -1)
        if len(portals) == 1:
            cv2.line(img, (0, 0), (x1, y1), (200, 200, 200), 2)
            cv2.line(img, (width - 1, 0), (x2, y1), (200, 200, 200), 2)
            cv2.line(img, (0, height - 1), (x1, y2), (200, 200, 200), 2)
            cv2.line(img, (width - 1, height - 1), (x2, y2), (200, 200, 200), 2)

    if has_overhang:
        beam_bottom = int(height * 0.44)
        cv2.rectangle(img, (0, 0), (width - 1, beam_bottom), (36, 40, 46), -1)
        for sx in range(0, width, 32):
            cv2.rectangle(img, (sx, beam_bottom - 18), (sx + 16, beam_bottom), (0, 175, 235), -1)

    if target_object_asset and Path(target_object_asset).is_file():
        asset = cv2.imread(target_object_asset)
        if asset is not None:
            th, tw = int(height * 0.24), int(width * 0.22)
            resized = cv2.resize(asset, (tw, th))
            tx = int(width * 0.14)
            ty = int(height * 0.56)
            img[ty : ty + th, tx : tx + tw] = resized

    return img


def _default_media_path() -> str:
    env_path = os.getenv("VIRTUAL_VIDEO_PATH", "").strip()
    if env_path:
        return env_path
    return str(Path(ultralytics.__file__).resolve().parent / "assets" / "bus.jpg")


def _is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _validate_local_asset_path(raw_path: str) -> str:
    """Ensure local media asset paths resolve inside trusted roots and use safe extensions."""
    cleaned = str(raw_path).strip()
    if not cleaned or "://" in cleaned or "\x00" in cleaned:
        raise ValueError("Invalid media asset path")
    resolved = Path(cleaned).resolve()
    if resolved.suffix.lower() not in _ALLOWED_MEDIA_EXTS:
        raise ValueError(f"Unsupported media extension: {resolved.suffix!r}")
    allowed_roots = [
        Path.cwd().resolve(),
        (Path(ultralytics.__file__).resolve().parent / "assets").resolve(),
        Path("/app").resolve(),
    ]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError("Media asset path outside permitted workspace roots")
    if not resolved.exists():
        raise ValueError(f"Media asset does not exist: {cleaned}")
    return str(resolved)


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
    """Thread-safe frame / JPEG provider supporting live feed & pose-driven corridor switching."""

    def __init__(self, media_path: str, fps: float, initial_mode: str = "target") -> None:
        self._lock = threading.Lock()
        self.fps = max(1.0, fps)
        self._clear_jpeg = _make_clear_jpeg()
        self._mode = initial_mode
        self._media_path = media_path
        self._version = 0
        self._static_jpeg: bytes | None = None
        self._scenario: str = "straight_20m"
        self._target_object_asset: str | None = None
        self._dynamic_return_block: bool = False
        self._pose: dict[str, float] = {
            "rel_x_m": 0.0,
            "rel_y_m": 0.0,
            "rel_z_m": 2.5,
            "heading_deg": 0.0,
        }
        self._origin: dict[str, float] | None = None
        self._last_corridor_pose_mono: float = 0.0
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

    def set_feed(
        self,
        mode: str,
        path: str | None = None,
        *,
        scenario: str | None = None,
        target_object_asset: str | None = None,
        dynamic_return_block: bool = False,
    ) -> dict[str, Any]:
        if mode not in ("clear", "target", "corridor_scene"):
            raise ValueError(f"Invalid feed mode: {mode}")
        validated_path = _validate_local_asset_path(path) if (path and mode == "target") else None
        validated_asset = (
            _validate_local_asset_path(target_object_asset)
            if (mode == "corridor_scene" and target_object_asset)
            else None
        )
        with self._lock:
            if validated_path is not None:
                self._load_target_asset(validated_path)
                self._media_path = validated_path
            if mode == "corridor_scene":
                chosen = scenario or "straight_20m"
                if chosen not in CORRIDOR_SCENARIOS:
                    raise ValueError(f"Invalid corridor scenario: {chosen}")
                self._scenario = chosen
                self._target_object_asset = validated_asset
                self._dynamic_return_block = bool(dynamic_return_block)
                self._pose = {"rel_x_m": 0.0, "rel_y_m": 0.0, "rel_z_m": 2.5, "heading_deg": 0.0}
                self._origin = None
                self._last_corridor_pose_mono = 0.0
            self._mode = mode
            self._version += 1
            return self._unlocked_status()

    def set_pose(
        self,
        *,
        rel_x_m: float,
        rel_y_m: float,
        rel_z_m: float,
        heading_deg: float,
    ) -> dict[str, float]:
        with self._lock:
            self._pose = {
                "rel_x_m": float(rel_x_m),
                "rel_y_m": float(rel_y_m),
                "rel_z_m": float(rel_z_m),
                "heading_deg": _norm_heading(heading_deg),
            }
            return dict(self._pose)

    def update_from_mqtt_telemetry(self, payload: dict[str, Any]) -> None:
        """Update local corridor ENU pose automatically from Mosquitto telemetry (`[B1]`)."""
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        if extra.get("survey_event_type") in ("corridor_phase", "corridor_snapshot"):
            lat = float(payload.get("lat") or 0.0)
            lon = float(payload.get("lon") or 0.0)
            alt_m = float(payload.get("alt_m") or 0.0)
            rel_z = float(extra.get("rel_z_m") or 2.5)
            heading = float(payload.get("heading_deg") or 0.0)
            with self._lock:
                if self._origin is None and lat != 0.0 and lon != 0.0:
                    self._origin = {"lat": lat, "lon": lon, "ground_alt": alt_m - rel_z}
                if "rel_x_m" in extra and "rel_y_m" in extra:
                    rx = float(extra["rel_x_m"])
                    ry = float(extra["rel_y_m"])
                    self._pose = {
                        "rel_x_m": rx,
                        "rel_y_m": ry,
                        "rel_z_m": rel_z,
                        "heading_deg": _norm_heading(heading),
                    }
                    if math.hypot(rx, ry) > 0.5:
                        self._last_corridor_pose_mono = time.monotonic()
            return

        if payload.get("metric_type") == "navigation":
            lat = float(payload.get("lat") or 0.0)
            lon = float(payload.get("lon") or 0.0)
            alt_m = float(payload.get("alt_m") or 0.0)
            heading = float(payload.get("heading_deg") or 0.0)
            if lat == 0.0 and lon == 0.0:
                return
            with self._lock:
                if self._origin is None:
                    self._origin = {"lat": lat, "lon": lon, "ground_alt": alt_m - 2.5}
                cos_lat = max(0.05, math.cos(math.radians(self._origin["lat"])))
                rel_y = math.radians(lat - self._origin["lat"]) * _EARTH_RADIUS_M
                rel_x = math.radians(lon - self._origin["lon"]) * _EARTH_RADIUS_M * cos_lat
                rel_z = alt_m - self._origin["ground_alt"]
                preserve_corridor_xy = (
                    (time.monotonic() - self._last_corridor_pose_mono) < 3.0
                    and math.hypot(rel_x, rel_y) + 0.5 < math.hypot(self._pose["rel_x_m"], self._pose["rel_y_m"])
                )
                self._pose = {
                    "rel_x_m": self._pose["rel_x_m"] if preserve_corridor_xy else float(rel_x),
                    "rel_y_m": self._pose["rel_y_m"] if preserve_corridor_xy else float(rel_y),
                    "rel_z_m": float(rel_z),
                    "heading_deg": _norm_heading(heading),
                }

    def _unlocked_status(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "media_path": self._media_path,
            "scenario": self._scenario if self._mode == "corridor_scene" else None,
            "pose": dict(self._pose) if self._mode == "corridor_scene" else None,
            "version": self._version,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._unlocked_status()

    def iter_jpegs(self):
        interval = 1.0 / self.fps
        rng = np.random.default_rng()
        cap = None
        cap_version = -1
        try:
            while True:
                with self._lock:
                    mode = self._mode
                    media_path = self._media_path
                    static_jpeg = self._static_jpeg
                    version = self._version
                    scenario = self._scenario
                    pose = dict(self._pose)
                    target_asset = self._target_object_asset
                    dyn_block = self._dynamic_return_block

                if mode == "clear":
                    if cap is not None:
                        cap.release()
                        cap = None
                    yield self._clear_jpeg
                    time.sleep(interval)
                    continue

                if mode == "corridor_scene":
                    if cap is not None:
                        cap.release()
                        cap = None
                    frame = render_corridor_scene_frame(
                        scenario=scenario,
                        rel_x_m=pose["rel_x_m"],
                        rel_y_m=pose["rel_y_m"],
                        rel_z_m=pose["rel_z_m"],
                        heading_deg=pose["heading_deg"],
                        target_object_asset=target_asset,
                        dynamic_return_block=dyn_block,
                    )
                    # Add subtle per-frame sensor grain so live MJPEG streams do not false-trigger static freeze detection
                    grain = rng.integers(-6, 7, size=frame.shape, dtype=np.int16)
                    noisy = np.clip(frame.astype(np.int16) + grain, 0, 255).astype(np.uint8)
                    ok, buf = cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ok:
                        yield buf.tobytes()
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


def _start_mqtt_pose_subscriber(registry: _ChannelRegistry) -> mqtt.Client | None:
    """Subscribe directly to Mosquitto navigation/alert telemetry to sync corridor_scene poses."""
    broker_host = os.getenv("MQTT_BROKER_HOST", "").strip()
    if not broker_host:
        return None
    broker_port = int(os.getenv("MQTT_BROKER_PORT", "1883"))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="virtual-cam-pose-sync")

    def _on_connect(c: Any, _ud: Any, _flags: Any, rc: Any, _props: Any = None) -> None:
        if rc == 0 or getattr(rc, "value", 1) == 0:
            c.subscribe("telemetry/projects/+/swarms/+/+/navigation", qos=0)
            c.subscribe("telemetry/projects/+/swarms/+/+/alert", qos=1)
            print(f"[virtual_cam] Subscribed to MQTT pose telemetry on {broker_host}:{broker_port}", flush=True)

    def _on_message(_c: Any, _ud: Any, msg: Any) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            drone_id = str(payload.get("drone_id") or "")
            if _DRONE_ID_RE.match(drone_id):
                registry.get(drone_id).update_from_mqtt_telemetry(payload)
        except Exception:
            pass

    client.on_connect = _on_connect
    client.on_message = _on_message
    try:
        client.connect_async(broker_host, broker_port, keepalive=30)
        client.loop_start()
        return client
    except Exception as exc:
        print(f"[virtual_cam] MQTT pose subscriber init warning ({broker_host}:{broker_port}): {exc}", flush=True)
        return None


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
    mqtt_client = _start_mqtt_pose_subscriber(registry)

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

        def _read_json_body(self) -> dict[str, Any]:
            raw_len = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_len)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length header") from exc
            if length < 0 or length > _MAX_POST_BYTES:
                raise ValueError(f"Request body exceeds maximum size ({_MAX_POST_BYTES} bytes)")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Request JSON payload must be an object")
            return parsed

        def do_POST(self) -> None:  # noqa: N802
            clean = self.path.split("?", 1)[0]
            feed_drone = _parse_channel_path(clean, "/feed")
            if feed_drone is not None:
                try:
                    prov = registry.get(feed_drone)
                    body = self._read_json_body()
                    res = prov.set_feed(
                        mode=str(body.get("mode", "target")),
                        path=body.get("path"),
                        scenario=body.get("scenario"),
                        target_object_asset=body.get("target_object_asset"),
                        dynamic_return_block=bool(body.get("dynamic_return_block", False)),
                    )
                    self._send_json(200, {"drone_id": feed_drone, **res})
                except Exception as exc:
                    self._send_json(400, {"error": str(exc)})
                return

            pose_drone = _parse_channel_path(clean, "/pose")
            if pose_drone is not None:
                try:
                    prov = registry.get(pose_drone)
                    body = self._read_json_body()
                    pose = prov.set_pose(
                        rel_x_m=float(body.get("rel_x_m", 0.0)),
                        rel_y_m=float(body.get("rel_y_m", 0.0)),
                        rel_z_m=float(body.get("rel_z_m", 2.5)),
                        heading_deg=float(body.get("heading_deg", 0.0)),
                    )
                    self._send_json(200, {"drone_id": pose_drone, "pose": pose})
                except Exception as exc:
                    self._send_json(400, {"error": str(exc)})
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[virtual_cam] Streaming {media_path} (drone-1 mode={initial_mode}) at {fps} fps on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        if mqtt_client is not None:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    run_server(
        host=os.getenv("VIRTUAL_CAM_HOST", "0.0.0.0"),
        port=int(os.getenv("VIRTUAL_CAM_PORT", "8091")),
    )
