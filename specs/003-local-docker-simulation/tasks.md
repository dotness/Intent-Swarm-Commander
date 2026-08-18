# Tasks: Local Docker Compose Simulation

**Input**: Design documents from `/specs/003-local-docker-simulation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ports.md

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for the orchestration environment.

- [x] T001 Create `Dockerfile.drone_sim` in the repository root (adapted from `Drone-Swarm`'s Dockerfile) for Gazebo/ROS2/PX4 edge node containerization.
- [x] T002 Create `Dockerfile.backend` in the repository root for the FastAPI microservices (edge/uservice) and dashboard.
- [x] T003 Create `docker-compose.yml` in the repository root bridging the services based on `contracts/ports.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before the simulation can run end-to-end.

- [x] T004 [P] Update `src/edge/api/server.py` or `src/edge/flight/controller.py` to allow overriding the MAVSDK connection URL via an environment variable (defaulting to `udp://:14540` for SITL).
- [x] T005 [P] Implement/verify the MicroXRCEAgent startup within the `Dockerfile.drone_sim` entrypoint to ensure telemetry bridging works upon container boot.

**Checkpoint**: Foundation ready - containers can be built and internal code supports the simulation endpoints.

---

## Phase 3: User Story 1 - Local E2E Simulation Environment (Priority: P1) 🎯 MVP

**Goal**: Run the entire Intent-Swarm-Commander stack locally on a single machine for testing and MVP validation.

**Independent Test**: Can be tested by running `docker compose up` on a host machine and verifying that all services start successfully.

### Implementation for User Story 1

- [x] T006 [P] [US1] Inject `SIMULATION_MODE=true` into the edge drone container definitions inside `docker-compose.yml`.
- [x] T007 [P] [US1] Define volume mounts for Gazebo GUI passthrough (X11/Wayland/WSLg) in `docker-compose.yml` to allow the 3D visualizer to spawn on the host.
- [x] T008 [US1] Configure Docker Compose networking (e.g., `network_mode: host` or bridged with specific exposed ports from `contracts/ports.md`).
- [x] T009 [US1] Update `src/edge/vision/camera.py` to consume the ROS 2 `/camera/image_raw` topic via `rclpy` when `SIMULATION_MODE=true`, instead of emitting mock frames.
- [x] T010 [US1] Test container orchestration via `docker compose build` and `docker compose up -d`.
- [x] T011 [US1] Perform the end-to-end validation defined in `quickstart.md`, including Scenario 3 (submitting SMEAC order triggers Gazebo drone takeoff) and explicitly verifying the 5 Hz telemetry throughput on the dashboard.
- [x] T014 [US1] Configure Docker Compose restart policies (e.g., `restart: unless-stopped`) for the simulation containers to handle edge cases like Gazebo crashes or MicroXRCEAgent failures.

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T012 Update root README.md with the new Docker Compose local development instructions.
- [x] T013 Code cleanup and ensuring no hardcoded IPs remain in the orchestrator config.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories.

### Parallel Opportunities

- Dockerfile creations (T001, T002) can happen in parallel.
- Internal python configuration (T004) and Docker entrypoints (T005) can be developed independently.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently using `docker compose up`
5. Deploy/demo if ready

## Phase 5: Convergence

- [x] T015 Connect API target assignment to trigger `FlightController` execution per SC-003 (missing). CRITICAL.
- [x] T016 Wire API `/telemetry` endpoint to MAVSDK drone telemetry stream instead of mock random data per SC-002, SC-004 (contradicts).
