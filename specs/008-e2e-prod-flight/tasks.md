# Tasks: End-to-End Production Flight Dispatch & Headless PX4 SITL

**Input**: Design documents from `/specs/008-e2e-prod-flight/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`

## Phase 1: Infrastructure & Headless PX4 SITL (`US1`)

- [X] T001 [US1] Configure `drone_sim` in `docker-compose.yml` for headless CPU execution (`HEADLESS=1`, `network_mode: "service:edge_drone"`, remove `nvidia` device reservation) and set `MAVSDK_URL=udp://:14540` on `edge_drone` and `SWARM_DEFAULT_ENDPOINT=http://edge_drone:8090` on `backend`
- [X] T002 [US1] Update `scripts/entrypoint_drone.sh` to run `HEADLESS=1 make px4_sitl sihsim_quadx` alongside `MicroXRCEAgent udp4 -p 8888`

## Phase 2: Edge MAVSDK Navigation & Context Binding (`US1`, `US2`)

- [X] T003 [US1] [US2] Add `POST /context` and `POST /navigate` endpoints to `src/edge/api/server.py` with dynamic `_telemetry_publisher` `(project_id, swarm_id)` binding and MAVSDK arm/takeoff/`goto_location` waypoint flight task

## Phase 3: Backend Temporal Worker & Edge Dispatch (`US2`)

- [X] T004 [US2] Update `src/uservice/swarm/operations/create.py` to sync newly provisioned `(swarm_id, project_id)` context to `endpoint_url` (`POST /context`) when reachable
- [X] T005 [US2] Implement `parse_smeac_activity`, `safety_check_activity`, and `dispatch_edge_mission_activity` (extracting GeoJSON waypoints, posting to `{endpoint_url}/navigate`, and marking `smeac_orders.status = "executed"`) in `src/uservice/smeac/operations/process.py` and pass `swarm_instance_id` / `project_id` / `commands` cleanly
- [X] T006 [US2] Start and gracefully shut down an in-process Temporal `Worker` on `ISC_TASK_QUEUE` (`isc-smeac-queue`) in `src/uservice/main.py` lifespan

## Phase 4: Zero-Mock Production Playwright E2E Test & Verification (`US3`)

- [X] T007 [US3] Create zero-mock `tests/e2e/prod_flight.spec.js` (login, provision swarm, observe live PX4 SITL `mqtt_live` Point A marker, submit SMEAC Point A -> Point B order, verify `executed` status and >10m real drone displacement on Leaflet map with zero `page.route()` or DB injects)
- [X] T008 Rebuild stack (`docker compose up -d --build`), verify `drone_sim` + `isc_edge` live telemetry, and run `prod_flight.spec.js`, full `pytest -v`, and full `npx playwright test`
