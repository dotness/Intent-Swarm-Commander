# Implementation Plan: End-to-End Production Flight Dispatch & Headless PX4 SITL

**Branch**: `main` | **Date**: 2026-11-15 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/008-e2e-prod-flight/spec.md`

## Summary

Wire the full production execution path from browser SMEAC order → `isc_backend` Temporal Worker → `isc_edge` MAVSDK `/navigate` → headless PX4 SITL + Gazebo Harmonic (`drone_sim`) → `pmdl_mosquitto` MQTT → PostgreSQL `swarm_live_states` → Leaflet map, and add a zero-mock Playwright E2E test (`tests/e2e/prod_flight.spec.js`) verifying real simulated Point A → Point B flight.

## Technical Context

**Language/Version**: Python 3.10+ (containers) / 3.14 (`.venv`), Node.js Playwright `^1.48.0`  
**Primary Dependencies**: FastAPI, Temporalio (`temporalio.worker.Worker`), MAVSDK, PX4-Autopilot `release/1.14`, Gazebo Harmonic (`gz_x500`), `httpx`, Paho/aiomqtt  
**Target Platform**: Docker Compose on Linux/WSL2 (`c2-shared-net`, headless CPU PX4 SITL without NVIDIA runtime)  
**Testing**: `pytest` (unit/contract/integration) + `playwright test` (`tests/e2e/prod_flight.spec.js`)  

## Constitution Check

- **P1.1 Real-Time Telemetry & P2.1 No Fallback**: Zero mocks, zero `page.route()`, zero synthetic telemetry in production code. All telemetry originates from PX4 SITL → MAVSDK → MQTT → `TelemetryIngestor`.
- **P2.2 Temporal Durable Workflows**: `ProcessSmeacWorkflow` is executed by an in-process Temporal `Worker` on `isc-smeac-queue`.
- **P3.1 Security**: `COMMANDER_PASSPHRASE` fail-closed auth enforced on all C2 endpoints.

## Project Structure

### Documentation (this feature)
- `specs/008-e2e-prod-flight/spec.md`
- `specs/008-e2e-prod-flight/plan.md`
- `specs/008-e2e-prod-flight/research.md`
- `specs/008-e2e-prod-flight/data-model.md`
- `specs/008-e2e-prod-flight/quickstart.md`
- `specs/008-e2e-prod-flight/tasks.md`

### Source & Infrastructure Changes
- `docker-compose.yml` — Remove NVIDIA GPU reservation on `drone_sim`, set `HEADLESS=1`, share `edge_drone` network namespace (`network_mode: "service:edge_drone"`) so MAVLink UDP `14540` hits `isc_edge` on loopback cleanly, set `SWARM_DEFAULT_ENDPOINT=http://edge_drone:8090` on `backend`, and set `MAVSDK_URL=udpin://0.0.0.0:14540` on `edge_drone`.
- `scripts/entrypoint_drone.sh` — Launch `MicroXRCEAgent udp4 -p 8888 &` and `HEADLESS=1 make px4_sitl gz_x500`.
- `src/edge/api/server.py` — Add `POST /context` and `POST /navigate` endpoints with MAVSDK arm, takeoff, and `goto_location` execution + dynamic `_telemetry_publisher` swarm/project binding.
- `src/uservice/swarm/operations/create.py` — Sync newly provisioned `swarm_id`/`project_id` context to `endpoint_url` (`POST /context`) when available.
- `src/uservice/smeac/operations/process.py` & `src/uservice/smeac/operations/activities.py` (or inside `process.py`) — Implement `parse_smeac_activity`, `safety_check_activity`, and `dispatch_edge_mission_activity` (extracting waypoints from `SwarmCommand.target_area`, calling `POST {endpoint_url}/navigate`, and updating `smeac_orders.status = "executed"`).
- `src/uservice/main.py` — Start and gracefully shut down the Temporal `Worker` on `ISC_TASK_QUEUE` (`isc-smeac-queue`) when Temporal is reachable.
- `tests/e2e/prod_flight.spec.js` — Zero-mock Playwright E2E test flying real PX4 SITL from Point A to Point B.
