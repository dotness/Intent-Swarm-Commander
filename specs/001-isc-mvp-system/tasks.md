# Tasks: Intent Swarm Commander — MVP System

**Input**: Design documents from `/specs/001-isc-mvp-system/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), data-model.md, contracts/, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create backend project structure (`src/uservice/`) per implementation plan
- [x] T002 Initialize edge project structure (`src/edge/`)
- [x] T003 Initialize dashboard project structure (`src/dashboard/`)
- [x] T004 [P] Create Docker Compose setup (`src/docker/docker-compose.yml`) including Postgres and Temporal
- [x] T004a Setup mock drone simulation environment using ROS 2, PX4, and Gazebo inside Docker Compose (referencing Drone-Swarm architecture)
- [x] T005 [P] Configure basic linting and formatting tools

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [x] T006 Setup database schema and SQLAlchemy models for shared entities (`src/uservice/database/`)
- [x] T007 [P] Implement Temporal operations facade (`src/uservice/operation/`)
- [x] T008 [P] Configure error handling and logging infrastructure for FastAPI
- [x] T009 [P] Initialize base pydantic-ai agent class (`src/uservice/base/agent.py`)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Commander Submits SMEAC Intent (Priority: P1) 🎯 MVP

**Goal**: System parses a SMEAC order and translates it into coarse-grained Swarm Commands.

**Independent Test**: API receives SMEAC and returns valid JSON swarm commands.

### Implementation for User Story 1

- [x] T010 [P] [US1] Create SMEAC Order model in `src/uservice/smeac/models/smeac.py`
- [x] T011 [P] [US1] Create Swarm Command model in `src/uservice/smeac/models/command.py`
- [x] T012 [US1] Implement SMEAC parsing agent in `src/uservice/smeac/operations/smeac_agents.py`
- [x] T013 [US1] Implement SMEAC processing Temporal workflow in `src/uservice/smeac/operations/process.py` (depends on T012)
- [x] T014 [US1] Implement SMEAC ingestion API endpoint in `src/uservice/smeac/api/routes.py`

**Checkpoint**: User Story 1 should be fully functional and testable independently.

---

## Phase 4: User Story 2 - HITL Approval Gate for High-Impact Actions (Priority: P1)

**Goal**: High-impact actions pause execution for mandatory human confirmation.

**Independent Test**: Trigger a high-impact action (e.g., strike) and verify execution halts until explicit API approval.

### Implementation for User Story 2

- [x] T015 [P] [US2] Create HITL Decision model in `src/uservice/hitl/models/decision.py`
- [x] T016 [US2] Implement HITL Temporal Signal handling in the SMEAC processing workflow (`src/uservice/smeac/operations/process.py`)
- [x] T017 [US2] Implement HITL facade in `src/uservice/hitl/facade/approval.py`
- [x] T018 [US2] Implement HITL approval/rejection API endpoints in `src/uservice/hitl/api/routes.py`

**Checkpoint**: User Stories 1 AND 2 should both work independently.

---

## Phase 5: User Story 3 - MCP Auth Gateway Enforces Agent Identity (Priority: P2)

**Goal**: Gateway validates agent OAuth 2.1 tokens and enforces scope-based access to tools.

**Independent Test**: Access API with valid/invalid tokens and verify 403 Forbidden for bad scopes.

### Implementation for User Story 3

- [x] T019 [P] [US3] Implement JWT decoding and validation scheme in `src/uservice/security/jwt.py`
- [x] T020 [US3] Implement MCP Auth Gateway middleware in `src/uservice/security/middleware.py`
- [x] T020a [US3] Implement JIT credential issuance and lifecycle management API in `src/uservice/security/jit.py`
- [x] T021 [US3] Add scope requirement enforcement to SMEAC and HITL endpoints

---

## Phase 6: User Story 4 - Safety Verification Before Swarm Execution (Priority: P2)

**Goal**: Constraint solvers validate commands against safety rules before execution.

**Independent Test**: Commands violating altitude limits are rejected with constraint error details.

### Implementation for User Story 4

- [x] T022 [P] [US4] Create Constraint Violation model in `src/uservice/smeac/models/violation.py`
- [x] T023 [US4] Implement Guardian Critic agent for safety checks in `src/uservice/swarm/operations/swarm_agents.py`
- [x] T024 [US4] Integrate Guardian Critic into the SMEAC Temporal workflow (`src/uservice/smeac/operations/process.py`)

---

## Phase 7: User Story 6 - Commander Provisions a New Swarm Instance (Priority: P2)

**Goal**: Dynamically provision dedicated container instances for specific swarms.

**Independent Test**: Calling Provisioning API spawns a new Swarm Instance.

### Implementation for User Story 6

- [x] T025 [P] [US6] Create Swarm Instance model in `src/uservice/swarm/models/instance.py`
- [x] T026 [US6] Implement Docker container provisioning logic using Docker SDK in `src/uservice/swarm/operations/create.py`
- [x] T027 [US6] Implement Swarm draining/termination logic in `src/uservice/swarm/operations/delete.py`
- [x] T027a [US6] Implement dynamic routing registration of new Swarms with the MCP Auth Gateway
- [x] T028 [US6] Implement Central Provisioning API endpoints in `src/uservice/swarm/api/routes.py`

---

## Phase 8: User Story 7 - Autonomous Object Identification and Targeting (Priority: P2)

**Goal**: Edge execution on Raspberry Pi 5 using YOLO-E and OpenCV.

**Independent Test**: Command drone to find "vehicle", verify edge instance logs YOLO-E detection and approach.

### Implementation for User Story 7

- [x] T029 [P] [US7] Implement camera stream parsing logic with OpenCV in `src/edge/vision/camera.py`
- [x] T030 [US7] Implement YOLO-E inference pipeline for target classification in `src/edge/vision/inference.py`
- [x] T031 [US7] Implement autonomous flight navigation logic in `src/edge/navigation/flight_controller.py`
- [x] T032 [US7] Create edge communication API to receive commands from backend in `src/edge/api/server.py`

---

## Phase 9: User Story 5 - Commander Dashboard with Tactical Awareness (Priority: P3)

**Goal**: Web dashboard with SMEAC panel, tactical map, unit roster, and status history.

**Independent Test**: Load frontend, verify UI components render correctly.

### Implementation for User Story 5

- [x] T033 [P] [US5] Create Commander dashboard HTML layout (`src/dashboard/index.html`)
- [x] T034 [P] [US5] Implement CSS design system using tokens (`src/dashboard/css/style.css`)
- [x] T035 [US5] Implement Leaflet.js map integration in `src/dashboard/js/map.js`
- [x] T036 [US5] Implement HITL polling and interactive modal in `src/dashboard/js/hitl.js`
- [x] T036a [US5] Implement JWT auth indicator component in `src/dashboard/js/auth_indicator.js`
- [x] T037 [US5] Wire frontend forms to the API (SMEAC submission, unit roster polling) in `src/dashboard/js/api.js` and `src/dashboard/js/main.js`

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T038 [P] Wire Temporal workflow triggering into SMEAC routes (`src/uservice/smeac/api/routes.py`)
- [x] T039 [P] Implement system startup routine via `scripts/startup.sh`
- [x] T040 [P] Implement audit logging wrapper and attach to SMEAC state transitions (`src/uservice/operation/audit.py`)
- [x] T041 [P] Write comprehensive E2E tests simulating full SMEAC to Edge command pipeline
- [x] T041a [P] Write performance testing script to validate SC-001 (15s processing limit)
- [x] T041b [P] Write and execute field evaluation scripts for physical Raspberry Pi 5 to validate SC-008 and SC-009 (80% YOLO-E confidence and 5m autonomous navigation accuracy)
- [x] T042 [P] Validate fail-closed constraints on gateway unavailability (FR-009)

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phases 3-9)**: All depend on Foundational phase completion
  - Phase 3 (US1) should be implemented first as it provides the core SMEAC to command logic.
  - Phase 4 (US2) relies on workflow hooks inside Phase 3.
  - Phase 8 (US7) can be developed entirely in parallel with the backend phases.
- **Polish (Phase 10)**: Depends on user stories being complete.

## Parallel Opportunities

- Edge autonomy development (Phase 8) shares no code dependencies with backend features and can run parallel to Phases 3-7.
- Dashboard frontend development (Phase 9) can use mocked endpoints and proceed parallel to backend development.
- Setup tasks T004, T005 and Foundational tasks T007, T008, T009 can be run in parallel.

---

## Phase 11: Convergence

- [x] T043 Implement reverse proxy routing in Auth Gateway for dedicated Swarm instances per FR-016 (missing)
- [x] T044 Integrate HITL signal handling in ProcessSmeacWorkflow per FR-005 (partial)
- [x] T045 Integrate Guardian Critic activity into ProcessSmeacWorkflow per FR-007 (partial)
- [x] T046 Invoke AuditEvent creation across workflow state transitions per FR-006 (partial)
- [x] T047 Write comprehensive E2E tests simulating full SMEAC to Edge pipeline per T041 (missing)
- [x] T048 Write tests to validate fail-closed constraints on gateway unavailability per T042 (missing)
- [x] T049 Execute the `.agents/agents/uservice-arch-reviewer` agent to validate architecture alignment with the Constitution
