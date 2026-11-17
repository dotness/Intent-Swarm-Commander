# Research: Multi-Drone Vision Streams, Web GUI Snapshots & Detection HITL (`010-multi-drone-vision-hitl`)

## Decision 1: Per-Drone Virtual Camera Channels (`/stream/{drone_id}` & `/feed/{drone_id}`)
- **Decision**: Refactor `scripts/virtual_cam_server.py` to manage a thread-safe `dict[str, _FrameProvider]` keyed by `drone_id` (validated against `^[a-zA-Z0-9_-]{1,64}$`), lazily initializing unconfigured `drone_id`s in `"clear"` mode (while `"drone-1"` initializes in `VIRTUAL_CAM_MODE`, default `"target"`). Expose `GET /stream/{drone_id}`, `POST /feed/{drone_id}`, and `GET /feed/{drone_id}`, keeping `/stream` and `/feed` as aliases for `"drone-1"`. Add CORS headers on `/feed*` and `/stream*` so the browser Web GUI can render `<img src="http://localhost:8091/stream/{drone_id}">` directly.
- **Rationale**: Zero extra containers needed to simulate 5+ independent drone video feeds; each drone stream is 100% isolated.

## Decision 2: Multi-Drone Vision Channels in `isc_edge` (Compatible with 1:1 Pi 5)
- **Decision**: Update `src/edge/api/server.py` to accept optional `drone_id` on `POST /target` (and `GET /target`), defaulting to `os.getenv("DRONE_ID", "drone-1")`. Maintain per-`drone_id` `_vision_tasks[drone_id]`, `_controllers[drone_id]`, and `CameraStream` (opening `CAMERA_SOURCE` directly when `drone_id` matches the node's own `DRONE_ID`, or `f"{VIRTUAL_CAM_BASE_URL}/stream/{drone_id}"` when `VIRTUAL_CAM_BASE_URL` is configured for multi-drone simulation), sharing the single loaded `YoloEInference` instance. Each `FlightController` uses a per-drone `EdgeTelemetryPublisher` (or passes `drone_id` explicitly on `publish_detection`).
- **Rationale**: Preserves 1:1 `DRONE_ID`/`CAMERA_SOURCE=0` behavior on Raspberry Pi 5 hardware while enabling single-container 5-drone vision simulation in local Docker.

## Decision 3: In-Flight Detection HITL with Cropped JPEG Snapshots
- **Decision**:
  - Extend `HitlDecision` (`src/uservice/hitl/models/storage/decision.py`), `HitlPendingItem`, and `HitlFacade.create_hitl_request` with optional `drone_id`, `detection_event_id`, `snapshot_url`, `target_class`, and `confidence` fields (plus idempotent `ADD COLUMN IF NOT EXISTS` in `init_db` for existing Postgres volumes).
  - When `_handle_detection` in `src/uservice/main.py` receives an in-flight `detection` event whose telemetry status/mode is `"approaching"` or `"hitl_on_detect"` (and no pending HITL already exists for that `drone_id` + `target_class`), create a pending `HitlDecision` carrying `drone_id`, `detection_event_id`, `snapshot_url`, `target_class`, and `confidence`.
  - Update `src/dashboard/js/hitl.js` (`showHitlModal`) to display `Drone ID`, `Target Class` + `Confidence`, and load the cropped JPEG via `window.ApiClient.fetchSnapshotBlobUrl(decision.snapshot_url)` when present.

## Decision 4: Per-Drone Web GUI Vision & Snapshots Panel
- **Decision**: Add a **Drone Vision & Snapshots** panel to `src/dashboard/index.html` and `src/dashboard/js/main.js` with a `drone_id` `<select>` (populated from active telemetry drones + default `drone-1` … `drone-5`), a live `<img id="vision-stream-img">` bound to `http://localhost:8091/stream/${droneId}`, and a per-drone snapshot gallery fetching correlated targets/observations from `/api/v1/targets` + `/lineage` filtered by `obs.drone_id === selectedDroneId` and rendering authenticated JPEG blobs via `fetchSnapshotBlobUrl`.
