# Feature Specification: Multi-Drone Vision Streams, Web GUI Snapshots & Detection HITL

**Feature Branch**: `010-multi-drone-vision-hitl`  
**Created**: 2026-11-17  
**Status**: Clarified  
**Input**: User description: "so that i can /feed and /stream separately, also watch snapshots in webgui and hitl separately."

## Clarifications

### Session 2026-11-17

- **Q1**: How should `isc_edge` run YOLO-E vision pipelines for multiple drones (`drone-1` … `drone-5`)? → **A**: Multi-channel `isc_edge` (`POST /target` accepts optional `drone_id`, opening `/stream/{drone_id}` per drone and sharing one loaded `YoloEInference` model for lightweight local simulation), while remaining fully compatible with 1:1 standalone Raspberry Pi 5 deployments (`DRONE_ID=drone-k`, `CAMERA_SOURCE=0`).
- **Q2**: How should detection HITL with snapshots trigger during a mission? → **A**: When an in-flight target detection occurs in `intercept` / `hitl_on_detect` mode, `TelemetryIngestor` / `HitlFacade` creates a pending `HitlDecision` carrying `drone_id`, `detection_event_id`, `snapshot_url`, `target_class`, and `confidence`, so `#hitl-modal` displays the cropped JPEG snapshot from MinIO for per-drone visual approval.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Drone Virtual Camera `/feed/{drone_id}` & `/stream/{drone_id}` (Priority: P1)

As an Operator or QA Engineer simulating a multi-drone swarm (e.g., 5 drones: `drone-1` … `drone-5`), I want to feed distinct video/image inputs into each drone individually (`POST /feed/{drone_id}`) and read each drone's live video feed independently (`GET /stream/{drone_id}`) so that feeding a target video to `drone-3` triggers detection only on `drone-3` without affecting `drone-1`, `drone-2`, `drone-4`, or `drone-5`.

**Why this priority**: Independent per-drone `/feed/{drone_id}` and `/stream/{drone_id}` channels are the foundation for multi-drone vision testing, per-drone telemetry tagging, and per-drone UI monitoring.

**Independent Test**: Start `isc_virtual_cam`, send `POST /feed/drone-1` (`{"mode": "clear"}`) and `POST /feed/drone-3` (`{"mode": "target"}`), and verify `GET /stream/drone-1` emits clear frames while `GET /stream/drone-3` emits target frames, while unparameterized `/feed` and `/stream` continue to target `"drone-1"`.

**Acceptance Scenarios**:

1. **Given** `isc_virtual_cam` is running, **When** a client sends `POST /feed/{drone_id}` with `{"mode": "target", "path": "..."}` or `{"mode": "clear"}`, **Then** only that `drone_id`'s `_FrameProvider` updates and `GET /stream/{drone_id}` reflects the new feed immediately without dropping existing connections.
2. **Given** 5 drones (`drone-1` … `drone-5`) in a swarm, **When** `drone-3` is fed a target video while the other 4 drones receive `"clear"` frames, **Then** only `drone-3` emits `metric_type="detection"` telemetry events tagged with `drone_id="drone-3"`.
3. **Given** legacy callers using `POST /feed` or `GET /stream` without a `drone_id`, **When** those endpoints are called, **Then** they route to `"drone-1"` transparently for full backwards compatibility.

---

### User Story 2 - Watch Live Drone Streams & Per-Drone Snapshots in Web GUI (Priority: P2)

As a Commander using the ISC Dashboard (`http://localhost:8080`), I want to select any drone in the active swarm to watch its live camera stream (`/stream/{drone_id}`) and inspect its detection snapshots separately in the Web GUI so I can monitor what each drone sees in real time and review each drone's captured crops.

**Why this priority**: Operators currently have to open `http://localhost:8091/stream` manually in a separate tab and click map markers one by one to see snapshots; a unified per-drone vision viewer in the dashboard closes that situational-awareness gap.

**Independent Test**: Open the dashboard, select a swarm with multiple drones (`drone-1` … `drone-5`), switch the Vision panel selector between `drone-1` and `drone-3`, and verify the live stream `<img>` URL switches between `/stream/drone-1` and `/stream/drone-3` and displays `drone-3`'s detection snapshots separately from `drone-1`.

**Acceptance Scenarios**:

1. **Given** an authenticated Commander on the dashboard, **When** a swarm is active, **Then** a **Drone Vision & Snapshots** panel lets the user select a `drone_id` (e.g., `drone-1` … `drone-5`) to view that drone's live MJPEG stream (`/stream/{drone_id}`).
2. **Given** detection events exist for `drone-3`, **When** the user views `drone-3` in the Vision panel or Target Lineage modal, **Then** `drone-3`'s JPEG snapshots load via authenticated backend proxy (`/api/v1/analytics/detections/{event_id}/snapshot`) filtered/grouped by `drone_id`.
3. **Given** no detections exist yet for `drone-2`, **When** the user selects `drone-2`, **Then** the snapshot gallery shows an empty state for `drone-2` while still showing `drone-2`'s live `/stream/drone-2` feed.

---

### User Story 3 - Per-Drone Detection Snapshots in HITL Approval Modal (Priority: P3)

As a Commander, when an in-flight target detection triggers a Human-in-the-Loop (HITL) decision (or when approving target engagement for a specific drone), I want the HITL modal (`#hitl-modal`) to display the exact `drone_id`, `target_class`, confidence, and cropped JPEG detection snapshot captured by that drone so I can visually verify what that drone saw before clicking Approve or Reject.

**Why this priority**: Blindly approving an automated strike/intercept without seeing the drone's actual detection image undermines C4ISR human-on-the-loop safety.

**Independent Test**: Trigger a detection on `drone-3` that creates a pending HITL decision referencing `event_id` / `snapshot_url`, verify `#hitl-modal` opens displaying `drone-3`'s cropped JPEG snapshot alongside Approve/Reject controls, and verify approving/rejecting applies only to that drone's decision.

**Acceptance Scenarios**:

1. **Given** a pending HITL decision created with detection metadata (`drone_id`, `event_id` / `snapshot_url`, `target_class`, `confidence`), **When** `#hitl-modal` opens on the dashboard, **Then** it renders the cropped detection JPEG snapshot inside the modal alongside the action summary and `drone_id`.
2. **Given** two drones (`drone-2` and `drone-3`) each have pending detection HITL requests, **When** the Commander views pending HITL decisions, **Then** each decision clearly identifies its `drone_id` and snapshot and can be approved or rejected independently without affecting the other drone.
3. **Given** a pre-flight HITL request without a detection snapshot (e.g., ThreatZone overlap before launch), **When** `#hitl-modal` opens, **Then** it renders cleanly without a broken image element.

---

### Edge Cases

- What happens if `POST /feed/{drone_id}` or `GET /stream/{drone_id}` is called for a `drone_id` not pre-configured at startup? `virtual_cam_server.py` dynamically initializes a new `_FrameProvider(mode="clear")` for that `drone_id` (capped at a safe max channel limit or using clean URL-safe `drone_id` validation).
- What happens if `drone_id` contains path traversal characters (e.g. `..` or `/`)? `virtual_cam_server.py` MUST validate `drone_id` against `^[a-zA-Z0-9_-]{1,64}$` and reject invalid IDs with HTTP `400`.
- What happens if a detection snapshot fails to load or MinIO is temporarily slow when `#hitl-modal` opens? The HITL modal MUST still display the `action_summary`, `drone_id`, and Approve/Reject buttons without blocking operator decisions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `scripts/virtual_cam_server.py` MUST support per-drone channels via `GET /stream/{drone_id}` and `POST /feed/{drone_id}` (and `GET /feed/{drone_id}`), while preserving `GET /stream` and `POST /feed` as aliases for `"drone-1"`.
- **FR-002**: `scripts/virtual_cam_server.py` MUST validate `drone_id` strictly (`^[a-zA-Z0-9_-]{1,64}$`) and isolate `_FrameProvider` state per `drone_id` so switching feed mode/path on one drone never alters another drone's stream.
- **FR-003**: `src/edge/api/server.py` MUST support per-`drone_id` vision channels (`POST /target` accepting optional `drone_id`, defaulting to `DRONE_ID`, opening the corresponding `CAMERA_SOURCE` / `/stream/{drone_id}` and sharing `YoloEInference` across active channels) so each drone's detections and MinIO snapshots are tagged with its own `drone_id`, while preserving 1:1 `DRONE_ID`/`CAMERA_SOURCE` behavior on physical Raspberry Pi 5 nodes.
- **FR-004**: The backend HITL contract (`HitlDecision` / `HitlPendingItem` / `create_hitl_request`) MUST support optional detection context fields (`drone_id`, `detection_event_id`, `snapshot_url`, `target_class`, `confidence`), and `TelemetryIngestor` MUST create a pending `HitlDecision` with these fields when an active `intercept` / `hitl_on_detect` detection arrives.
- **FR-005**: The dashboard UI (`src/dashboard/index.html`, `src/dashboard/js/`) MUST include a **Drone Vision & Snapshots** panel with a per-drone selector to watch `/stream/{drone_id}` live and view captured detection snapshots filtered by `drone_id`.
- **FR-006**: The dashboard HITL modal (`src/dashboard/js/hitl.js`) MUST render the drone's cropped JPEG detection snapshot (fetched securely via `fetchSnapshotBlobUrl` when `snapshot_url` / `detection_event_id` is present) and `drone_id` label, and allow deciding each drone's pending HITL independently.
- **FR-007**: Zero-mock E2E and integration tests MUST verify independent `/feed/{drone_id}` & `/stream/{drone_id}` behavior across multiple drones (e.g., `drone-1` vs `drone-3`), per-drone snapshot display in the Web GUI, and detection snapshot rendering inside `#hitl-modal`.

### Key Entities

- **Virtual Camera Channel (`drone_id`)**: Isolated `_FrameProvider` instance serving `GET /stream/{drone_id}` and controlled via `POST /feed/{drone_id}`.
- **Drone Detection Snapshot**: Cropped JPEG stored in MinIO `tactical-snapshots`, indexed by `event_id` and `drone_id`, served via `/api/v1/analytics/detections/{event_id}/snapshot`.
- **Detection HITL Decision**: `HitlDecision` record linked to a `SwarmCommand`, optionally carrying `drone_id` and `detection_event_id` / `snapshot_url` for visual confirmation in `#hitl-modal`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sending `POST /feed/drone-3` (`{"mode": "target"}`) while `drone-1`, `drone-2`, `drone-4`, `drone-5` remain `"clear"` results in `GET /stream/drone-3` serving target frames while the other 4 streams remain `"clear"` (`100%` channel isolation).
- **SC-002**: Selecting any `drone_id` in the dashboard Vision panel updates the displayed live stream to `/stream/{drone_id}` and filters the snapshot gallery to that drone's detections within `2s`.
- **SC-003**: When a detection HITL request with `snapshot_url` opens in `#hitl-modal`, the modal displays a valid loaded `<img>` (`naturalWidth > 0`) alongside `drone_id`, and Approve/Reject completes without breaking pre-flight text-only HITL flows.
- **SC-004**: All `pytest` and Playwright E2E tests (including new multi-drone `/feed` + `/stream` + GUI/HITL snapshot tests) pass `100%` with zero mocks in `src/`.

## Assumptions

- Host-side browser access to `http://localhost:8091/stream/{drone_id}` works directly via the existing `8091:8091` port mapping on `virtual_cam` in `docker-compose.yml` (configurable via UI/window config for non-localhost deployments).
- Existing `CAMERA_SOURCE` and `DRONE_ID` environment variables remain backwards-compatible for single-drone edge deployments.
