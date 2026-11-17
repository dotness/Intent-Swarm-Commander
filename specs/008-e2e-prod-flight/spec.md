# Feature Specification: End-to-End Production Flight Dispatch & Headless PX4 SITL

**Feature Branch**: `main`  
**Feature Directory**: `specs/008-e2e-prod-flight`  
**Created**: 2026-11-15  
**Status**: Draft  
**Input**: Specify and implement the needed pieces to achieve end-to-end production flight from Point A to Point B without mocks, route intercepts, or DB injections, running `drone_sim` without NVIDIA GPU passthrough.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Headless PX4 SITL & Live MAVSDK Telemetry Link (Priority: P1)

As a system operator on a host without an NVIDIA Docker runtime, I need `drone_sim` (`autonomous_drone_env`) to run PX4 SITL + Gazebo Harmonic in headless CPU mode (`HEADLESS=1`) and stream real MAVLink telemetry to `isc_edge`, so that `isc_backend` ingests live drone coordinates via `pmdl_mosquitto` MQTT.

**Why this priority**: Without a running PX4 SITL autopilot and live MAVSDK → MQTT telemetry stream, no real Point A to Point B flight or `mqtt_live` dashboard tracking is possible.

**Independent Test**: Bring up `drone_sim` and `edge_drone`, query `GET http://localhost:8090/telemetry` and `GET /api/v1/swarms/{id}/telemetry`, and verify real PX4 GPS coordinates (`lat != 0`, `lon != 0`) and `telemetry_source == "mqtt_live"` appear without synthetic injection.

**Acceptance Scenarios**:

1. **Given** a host without `nvidia-container-toolkit`, **When** `docker compose up -d` starts `drone_sim`, **Then** `autonomous_drone_env` starts in `HEADLESS=1` mode with `MicroXRCEAgent` and `make px4_sitl gz_x500`.
2. **Given** `drone_sim` and `edge_drone` are running on `c2-shared-net`, **When** PX4 broadcasts MAVLink telemetry on UDP `14540`, **Then** `isc_edge` connects via MAVSDK, updates its telemetry state, and publishes `SwarmTelemetryEvent` messages to `pmdl_mosquitto` for the active swarm.

---

### User Story 2 - Temporal Worker & Backend-to-Edge Waypoint Dispatch (Priority: P1)

As a human commander submitting a SMEAC movement order, I need `isc_backend` to run a Temporal Worker for `ProcessSmeacWorkflow` that executes safety checks and dispatches extracted waypoints to `isc_edge`, so the drone physically arms, takes off, and flies from Point A to Point B in PX4 SITL.

**Why this priority**: Currently `POST /api/v1/swarms/{id}/orders` stops at `status: "translated"` because no Temporal Worker polls `isc-smeac-queue` and no activity dispatches commands to `isc_edge`.

**Independent Test**: Submit a SMEAC order via `POST /api/v1/swarms/{id}/orders` and verify `ProcessSmeacWorkflow` completes in Temporal, `isc_edge` receives `POST /navigate` with target `(lat, lon, alt_m)`, PX4 SITL arms/takes off/moves toward the target coordinate, and `smeac_orders.status` transitions to `executed`.

**Acceptance Scenarios**:

1. **Given** `isc_backend` starts up, **When** Temporal is reachable on `TEMPORAL_URL`, **Then** an in-process Temporal `Worker` polls `ISC_TASK_QUEUE` (`isc-smeac-queue`) for `ProcessSmeacWorkflow` and its activities.
2. **Given** a swarm provisioned without Docker socket container spawning, **When** `EDGE_DEFAULT_ENDPOINT` is configured (e.g., `http://edge_drone:8090`), **Then** swarm provisioning binds `endpoint_url` to `EDGE_DEFAULT_ENDPOINT` and notifies `isc_edge` of the active `swarm_id` / `project_id` context.
3. **Given** an approved/verified `SwarmCommand` with GeoJSON coordinates, **When** `ProcessSmeacWorkflow` runs `dispatch_edge_mission_activity`, **Then** `isc_backend` posts the waypoints to `isc_edge /navigate` and updates `smeac_orders.status` to `executed`.
4. **Given** `isc_edge` receives `POST /navigate` with target waypoints, **When** MAVSDK is connected to PX4 SITL, **Then** `isc_edge` arms (if disarmed), takes off (if landed), calls `action.goto_location(lat, lon, abs_alt_m, yaw)` for each waypoint, and streams updated positions over MQTT.

---

### User Story 3 - Zero-Mock Production Playwright E2E Flight Test (Priority: P1)

As a human commander validating the live stack, I need a dedicated Playwright E2E test (`tests/e2e/prod_flight.spec.js`) that logs in, creates a swarm, issues a Point A → Point B SMEAC order, and observes the real PX4-driven drone marker move on the Leaflet map with zero mocks, zero `page.route()` intercepts, and zero DB injections.

**Why this priority**: Proves true end-to-end production operation from browser UI → FastAPI → Gemini → Temporal → Edge MAVSDK → PX4 SITL → MQTT → PostgreSQL → Leaflet map.

**Independent Test**: Run `COMMANDER_PASSPHRASE=commander-test-passphrase npx playwright test tests/e2e/prod_flight.spec.js` against the live Docker Compose stack and verify it passes with zero `page.route` calls.

**Acceptance Scenarios**:

1. **Given** the full Docker Compose stack (including `drone_sim` and `edge_drone`) is running, **When** `prod_flight.spec.js` logs in, provisions a new swarm, and selects it, **Then** a real drone marker appears on the Leaflet map from live `mqtt_live` PX4 telemetry.
2. **Given** the drone is hovering/holding at its PX4 home position (Point A), **When** the commander submits a SMEAC order to fly to an offset coordinate (Point B ~100m away), **Then** the order reaches `executed`, and the Leaflet drone marker's live `LatLng` moves meaningfully toward Point B (> 10m displacement) driven purely by PX4 SITL telemetry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `docker-compose.yml` MUST configure `drone_sim` to run in `HEADLESS=1` CPU mode without requiring the `nvidia` Docker device driver, and share/expose MAVLink UDP `14540` with `edge_drone`.
- **FR-002**: `scripts/entrypoint_drone.sh` MUST launch `MicroXRCEAgent udp4 -p 8888` and `HEADLESS=1 make px4_sitl gz_x500` (with `PX4_SIM_HOST_ADDR` / MAVLink broadcast configured so `edge_drone` receives UDP `14540`).
- **FR-003**: `src/uservice/main.py` MUST start and cleanly shut down an in-process Temporal `Worker` polling `ISC_TASK_QUEUE` (`isc-smeac-queue`) with `ProcessSmeacWorkflow` and its registered activities.
- **FR-004**: `src/uservice/smeac/operations/process.py` MUST include a `dispatch_edge_mission_activity` that dispatches parsed `SwarmCommand` target coordinates to the swarm's `endpoint_url` (`POST /navigate`) and marks `smeac_orders.status = "executed"`.
- **FR-005**: `src/uservice/swarm/operations/create.py` MUST fall back to `EDGE_DEFAULT_ENDPOINT` (when set in environment, e.g. `http://edge_drone:8090` in Docker Compose) when `/var/run/docker.sock` is unavailable, so created swarms have a valid reachable `endpoint_url`.
- **FR-006**: `src/edge/api/server.py` MUST expose `POST /navigate` (accepting waypoints `[{lat, lon, alt_m}]` and optional `swarm_id` / `project_id`), bind `_telemetry_publisher` to the active `swarm_id`/`project_id`, arm/takeoff if needed, and execute `goto_location` via MAVSDK against PX4 SITL.
- **FR-007**: `tests/e2e/prod_flight.spec.js` MUST execute the entire workflow through the real browser UI with zero `page.route()` calls, zero `page.evaluate()` state injections, and zero `psql` DB inserts.

### Key Entities

- **Temporal Worker**: In-process `temporalio.worker.Worker` hosted in `isc_backend` lifespan on `isc-smeac-queue`.
- **Navigation Waypoint**: `(lat, lon, alt_m)` extracted from `SwarmCommand.target_area` GeoJSON and dispatched to `isc_edge /navigate`.
- **Edge Telemetry Context**: Active `(project_id, swarm_id, drone_id)` published over MQTT (`isc/{project_id}/{swarm_id}/telemetry/{drone_id}`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `docker compose up -d` starts all 9 services (including `autonomous_drone_env` / `drone_sim`) with exit code `0` on a non-NVIDIA WSL2 host.
- **SC-002**: `GET /api/v1/swarms/{id}/telemetry` returns `telemetry_source: "mqtt_live"` and non-zero PX4 SITL coordinates without synthetic injection.
- **SC-003**: `tests/e2e/prod_flight.spec.js` passes end-to-end, confirming > 10m real PX4 SITL displacement on the Leaflet map after submitting a SMEAC order.
- **SC-004**: Existing `pytest` suite (`27 passed`) continues to pass with zero regressions.
