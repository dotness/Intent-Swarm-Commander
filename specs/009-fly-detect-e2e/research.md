# Research: Fly-and-Detect E2E with Virtual Video Stream (`009-fly-detect-e2e`)

## Decision 1: Virtual Video Stream Protocol & Docker Service
- **Decision**: Implement a lightweight HTTP MJPEG (`multipart/x-mixed-replace`) streaming server (`scripts/virtual_cam_server.py`) running in a dedicated `virtual_cam` Docker Compose service on port `8091` (`http://virtual_cam:8091/stream`, host-exposed at `http://localhost:8091/stream`), reusing `Dockerfile.backend`.
- **Rationale**:
  - `cv2.VideoCapture("http://virtual_cam:8091/stream")` opens HTTP MJPEG streams natively via OpenCV's FFmpeg backend with no extra RTSP server dependencies.
  - Operators and developers can open `http://localhost:8091/stream` directly in any browser to watch the exact video feed being processed by the drone.
  - Supports both real `.mp4`/`.avi` video files via `VIRTUAL_VIDEO_PATH` (looping on EOF) and a built-in real sample photo (`ultralytics/assets/bus.jpg`, containing `bus` and `person` COCO classes) when no custom video file is mounted, keeping Docker builds 100% offline/hermetic.
- **Alternatives Considered**:
  - *RTSP (`mediamtx` + `ffmpeg`)*: Adds two extra containers/binaries and cannot be viewed directly in a browser tab without WebRTC/HLS transcoding.
  - *`v4l2loopback` kernel module*: Not available in standard WSL2 kernels without custom kernel builds.

## Decision 2: Configurable `CameraStream` Source (Constitution Principle VII)
- **Decision**: Update `CameraStream.__init__` in `src/edge/vision/camera.py` to accept `source: int | str | None = None` (defaulting from `os.getenv("CAMERA_SOURCE", "0")`, parsing digit-only strings as `int` for V4L2 device indices and keeping URLs/paths as `str`), passing it through a single canonical `cv2.VideoCapture(self.source)` call.
- **Rationale**: Preserves `device_id=0` hardware behavior on Raspberry Pi 5 while enabling HTTP MJPEG / RTSP / video file streams in Docker with zero conditional library guards or mock frame generators.
- **Alternatives Considered**:
  - *Mock frame generator inside `CameraStream`*: Violates Constitution Principle VI (No Mocks in Production) and Principle VII (Single-Path Success Logic).

## Decision 3: Decoupled Navigation & Vision Tasks + Business-Logic `detection_mode`
- **Decision**:
  - Split `_flight_task` in `src/edge/api/server.py` into `_nav_task` (MAVSDK `POST /navigate`) and `_vision_task` (`FlightController` via `POST /target`).
  - Add `detection_mode: Literal["report_only", "intercept"] = "report_only"` to `TargetRequest` and `FlightController`.
  - In `report_only` mode (used by `patrol`, `recon`, `escort`, `transport`), `FlightController` runs YOLO-E in parallel, publishes `detection` events + JPEG snapshot crops, and skips `_apply_heading_correction` without interrupting `_nav_task`.
  - In `intercept` mode (used by `strike` post-HITL), on first detection `FlightController` invokes an optional `on_detect_intercept` callback that cancels `_nav_task` and allows `_apply_heading_correction` to steer toward the target.
  - Update `dispatch_edge_mission_activity` in `src/uservice/smeac/operations/process.py` to call `POST /target` alongside `POST /navigate` whenever `cmd.get("target_object_class")` is set, deriving `detection_mode = "intercept"` for `mission_type == "strike"` and `"report_only"` otherwise.
- **Rationale**: Keeps flight control policy in C2/SMEAC business logic rather than hardcoding a single edge behavior.
