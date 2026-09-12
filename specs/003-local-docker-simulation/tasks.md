# Tasks: Local Docker Compose Simulation

**Input**: Design documents from `/specs/003-local-docker-simulation/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/ports.md, quickstart.md

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and containerization infrastructure for the local orchestration environment.

- [X] T001 [P] Create `Dockerfile.drone_sim` in the repository root containerizing Gazebo Harmonic, ROS 2 Humble, and PX4 SITL.
- [X] T002 [P] Create `Dockerfile.backend` in the repository root containerizing FastAPI microservices and dashboard static server.
- [X] T003 [P] Create `scripts/entrypoint_drone.sh` to initialize MicroXRCEAgent UDP bridge and launch PX4 Gazebo SITL per Constitution Principle V.
- [X] T004 Create `docker-compose.yml` in the repository root orchestrating postgres, temporal, backend, dashboard, edge_drone, and drone_sim per `contracts/ports.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core edge service interfaces and communications required before simulation integration.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 [P] Update `src/edge/api/server.py` to configure MAVSDK connection URL via `MAVSDK_URL` environment variable (defaulting to `udp://:14540`).
- [X] T006 [P] Update `src/edge/vision/camera.py` to subscribe to Gazebo simulated ROS 2 topic `/camera/image_raw` via `rclpy` when `SIMULATION_MODE=true`.
- [X] T007 Wire `src/edge/api/server.py` `/target` endpoint to instantiate `FlightController` and trigger autonomous navigation loop per SC-003.
- [X] T008 Wire `src/edge/api/server.py` `/telemetry` endpoint to stream live MAVSDK drone telemetry (position, battery, heading) per SC-002 and SC-004.

**Checkpoint**: Foundation ready — edge microservices and simulation connection endpoints are established.

---

## Phase 3: User Story 1 - Local E2E Simulation Environment (Priority: P1) 🎯 MVP

**Goal**: Run the entire Intent-Swarm-Commander stack locally on a single machine for testing and MVP validation via Docker Compose.

**Independent Test**: Execute `docker compose up -d` and run `quickstart.md` scenarios (verify all services start, Gazebo SITL connects, telemetry streams at $\ge 5\text{ Hz}$, and SMEAC order executes takeoff).

### Implementation for User Story 1

- [X] T009 [P] [US1] Inject `SIMULATION_MODE=true` into edge drone container environment definitions in `docker-compose.yml`.
- [X] T010 [P] [US1] Configure Gazebo GUI display passthrough (`DISPLAY`, `WAYLAND_DISPLAY`, `/tmp/.X11-unix`, `/mnt/wslg`) and GPU reservations in `docker-compose.yml`.
- [X] T011 [US1] Configure simulation container entrypoint (`/opt/entrypoint_drone.sh`) and restart policies (`restart: unless-stopped`) in `docker-compose.yml`.
- [X] T012 [US1] Update dashboard telemetry polling in `src/dashboard/js/main.js` to 200 ms interval to satisfy SC-002 (5 Hz throughput).
- [X] T013 [US1] Implement automated integration test assertions in `tests/integration/test_e2e.py` verifying edge simulation endpoints and telemetry responses.
- [X] T014 [US1] Execute full container build and startup validation via `docker compose build` and `docker compose up -d` per SC-001.
- [X] T015 [US1] Execute end-to-end mission and telemetry validation defined in `quickstart.md` Scenario 3.

**Checkpoint**: At this point, User Story 1 is fully functional and verifiable end-to-end.

---

## Phase 4: Polish & Governance

**Purpose**: Cross-cutting documentation, sanitization, and constitutional governance.

- [X] T016 [P] Update root `README.md` with local Docker Compose prerequisites, GPU passthrough instructions, and startup commands.
- [X] T017 [P] Audit and sanitize orchestrator configurations to ensure no hardcoded host IPs remain in `src/` or `docker-compose.yml`.
- [X] T018 Conduct formal architectural review using `.agents/agents/uservice-arch-reviewer` to verify compliance with Constitution standards.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion.
- **Polish & Governance (Phase 4)**: Depends on User Story 1 completion.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — self-contained MVP increment.

### Parallel Opportunities

- In Phase 1: `T001`, `T002`, and `T003` can run in parallel.
- In Phase 2: `T005` and `T006` can run in parallel.
- In Phase 3: `T009` and `T010` can run in parallel.
- In Phase 4: `T016` and `T017` can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch environment and GUI passthrough configurations in parallel:
Task: "Inject SIMULATION_MODE=true into edge drone container environment definitions in docker-compose.yml"
Task: "Configure Gazebo GUI display passthrough (X11/Wayland/WSLg) and GPU reservations in docker-compose.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (container definitions, entrypoint, orchestrator).
2. Complete Phase 2: Foundational (MAVSDK connection, ROS 2 camera subscriber, flight controller & telemetry wiring).
3. Complete Phase 3: User Story 1 (compose environment, dashboard 5 Hz telemetry, E2E validation).
4. **STOP and VALIDATE**: Verify all `quickstart.md` scenarios.
5. Complete Phase 4: Polish & Governance (documentation, sanitization, arch review).
