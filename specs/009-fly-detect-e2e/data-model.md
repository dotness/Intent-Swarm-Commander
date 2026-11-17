# Data Model: Fly-and-Detect E2E (`009-fly-detect-e2e`)

## Edge Contracts

### `TargetRequest` (`POST /target` on `isc_edge`)
- `target_object_class: str` — COCO / YOLO-E class name (e.g. `"person"`, `"bus"`, `"car"`).
- `command_id: str` — Originating `SwarmCommand.id`.
- `confidence_threshold: float` (default `0.5`, range `0.0..1.0`).
- `detection_mode: Literal["report_only", "intercept"]` (default `"report_only"`):
  - `"report_only"`: Emit detection telemetry & JPEG crops while `_nav_task` completes its Point A → Point B route.
  - `"intercept"`: Cancel `_nav_task` upon target detection and engage `FlightController` heading/approach control.

### `CameraStream` Configuration
- `CAMERA_SOURCE` env var (default `"0"`): Parsed as `int` when numeric (`"0"` → `0`) or `str` when stream URL/path (e.g., `"http://virtual_cam:8091/stream"`).

## Detection & Correlation Flow
- **MQTT / MinIO (`SwarmTelemetryEvent`)**:
  - `metric_type = "detection"`
  - `project_id`, `swarm_id` bound from active `_telemetry_publisher` context
  - `target_class`, `confidence`, `snapshot_uri` (`s3://tactical-snapshots/...`)
- **Memgraph (`TargetCorrelator`)**:
  - Correlates detection events into target nodes accessible via `GET /api/v1/targets?project_id=default-theater` and `GET /api/v1/analytics/detections/{event_id}/snapshot`.
