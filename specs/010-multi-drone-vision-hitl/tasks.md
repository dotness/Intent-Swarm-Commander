# Tasks: Multi-Drone Vision Streams, Web GUI Snapshots & Detection HITL

**Input**: Design documents from `/specs/010-multi-drone-vision-hitl/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`

## Phase 1: Per-Drone Virtual Camera Channels (`US1`)

- [X] T001 [US1] Refactor `scripts/virtual_cam_server.py` to support isolated per-`drone_id` channels (`GET /stream/{drone_id}`, `POST /feed/{drone_id}`, `GET /feed/{drone_id}` with `^[a-zA-Z0-9_-]{1,64}$` validation, CORS headers, and `/stream` + `/feed` defaulting to `"drone-1"`)
- [X] T002 [US1] Set `VIRTUAL_CAM_BASE_URL=${VIRTUAL_CAM_BASE_URL:-http://virtual_cam:8091}` on `edge_drone` in `docker-compose.yml`

## Phase 2: Multi-Drone Edge Vision Channels (`US1`)

- [X] T003 [US1] Update `EdgeTelemetryPublisher.publish_detection` in `src/edge/telemetry/publisher.py` to accept optional `drone_id` override so multi-drone channels tag MQTT events and MinIO snapshot URIs with their own `drone_id`
- [X] T004 [US1] Update `src/edge/api/server.py` (`TargetRequest`, `POST /target`, `GET /target`) to accept optional `drone_id` (defaulting to `DRONE_ID`), open `CAMERA_SOURCE` or `VIRTUAL_CAM_BASE_URL/stream/{drone_id}` per drone, and run isolated `_vision_tasks[drone_id]` sharing `YoloEInference`

## Phase 3: In-Flight Detection HITL with Snapshot Metadata (`US3`)

- [X] T005 [US3] Add optional `drone_id`, `detection_event_id`, `snapshot_url`, `target_class`, and `confidence` columns/fields to `HitlDecision` (`src/uservice/hitl/models/storage/decision.py`), `HitlPendingItem` (`src/uservice/hitl/models/contract/schemas.py`), `HitlFacade` (`src/uservice/hitl/facade/hitl.py`), and idempotent `ALTER TABLE hitl_decisions ADD COLUMN IF NOT EXISTS` in `src/uservice/database/engine.py`
- [X] T006 [US3] Update `_handle_detection` in `src/uservice/main.py` to create a pending `HitlDecision` (carrying `drone_id`, `detection_event_id`, `snapshot_url`, `target_class`, and `confidence`) when an active `intercept` (`approaching`) detection arrives and no pending HITL exists for that `drone_id`

## Phase 4: Web GUI Vision Panel & HITL Snapshot Modal (`US2`, `US3`)

- [X] T007 [US2] Add a **Drone Vision & Snapshots** panel with a per-`drone_id` selector (`drone-1` … `drone-5`), live `/stream/{drone_id}` `<img>` viewer, and per-drone detection snapshot gallery to `src/dashboard/index.html` and `src/dashboard/js/main.js`
- [X] T008 [US3] Update `showHitlModal` in `src/dashboard/js/hitl.js` to display `drone_id`, `target_class`, confidence, and the cropped detection JPEG snapshot (via `fetchSnapshotBlobUrl`) when `snapshot_url` is present

## Phase 5: Verification (`US1`, `US2`, `US3`)

- [X] T009 Rebuild stack (`docker compose up -d --build`), add and run `tests/e2e/multi_drone_vision_hitl.spec.js` (verifying 5-drone `/feed/{drone_id}` & `/stream/{drone_id}` isolation, `drone-3` detection snapshots in Web GUI, and `#hitl-modal` snapshot rendering + decision), plus full `.venv/bin/pytest -v` and full `npx playwright test`

## Dependencies & Execution Order

- **Phase 1 (`T001`–`T002`)** and **Phase 2 (`T003`–`T004`)** enable per-drone feeds and edge detection tagging.
- **Phase 3 (`T005`–`T006`)** enables detection HITL persistence with snapshot metadata.
- **Phase 4 (`T007`–`T008`)** renders per-drone streams/snapshots in the Web GUI and detection snapshots inside `#hitl-modal`.
- **Phase 5 (`T009`)** verifies everything end-to-end.
