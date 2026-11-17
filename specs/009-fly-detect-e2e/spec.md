# Feature Specification: Fly-and-Detect E2E with Virtual Video Stream

**Feature Branch**: `009-fly-detect-e2e`  
**Created**: 2026-11-17  
**Status**: Clarified  
**Input**: User description: "I want you to cover what is needed to Support Fly-and-Detect E2E with virtual video stream."

## Clarifications

### Session 2026-11-17

- **Q**: When should `isc_edge` start YOLO-E target detection during a Fly-and-Detect SMEAC mission? → **A**: Start YOLO-E detection immediately in parallel with `POST /navigate` takeoff/transit.
- **Q**: When YOLO-E detects the target object during transit, how should `isc_edge` handle flight control? → **A**: Driven by command business logic — route/ISR missions (`patrol`, `recon`, `escort`, `transport`) publish detections + snapshots and continue flying to Point B (`report_only` / passive mode), whereas `strike` (seek-and-destroy, post-HITL) interrupts waypoint transit and flies/approaches the detected target (`intercept` mode).
- **Q**: How should the virtual video stream service supply frames for Fly-and-Detect E2E? → **A**: Continuous looping feed from a configurable input video file (`VIRTUAL_VIDEO_PATH`), so operators/tests can feed any real video into the simulation and observe how the drone reacts (reporting detections along the route in `report_only` mode or engaging in `intercept` mode).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Virtual Video Stream Ingestion on Edge Node (Priority: P1)

As an Edge Drone operator/simulation environment, the edge node must be able to open and continuously read frames from a configurable virtual video stream (e.g., RTSP, HTTP MJPEG, or video stream URL) in addition to a local hardware camera index so that YOLO-E object detection and `FlightController` execute identically in headless Docker/PX4 simulation and on Raspberry Pi hardware.

**Why this priority**: Without a working video stream inside the headless container (`Failed to open camera device 0`), `FlightController` aborts immediately and cannot run YOLO-E inference, capture detection crops, or publish detection telemetry.

**Independent Test**: Start the virtual video stream service and `isc_edge`, send `POST /target` for a known object class present in the stream, and verify `isc_edge` opens the stream, runs YOLO-E inference, detects the object, and publishes `metric_type="detection"` telemetry with a non-empty JPEG snapshot crop to MinIO/MQTT.

**Acceptance Scenarios**:

1. **Given** a virtual video stream endpoint configured for `isc_edge`, **When** `isc_edge` starts, **Then** `CameraStream` opens the stream cleanly without hardware `/dev/video0` errors and delivers continuous frames.
2. **Given** a stream that reaches end-of-file or experiences a transient frame drop, **When** `CameraStream.read_frame()` reads frames during an active mission, **Then** the stream loops/recovers cleanly so long-running patrols do not abort prematurely.
3. **Given** `FlightController` is running on a virtual stream containing a target class (e.g., `person` or `car`), **When** YOLO-E detects the object above the confidence threshold, **Then** `EdgeTelemetryPublisher` emits a `detection` event with `target_class`, `confidence`, and `snapshot_uri` stored in MinIO `tactical-snapshots`.

---

### User Story 2 - Combined Flight + Target Detection Dispatch from SMEAC Order (Priority: P2)

As a Commander, when I submit a SMEAC order specifying both a destination area/waypoint (Point B) and a target object class to identify (e.g., `"recon"` / `"patrol"` for `"vehicle"` or `"person"` at Point B), the backend must dispatch both physical navigation to Point B and vision target detection on the edge node so the drone flies there and autonomously scans for the object.

**Why this priority**: Currently `dispatch_edge_mission_activity` only calls `POST /navigate` and ignores `target_object_class`, leaving the edge vision/detection pipeline disconnected from SMEAC mission execution.

**Independent Test**: Submit a SMEAC order containing a target waypoint and `target_object_class`, verify `ProcessSmeacWorkflow` completes with status `executed`, and confirm `isc_edge` receives both `/navigate` and `/target` assignments for that command.

**Acceptance Scenarios**:

1. **Given** a parsed `SwarmCommand` with both waypoints (`target_area`) and a non-empty `target_object_class`, **When** `dispatch_edge_mission_activity` executes, **Then** it dispatches navigation (`POST /navigate`) and arms/activates target detection (`POST /target`) on the edge node without cancelling the waypoint flight before arrival.
2. **Given** a parsed `SwarmCommand` without `target_object_class`, **When** `dispatch_edge_mission_activity` executes, **Then** it executes waypoint navigation only, preserving existing Point A → Point B behavior.
3. **Given** the drone reaches the vicinity of Point B while scanning, **When** YOLO-E detects the requested `target_object_class`, **Then** `isc_edge` publishes the detection event to MQTT, `isc_backend` ingests it, `TargetCorrelator` persists/correlates the target in Memgraph, and the detection snapshot is stored in MinIO `tactical-snapshots`.

---

### User Story 3 - Zero-Mock Playwright Fly-and-Detect E2E Verification (Priority: P3)

As a QA/System Engineer, I want a zero-mock Playwright E2E test (`tests/e2e/prod_fly_detect.spec.js`) that logs into the dashboard, provisions a swarm, observes live PX4 SITL Point A telemetry, submits a SMEAC order to fly to Point B and detect a target object, verifies real drone movement to Point B, and verifies the resulting correlated detection and snapshot crop appear in the dashboard UI (Target Lineage / Map / Unit Roster) and PMDL stores.

**Why this priority**: Provides full production-path confidence across C2 UI, Gemini intent parsing, Temporal workflow, MAVSDK/PX4 SITL flight, virtual video stream + YOLO-E detection, MQTT, MinIO snapshots, Memgraph correlation, and dashboard visualization.

**Independent Test**: Run `npx playwright test tests/e2e/prod_fly_detect.spec.js` against the running Docker Compose stack (including the virtual video stream service) and observe all assertions pass without `page.route()` or DB injections.

**Acceptance Scenarios**:

1. **Given** the full Docker Compose stack with headless PX4 SITL and the virtual video stream running, **When** Playwright submits a SMEAC recon/patrol order for Point B with a target object class, **Then** the test observes the order reach `executed`, real PX4 displacement toward Point B on the Leaflet map, at least one correlated target detection in `GET /api/v1/targets` and the Target Lineage UI, and a valid HTTP 200 JPEG snapshot image from `/api/v1/analytics/detections/{event_id}/snapshot`.
2. **Given** step-by-step E2E execution, **When** the test runs, **Then** it captures screenshots at key stages (Point A, flight in transit, Point B arrival, target detection & snapshot visible in UI).

---

### Edge Cases

- What happens if `POST /navigate` and `POST /target` are both called on `isc_edge`? Cancelling `_flight_task` in `/target` must NOT abort an active waypoint navigation task (`_nav_task` vs `_vision_task` must run concurrently or transition cleanly upon arrival).
- What happens if the virtual video stream disconnects or reaches end-of-file before the drone arrives at Point B? The stream reader or media server must loop continuously so frames remain available throughout the flight.
- What happens if YOLO-E detects multiple frames of the same object? `TargetCorrelator` must deduplicate/correlate nearby detections into a correlated target without flooding the UI.
- What happens if `CAMERA_SOURCE` is unset or unreachable? Per Constitution Principle VII, `CameraStream` must fail fast with a clear error rather than synthesizing fake frames or mock detections inside `src/`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `CameraStream` MUST accept a configurable media source (`CAMERA_SOURCE`, supporting integer device index or stream URL such as RTSP/HTTP MJPEG/video stream) via a single canonical `cv2.VideoCapture` path with zero mock frame generators in `src/`.
- **FR-002**: A dedicated virtual video stream container/service in `docker-compose.yml` MUST serve real video frames from a configurable input video file (`VIRTUAL_VIDEO_PATH`, looping continuously) over the internal Docker network (`c2-shared-net`) to `isc_edge`, containing detectable COCO/YOLO object classes (e.g., `person` or `car`) for E2E verification.
- **FR-003**: `isc_edge` MUST decouple navigation flight tasks (`_nav_task` via `POST /navigate`) from vision detection tasks (`_vision_task` via `POST /target`) and accept a `detection_mode` (`"report_only"` vs `"intercept"`) on `POST /target`:
  - In `"report_only"` mode (used for `patrol`, `recon`, `escort`, `transport`), `FlightController` runs YOLO-E in parallel, publishes detection telemetry and JPEG snapshot crops, and does **not** cancel or override `_nav_task`.
  - In `"intercept"` mode (used for `strike` / seek-and-destroy after HITL approval), once a matching target is detected above the confidence threshold, `isc_edge` cancels `_nav_task` and hands flight control to `FlightController` to approach/engage the detected target.
- **FR-004**: When `FlightController` detects a matching `target_object_class` above the confidence threshold, `EdgeTelemetryPublisher` MUST publish a `SwarmTelemetryEvent` (`metric_type="detection"`) tagged with the active `(project_id, swarm_id)` and upload the cropped JPEG snapshot to MinIO `tactical-snapshots`.
- **FR-005**: `dispatch_edge_mission_activity` in `src/uservice/smeac/operations/process.py` MUST dispatch both `POST /navigate` and `POST /target` (passing `command_id`, `target_object_class`, and business-logic-derived `detection_mode`: `"intercept"` for `strike`, `"report_only"` otherwise) whenever a `SwarmCommand` specifies `target_object_class`.
- **FR-006**: `isc_backend`'s `TelemetryIngestor` + `TargetCorrelator` MUST correlate incoming `detection` events from `isc_edge` in Memgraph so they are queryable via `/api/v1/targets` and viewable in the dashboard Target Lineage UI.
- **FR-007**: A zero-mock Playwright E2E test (`tests/e2e/prod_fly_detect.spec.js`) MUST verify the complete Fly-and-Detect flow end-to-end (Login → Swarm Provision → Point A → SMEAC Fly+Detect Order → Real PX4 Displacement → Correlated Target Detection & JPEG Snapshot in UI) without `page.route()` intercepts or database injections.

### Key Entities

- **Virtual Video Stream**: Networked video feed (RTSP/HTTP MJPEG) providing real encoded frames from test media assets to `isc_edge` inside Docker without GPU or physical `/dev/video0`.
- **Detection Telemetry Event (`SwarmTelemetryEvent`)**: MQTT/Parquet event with `metric_type="detection"`, `target_class`, `confidence`, `snapshot_uri`, coordinates `(lat, lon, alt_m)`, and `(project_id, swarm_id)`.
- **Correlated Target**: Memgraph entity aggregated by `TargetCorrelator` from one or more nearby detection events within the spatial/temporal correlation window.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `isc_edge` opens the virtual video stream on startup with zero `Failed to open camera device` errors and processes frames with YOLO-E (`yolov8n.pt`).
- **SC-002**: Submitting a Fly-and-Detect SMEAC order causes `isc_edge` to fly the PX4 SITL drone `> 150m` from Point A toward Point B AND emit at least 1 real YOLO-E detection event with an accessible JPEG snapshot in MinIO (`HTTP 200`, `image/jpeg`).
- **SC-003**: `TargetCorrelator` records the correlated target in Memgraph so it appears in `GET /api/v1/targets` and the Dashboard Target Lineage UI within `30s` of arrival/detection.
- **SC-004**: `tests/e2e/prod_fly_detect.spec.js` passes `100%` end-to-end with zero mocks, and all existing `pytest` (`27+`) and Playwright (`20+`) tests remain passing.

## Assumptions

- `isc_edge` continues running `yolov8n.pt` on CPU inside Docker (already downloaded and working in `isc_edge`).
- The virtual video stream service runs in Docker alongside `edge_drone` and `drone_sim` (using e.g. `ffmpeg` + `mediamtx` RTSP or a lightweight HTTP MJPEG server streaming real frames from a bundled sample video/image asset) so no host webcam or NVIDIA GPU is required.
- Existing `CAMERA_SOURCE` default (`0`) remains supported for Raspberry Pi / local hardware deployments when not overridden in `docker-compose.yml`.
