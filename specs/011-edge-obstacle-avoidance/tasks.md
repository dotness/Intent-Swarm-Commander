# Tasks: Edge-Autonomous Obstacle Detection and Avoidance

**Input**: Design documents from `/specs/011-edge-obstacle-avoidance/`
**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/edge-avoidance-contract.md`, `quickstart.md`

**Tests**: Included as explicitly requested by the feature specification (hermetic unit/contract tests + no-mock Playwright E2E test with `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., `US1`, `US2`, `US3`)
- Exact file paths are included in every task description.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify test media asset and environment readiness

- [X] T001 Verify real FPV test video exists and is readable at tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4
- [X] T002 [P] Verify `google-genai`, `ultralytics`, `opencv-python-headless`, `mavsdk`, and `paho-mqtt` are installed in pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core contracts and shared models required across all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Add `CorridorDetection` (with `detection_id`, `area_ratio`, `in_forward_corridor`) and corridor geometry helpers (`compute_corridor_occupancy`, `select_clearest_lateral_side`) in src/edge/vision/inference.py
- [X] T004 [P] Add `EdgeAvoidanceCommand` provenance schema and helper validation for `command_source == "edge_autonomous"` `alert` events in src/uservice/telemetry/models/contract/events.py
- [X] T005 [P] Verify `AuditEventType.COMMAND_EXECUTED` and `ActorType.AGENT` support `details.command_source == "edge_autonomous"` without breaking existing PostgreSQL enum schema in src/uservice/operation/audit.py

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Edge-Autonomous Obstacle Detection and Bypass (Priority: P1) 🎯 MVP

**Goal**: Enable the edge node to detect non-target obstacles in the forward flight corridor, autonomously compute and execute a dynamic lateral detour toward the clearest open side via MAVSDK, resume the original route once clear, and emit auditable edge-authored telemetry to both the stream and C2 audit view.

**Independent Test**: Run `pytest tests/unit/test_edge_obstacle_avoidance.py tests/contract/test_mqtt_contract.py -v` to verify corridor detection, `bypassing` -> `resuming` -> `searching` transitions, `obstructed_hold` fail-safe on blocked corridor/lost frames, and `edge_autonomous` MQTT + `AuditEvent` provenance.

### Tests for User Story 1

- [X] T006 [P] [US1] Add unit tests for corridor occupancy, clearest-side selection, `FlightController` bypass/resume/obstructed_hold state transitions, perception-loss hold, and <500 ms frame-to-command latency (`SC-004`) in tests/unit/test_edge_obstacle_avoidance.py
- [X] T007 [P] [US1] Add MQTT contract tests for `edge_autonomous` QoS 1 `alert` payload validation in tests/contract/test_mqtt_contract.py

### Implementation for User Story 1

- [X] T008 [US1] Update `YoloEInference.detect()` to support unfiltered multi-object corridor detection (`target_class=None`) in src/edge/vision/inference.py
- [X] T009 [US1] Add `publish_avoidance_alert()` (QoS 1 `alert` with `EdgeAvoidanceCommand` provenance in `extra`) in src/edge/telemetry/publisher.py
- [X] T010 [US1] Implement obstacle-avoidance state machine (`bypassing`, `resuming`, `obstructed_hold`), dynamic lateral MAVSDK `goto_location` detour, and route resumption in src/edge/navigation/flight_controller.py
- [X] T011 [US1] Expose `last_avoidance_command` in `GET /telemetry` and `obstacle_avoidance_enabled` in `POST /target` in src/edge/api/server.py
- [X] T012 [P] [US1] Persist `AuditEvent` (`AuditEventType.COMMAND_EXECUTED`, `ActorType.AGENT`, `actor_id="edge:{drone_id}"`, `details.action="obstacle_bypass"`) when `TelemetryIngestor` receives `edge_autonomous` alert events in src/uservice/telemetry/operations/ingestor.py
- [X] T013 [P] [US1] Expose edge avoidance provenance in swarm telemetry/audit responses in src/uservice/swarm/api/routes.py and render edge-autonomous bypass events in the C2 operator view in src/dashboard/js/main.js

**Checkpoint**: User Story 1 is independently functional and testable via unit/contract tests

---

## Phase 4: User Story 2 - Target vs. Obstacle Discrimination (Priority: P1)

**Goal**: Use the edge LLM to match detected object classes and attributes against the active mission order's target specification so ordered targets trigger `approaching` (zero bypasses) while non-target objects trigger obstacle bypass.

**Independent Test**: Run `pytest tests/unit/test_edge_obstacle_avoidance.py -k matcher -v` to verify LLM semantic target matching, TTL cache behavior, fail-safe `< 0.7` confidence classification as obstacle, and mixed target + obstacle routing.

### Tests for User Story 2

- [X] T014 [P] [US2] Add hermetic unit tests (with `google-genai` stubbed via `pytest` fixture per Constitution VI) for `EdgeTargetMatcher` (semantic match, mismatch, TTL cache hit, `< 0.7` fail-safe to obstacle, mixed target + obstacle frame) in tests/unit/test_edge_obstacle_avoidance.py

### Implementation for User Story 2

- [X] T015 [US2] Create `EdgeTargetMatcher` using unconditional `google-genai` structured output, `(mission_id, target_spec, detected_class)` TTL cache, and `< 0.7` fail-safe threshold in src/edge/vision/target_matcher.py
- [X] T016 [US2] Extend `TargetAssignment` and `POST /target` request model with optional `target_attributes` in src/edge/api/server.py
- [X] T017 [US2] Integrate `EdgeTargetMatcher` into `FlightController._navigation_loop()` so LLM-confirmed targets enter `approaching` while non-target corridor obstacles enter `bypassing` in src/edge/navigation/flight_controller.py

**Checkpoint**: User Story 2 is independently functional and preserves target-acquisition missions alongside obstacle avoidance

---

## Phase 5: User Story 3 - End-to-End Real-Media Verification and Telemetry Auditability (Priority: P2)

**Goal**: Prove end-to-end without mocks that streaming `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4` to a drone flying straight causes the edge system to detect the lamp post obstacle, autonomously order a lateral bypass, and record verifiable edge provenance in telemetry and the C2 audit view.

**Independent Test**: Run `npx playwright test tests/e2e/prod_obstacle_avoidance.spec.js` against the live Docker Compose stack (`virtual-cam`, `edge`, PX4 SITL, MQTT, `uservice`, PostgreSQL, dashboard).

### Implementation & E2E Verification for User Story 3

- [X] T018 [US3] Verify and configure `scripts/virtual_cam_server.py` video looping/streaming support for `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`
- [X] T019 [US3] Create no-mock Playwright E2E test verifying straight flight -> lamp post detection -> edge-ordered lateral bypass -> telemetry & C2 audit provenance (`command_source: "edge_autonomous"`) -> ordered target non-bypass in tests/e2e/prod_obstacle_avoidance.spec.js

**Checkpoint**: All 3 user stories are complete and verified end-to-end without mocks

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Constitution compliance, linting, and full validation pass

- [X] T020 [P] Verify Constitution VI & VII compliance across `src/edge/` and `src/uservice/` (zero mocks/stubs, zero `try/except ImportError`, zero `*_AVAILABLE` flags, zero fallback branches)
- [ ] T021 [P] Run `ruff check src/edge src/uservice tests/unit/test_edge_obstacle_avoidance.py tests/contract/test_mqtt_contract.py`
- [X] T022 Run quickstart validation commands from specs/011-edge-obstacle-avoidance/quickstart.md and confirm all checks pass
- [X] T023 [P] Run `uservice-arch-reviewer` agent review on implemented changes and document LTV Node Point alignment in specs/011-edge-obstacle-avoidance/plan.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 — **blocks** Phases 3, 4, and 5.
- **Phase 3 (US1 - Obstacle Bypass & Telemetry)**: Depends on Phase 2.
- **Phase 4 (US2 - LLM Target vs. Obstacle Discrimination)**: Depends on Phase 2 and integrates with `FlightController` from US1 (`T010`).
- **Phase 5 (US3 - No-Mock E2E Video Verification)**: Depends on US1 (`T008`–`T013`) and US2 (`T015`–`T017`).
- **Phase 6 (Polish)**: Depends on Phases 3, 4, and 5.

### Parallel Opportunities

- Within **Phase 2**: `T003`, `T004`, and `T005` touch separate files (`inference.py`, `events.py`, `audit.py`) and can run in parallel.
- Within **Phase 3 (US1)**: `T006` and `T007` (tests) can run in parallel; `T012` (`ingestor.py`) and `T013` (`routes.py`, `main.js`) can run in parallel with `T011` (`server.py`).
- Within **Phase 6**: `T020` and `T021` can run in parallel.

### Parallel Example: Phase 2 (Foundational)

```bash
# Run all foundational model/contract updates concurrently:
T003: src/edge/vision/inference.py
T004: src/uservice/telemetry/models/contract/events.py
T005: src/uservice/operation/audit.py
```

### Implementation Strategy

- **MVP First (User Story 1)**: Complete Phases 1–3 to deliver working edge corridor obstacle detection, dynamic lateral bypass, route resumption, and edge-authored telemetry/audit provenance.
- **Incremental Delivery**: Add Phase 4 (`EdgeTargetMatcher` LLM discrimination) to preserve ordered target approach, then Phase 5 (no-mock E2E video verification with `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`), and finish with Phase 6 compliance & lint checks.
