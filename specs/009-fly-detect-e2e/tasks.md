# Tasks: Fly-and-Detect E2E with Virtual Video Stream

**Input**: Design documents from `/specs/009-fly-detect-e2e/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`

## Phase 1: Virtual Video Stream Infrastructure (`US1`)

- [X] T001 [US1] Implement HTTP MJPEG virtual camera server in `scripts/virtual_cam_server.py` (`GET /stream`, `GET /health`, looping `VIRTUAL_VIDEO_PATH` video or COCO sample image at configurable `VIRTUAL_CAM_FPS`)
- [X] T002 [US1] Add `virtual_cam` service (`8091:8091` on `c2-shared-net`, with `GET /health` healthcheck) to `docker-compose.yml` and set `CAMERA_SOURCE=${CAMERA_SOURCE:-http://virtual_cam:8091/stream}` + `depends_on: virtual_cam (service_healthy)` on `edge_drone`

## Phase 2: Edge Configurable Camera & Decoupled Detect/Flight Control (`US1`, `US2`)

- [X] T003 [US1] Update `CameraStream` in `src/edge/vision/camera.py` to read `source` / `CAMERA_SOURCE` (integer device index or stream URL) via canonical `cv2.VideoCapture`
- [X] T004 [US1] [US2] Add `detection_mode` (`"report_only"` vs `"intercept"`), `on_detect_intercept` callback, and detection publish throttling to `FlightController` in `src/edge/navigation/flight_controller.py`
- [X] T005 [US1] [US2] Decouple `_nav_task` (`POST /navigate`) and `_vision_task` (`POST /target`) in `src/edge/api/server.py` and accept `detection_mode` on `TargetRequest`

## Phase 3: Backend SMEAC Target Dispatch (`US2`)

- [X] T006 [US2] Update `dispatch_edge_mission_activity` in `src/uservice/smeac/operations/process.py` to dispatch `POST /target` alongside `POST /navigate` when `target_object_class` is set (`detection_mode="intercept"` for `strike`, `"report_only"` otherwise)

## Phase 4: Zero-Mock E2E Verification & Regression Checks (`US3`)

- [X] T007 [US3] Create zero-mock `tests/e2e/prod_fly_detect.spec.js` (login, provision swarm, live Point A, submit SMEAC Fly-and-Detect order to Point B, verify `executed`, >150m PX4 displacement, correlated target in `/api/v1/targets` & Target Lineage UI, HTTP 200 JPEG snapshot, and step screenshots)
- [X] T008 Rebuild stack (`docker compose up -d --build`), verify `virtual_cam` + `isc_edge` stream ingestion, and run `prod_fly_detect.spec.js`, full `.venv/bin/pytest -v`, and full `npx playwright test`

## Dependencies & Execution Order

- **Phase 1 (`T001`–`T002`)** and **Phase 2 (`T003`–`T005`)** + **Phase 3 (`T006`)** can be implemented in parallel once contracts in `data-model.md` are fixed (`T001`→`T002`, `T003`→`T004`→`T005`).
- **Phase 4 (`T007`→`T008`)** depends on `T001`–`T006`.

## Phase 5: Convergence

- [X] T009 [SC-004] Diagnose and resolve the `30000ms` timeout on `/api/v1/smeac/draft` in `tests/e2e/pmdl_c2.spec.js` (`T047.3`) so the full Playwright E2E suite passes (`21/21`) alongside `27/27` `pytest`
