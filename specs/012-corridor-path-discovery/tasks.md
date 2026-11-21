# Tasks: Gradual Corridor Path Discovery and Adaptive Survey

**Input**: Design documents from `/specs/012-corridor-path-discovery/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/corridor-survey-contract.md`, `quickstart.md`

**Tests**: Included as explicitly required by `FR-017`, `SC-001`–`SC-007`, and `quickstart.md` (hermetic unit/contract/security tests + live zero-mock multi-shape corridor Playwright E2E test).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., `US1`, `US2`, `US3`, `US4`)
- Exact file paths are included in every task description.

## Path Conventions

- **Edge companion node**: `src/edge/`
- **Central C2 microservice (`uservice-template` DDD)**: `src/uservice/`
- **Operator web dashboard**: `src/dashboard/`
- **Simulation / E2E helper scripts**: `scripts/`
- **Automated tests**: `tests/unit/`, `tests/contract/`, `tests/e2e/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the new corridor domain package, confirm dependency availability, and extend shared SMEAC command definitions

- [X] T001 Scaffold DDD package structure (`api/`, `facade/`, `models/contract/`, `models/storage/`, `operations/`) with `__init__.py` modules under src/uservice/corridor/
- [X] T002 [P] Verify required dependencies (`opencv-python-headless`, `ultralytics`, `google-genai`, `mavsdk`, `paho-mqtt`, `aiomqtt`, `boto3`, `sqlalchemy[asyncio]`, `fastapi`, `pydantic-ai`, `temporalio`, Playwright) are present in pyproject.toml and package.json with zero new third-party packages added
- [X] T003 [P] Add `MissionType.CORRIDOR_SURVEY = "corridor_survey"` and nullable `survey_params` text column on `SwarmCommand` in src/uservice/smeac/models/contract/command.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core schemas, ORM persistence tables, MQTT provenance contracts, proxy pass-through, and MinIO/EdgeSpool snapshot upload pipeline required across all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Define Pydantic v2 schemas (`CorridorSurveyParams`, `PathBreadcrumb3D`, `CorridorSnapshotSummary`, `CorridorDecisionItem`, `CorridorFindingItem`, `CorridorIntelligenceReport`, `CorridorSurveyListItem`, `CorridorOverrideResponse`) with strict validation (`target_distance_m > 0`, `0.5 <= min_altitude_m < max_altitude_m <= 120.0`, UUID/slug rules) in src/uservice/corridor/models/contract/schemas.py
- [X] T005 [P] Define SQLAlchemy ORM models (`CorridorSurvey`, `CorridorSnapshot`, `CorridorTrajectoryDecision`, `CorridorFinding`) with foreign keys and indexes in src/uservice/corridor/models/storage/survey.py
- [X] T006 Register `src.uservice.corridor.models.storage.survey` models and add idempotent `ALTER TABLE swarm_commands ADD COLUMN IF NOT EXISTS survey_params TEXT` migration in src/uservice/database/engine.py (depends on T003, T005)
- [X] T007 [P] Add corridor survey MQTT provenance payloads (`CorridorSurveyEventType`, `CorridorSnapshotPayload`, `CorridorTrajectoryPayload`, `CorridorPhasePayload`, `CorridorReportPayload`, `CorridorOverridePayload`), canonical `survey_<phase>` / `survey_staging_hold` flight-status helper, and `is_corridor_survey_event()` helper while keeping Feature 011 `is_edge_autonomous_alert()` untouched in src/uservice/telemetry/models/contract/events.py
- [X] T008 [P] Register `"/corridor-surveys"` direct pass-through routing exemption in src/uservice/security/proxy.py
- [X] T009 Implement `publish_corridor_snapshot()` (JPEG magic-byte `\xff\xd8\xff` and `<= 5 MB` check, UUID key upload to MinIO `tactical-snapshots`, `EdgeSpool` DDIL fallback) and `publish_corridor_event()` (QoS 1 `alert` events with `command_source="edge_corridor_survey"`) in src/edge/telemetry/publisher.py (depends on T007)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Coordinate-Free Survey Order & Initial Look-Around Discovery (Priority: P1) 🎯 MVP

**Goal**: Accept coordinate-free SMEAC spatial survey orders (e.g., *"go check the corridor next 20 meters and go back"*), validate distance/altitude bounds, assign a single lead scout drone while holding remaining swarm drones at staging, perform a mandatory 8-heading 360° yaw look-around sweep while hovering at origin, hold until edge analysis finishes, and begin flight only on an edge-validated opening (or hold safely on impassable start).

**Independent Test**: Run `pytest tests/unit/test_corridor_smeac_and_api.py tests/unit/test_corridor_analyzer.py tests/unit/test_corridor_survey_controller.py -k "us1 or look_around or smeac_intake" -v` to verify coordinate-free SMEAC intake (`RelativeCorridor`, `<= 0` rejection, `20.0 m` default, lead scout assignment), 8-heading 360° sweep while stationary at origin, zero forward movement before edge clearance, and `impassable_start` hold when enclosed.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Write hermetic unit tests for coordinate-free SMEAC intake (`RelativeCorridor`), `<= 0` distance HTTP `422` rejection, omitted-distance `20.0 m` default, arbitrary positive distance acceptance, omitted `altitude_m` defaulting to `clamp(2.5, min_altitude_m, max_altitude_m)` vs. explicit out-of-envelope `altitude_m` `422` rejection (`FR-021`), and multi-drone lead scout + staging hold assignment (`FR-001`, `FR-019`) in tests/unit/test_corridor_smeac_and_api.py
- [X] T011 [P] [US1] Write hermetic unit tests for `CorridorVisualAnalyzer` frame quality checks (blur, darkness, frozen frame) and open passage vs. enclosed-start wall detection in tests/unit/test_corridor_analyzer.py
- [X] T012 [P] [US1] Write hermetic unit tests for `CorridorSurveyController` initial 8-heading 360° yaw sweep while holding at `entry_altitude_m` at origin, zero forward advance before edge validation (`SC-002`), initial trajectory emission, canonical `survey_<phase>` telemetry emission, and `impassable_start` hold in tests/unit/test_corridor_survey_controller.py

### Implementation for User Story 1

- [X] T013 [P] [US1] Extend `GeoJsonTargetArea` (support `RelativeCorridor` with empty coordinates), `SwarmCommandDTO` (`survey_params: CorridorSurveyParams | None`), and `SMEAC_SYSTEM_PROMPT` for coordinate-free corridor orders in src/uservice/smeac/operations/smeac_agents.py
- [X] T014 [P] [US1] Extend `SwarmCommandResponse` with optional `survey_id`, `lead_scout_drone_id`, `staging_hold_drone_ids`, and `survey_params` in src/uservice/smeac/models/contract/schemas.py
- [X] T015 [US1] Update `SmeacFacade.submit_smeac_order()` and `get_order_status()` to validate `CorridorSurveyParams` (`422` on `target_distance_m <= 0`, `min_altitude_m >= max_altitude_m`, or explicit `altitude_m` outside `[min_altitude_m, max_altitude_m]`; default omitted distance to `20.0 m`, `return_to_origin=True`, and omitted `altitude_m` to `clamp(2.5, min_altitude_m, max_altitude_m)` per `FR-021`), assign `drone-1` as lead scout + staging-hold remaining swarm drones (`FR-019`), skip empty-coordinate geo threat intersection, and persist initial `CorridorSurvey` row in src/uservice/smeac/facade/smeac.py (depends on T013, T014)
- [X] T016 [US1] Update `parse_smeac_activity()` (when DB-reloading on empty `input.commands` during Temporal replay/retry, hydrate `survey_params` from `SwarmCommand` plus `survey_id`, `lead_scout_drone_id`, and `staging_hold_drone_ids` from `CorridorSurvey` by `command_id`/`smeac_order_id`) and `dispatch_edge_mission_activity()` to dispatch `corridor_survey` commands with `entry_altitude_m` and `staging_hold_drone_ids` to edge `POST /corridor-survey/start` in src/uservice/smeac/operations/process.py (depends on T015)
- [X] T017 [P] [US1] Create `CorridorVisualAnalyzer` core (`CorridorFrameAnalysis`, `CorridorBranchCandidate`, blur/brightness/freeze visual quality gate, and 5×3 OpenCV spatial-grid opening/clearance estimation with unconditional imports) in src/edge/vision/corridor_analyzer.py
- [X] T018 [US1] Implement `CorridorSurveyController` initialization, origin 3D ENU frame anchor, takeoff/hold at `entry_altitude_m`, 8-heading 360° initial yaw sweep persisting all 8 panoramic snapshots, canonical `f"survey_{phase}"` flight status emissions, best-opening ranking, initial `EdgeTrajectoryInstruction` emission, and `impassable_start` safe hold in src/edge/navigation/corridor_survey.py (depends on T009, T017)
- [X] T019 [US1] Expose `POST /corridor-survey/start` (actively stopping/cancelling pre-existing vision or navigation tasks for `staging_hold_drone_ids`, holding them safely at staging, and publishing `flight_status = "survey_staging_hold"` telemetry while launching `CorridorSurveyController` exclusively on `drone_id`), `GET /corridor-survey/{survey_id}/status`, and `active_corridor_survey` projection in `GET /telemetry` in src/edge/api/server.py (depends on T018)

**Checkpoint**: User Story 1 is independently functional and testable — coordinate-free survey orders assign a lead scout, execute the 360° initial look-around sweep, hold until edge clearance, and either depart safely or hold on impassable start.

---

## Phase 4: User Story 2 - Iterative In-Flight Snapshot Analysis and Adaptive 3D Trajectory Discovery (Priority: P1)

**Goal**: Perform continuous rolling 3D flight along authorized corridor segments while periodically capturing snapshots, analyzing each frame within `<=500 ms` to adapt to straight, curved, L-turn, S-bend, forked, narrowing/widening, and elevation-varying passages within configurable `[min_altitude_m, max_altitude_m]` bounds, enforcing `boundary_hold` / `turn_look_around` + `5.0 s` guidance-outage failsafe return, autonomously choosing primary fork continuations, and logging mission-interest objects without HITL blocking.

**Independent Test**: Run `pytest tests/unit/test_corridor_analyzer.py tests/unit/test_corridor_survey_controller.py -k "us2 or adaptive or overhang or fork or timeout" -v` to verify `<500 ms` frame-to-instruction latency (`SC-007`), L-turn/S-bend/overhang steering, `FR-021` altitude clamping/refusal, `5.0 s` boundary-hold failsafe return (`SC-004`), degraded-visual pause/recapture fail-safe (`FR-015`), autonomous fork continuation (`FR-011`), and non-blocking target/hazard findings (`FR-016`).

### Tests for User Story 2

- [X] T020 [P] [US2] Add unit tests for `CorridorVisualAnalyzer` curve/L-turn/S-bend steering, low-overhang/slope vertical elevation adjustment, multi-peak fork/intersection branch detection, YOLO-World + `EdgeTargetMatcher` interior hazard vs. mission-interest classification, and `<=500 ms` latency budget (`SC-007`) in tests/unit/test_corridor_analyzer.py
- [X] T021 [P] [US2] Add unit tests for `CorridorSurveyController` continuous rolling 3D flight, periodic snapshot capture, 3D cumulative path distance (`sqrt(dx^2+dy^2+dz^2)`), `[min_altitude_m, max_altitude_m]` clamping/refusal (`FR-021`), `boundary_hold` and `turn_look_around`, `5.0 s` guidance timeout failsafe (`SC-004`, `SC-007`), degraded-visual pause/recapture fail-safe (`FR-015`), autonomous primary-branch selection (`FR-011`), and non-blocking mid-corridor findings (`FR-016`) in tests/unit/test_corridor_survey_controller.py

### Implementation for User Story 2

- [X] T022 [US2] Extend `CorridorVisualAnalyzer` with 3D low-overhang/slope vertical clearance estimation, multi-peak fork/T-junction branch detection (`secondary_branches`), structural tagging (`curve_*`, `turn_*`, `narrowing`, `widening`, `low_overhang`, `slope_*`, `intersection`, `dead_end`), and `YoloEInference` + cached `EdgeTargetMatcher` integration in src/edge/vision/corridor_analyzer.py (depends on T017)
- [X] T023 [US2] Implement `outbound_discovery` continuous 3D rolling flight loop, periodic full-snapshot persistence, 3D `PathBreadcrumb3D` recording, cumulative 3D path length tracking, `[min_altitude_m, max_altitude_m]` vertical bounds enforcement (`FR-021`), autonomous branch selection + side-branch logging (`FR-011`), and non-blocking mission-interest/hazard finding emission (`FR-016`) in src/edge/navigation/corridor_survey.py (depends on T018, T022)
- [X] T024 [US2] Implement `boundary_hold`, `turn_look_around`, degraded-visual pause/recapture fail-safe (`FR-015`), and `5.0 s` cleared-segment guidance-outage failsafe timer (`SC-004`, `SC-007`) in src/edge/navigation/corridor_survey.py (depends on T023)
- [X] T025 [P] [US2] Update `_handle_detection` in src/uservice/main.py so `survey_*` flight statuses never trigger blocking mid-corridor HITL modals while preserving target correlation (`FR-016`)

**Checkpoint**: User Stories 1 AND 2 work together end-to-end at the edge — the drone safely discovers non-straight, 3D elevation-varying, and branching corridors while persisting every snapshot and obeying all latency and safety bounds.

---

## Phase 5: User Story 3 - Distance Completion, Autonomous Return-to-Origin ("Go Back") & Operator Overrides (Priority: P2)

**Goal**: Terminate outbound discovery accurately upon reaching the ordered 3D distance, confirming a dead end/blockage, or reaching the dynamic battery safe-return reserve (without any fixed upper distance cap), retrace the verified 3D corridor path in reverse back to origin while monitoring return snapshots for dynamic obstacles, and support two-tier operator `Recall` (reverse return + partial report) vs. `Emergency Abort` (immediate in-place hold).

**Independent Test**: Run `pytest tests/unit/test_corridor_survey_controller.py -k "us3 or return or dead_end or endurance or recall or abort" -v` to verify `20 m` completion, `12 m` dead-end early termination, battery reserve auto-return on long-distance orders, reverse 3D breadcrumb retracing (`SC-005`), return-leg obstacle bypass vs. `return_blocked_hold` (`FR-010`), and two-tier `recall` vs. `emergency_abort` (`FR-018`).

### Tests for User Story 3

- [X] T026 [P] [US3] Add unit tests covering target-distance termination (`20 m`), dead-end early termination (`12 m`), dynamic battery safe-return endurance reserve on unbounded positive distance (`FR-009`, `FR-021`), `return_to_origin=False` far-end hold, reverse 3D breadcrumb retracing (`SC-005`), dynamic return-leg obstacle bypass vs. `return_blocked_hold` (`FR-010`), and two-tier `recall()` vs. `emergency_abort()` (`FR-018`) in tests/unit/test_corridor_survey_controller.py

### Implementation for User Story 3

- [X] T027 [US3] Implement outbound termination triggers (`distance_reached`, `dead_end`, dynamic battery `endurance_reserve`, `far_end_hold`) and reverse 3D breadcrumb retracing (`returning`, `return_blocked_hold`, `completed`, `completed_holding`) with return-leg snapshot monitoring and obstacle adaptation in src/edge/navigation/corridor_survey.py (depends on T024)
- [X] T028 [US3] Implement `recall()` (immediate transition to reverse-path `returning` + partial report) and `emergency_abort()` (immediate MAVSDK `action.hold()` → `emergency_hold` + preserved intelligence) in src/edge/navigation/corridor_survey.py (depends on T027)
- [X] T029 [US3] Expose `POST /corridor-survey/{survey_id}/recall` and `POST /corridor-survey/{survey_id}/emergency-abort` endpoints in src/edge/api/server.py (depends on T019, T028)
- [X] T030 [P] [US3] Implement `recall_survey()` and `emergency_abort_survey()` in src/uservice/corridor/facade/corridor.py enforcing `smeac:create` RBAC and swarm ownership, forwarding overrides to edge, and writing `AuditEvent(actor_type=ActorType.COMMANDER)`

**Checkpoint**: User Story 3 is complete — surveys terminate cleanly on distance, dead end, endurance reserve, or operator recall/abort and safely retrace verified 3D corridor paths back to origin.

---

## Phase 6: User Story 4 - Corridor Intelligence Capture, Reconstruction, Reporting & Dashboard Visualization (Priority: P2)

**Goal**: Ingest QoS 1 corridor telemetry and full snapshot metadata into PostgreSQL (`corridor_surveys`, `corridor_snapshots`, `corridor_trajectory_decisions`, `corridor_findings`) and immutable `AuditEvent` logs, serve the `CorridorIntelligenceReport` (`<=5 s`) and authenticated BFF snapshot image proxy via `src/uservice/corridor/`, render live dual-projection 3D SVG views + full snapshot replay filmstrip + `<dialog>`-confirmed Recall/Emergency Abort buttons in `src/dashboard/`, and prove the entire production pipeline end-to-end without mocks across multi-shape corridors (`FR-017`).

**Independent Test**: Run `pytest tests/contract/test_corridor_mqtt_contract.py tests/unit/test_corridor_smeac_and_api.py -v` for MQTT provenance, report assembly, RBAC/IDOR security, and snapshot BFF proxy behavior; then run `npx playwright test tests/e2e/prod_corridor_survey.spec.js` against the live Docker Compose stack (`virtual_cam`, `edge_drone`, PX4 SITL, Mosquitto, MinIO, PostgreSQL, `backend`, `dashboard`) to verify multi-shape corridor navigation, reverse return, full snapshot replay, and `CorridorIntelligenceReport` UI rendering.

### Tests for User Story 4

- [X] T031 [P] [US4] Write MQTT contract tests validating `corridor_snapshot`, `corridor_trajectory`, `corridor_phase`, `corridor_report`, and `corridor_override` QoS 1 envelopes and Feature 011 backward compatibility in tests/contract/test_corridor_mqtt_contract.py
- [X] T032 [P] [US4] Add hermetic API, persistence, and security tests (incremental report materialization `<5 s`, full snapshot storage count, JWT `401`/`403` RBAC, cross-swarm IDOR `404`, path-traversal key rejection, JPEG magic-byte/size enforcement, Recall/Emergency Abort `AuditEvent` provenance) in tests/unit/test_corridor_smeac_and_api.py

### Implementation for User Story 4

- [X] T033 [US4] Implement incremental atomic ingestion (`ingest_corridor_event`) and `CorridorIntelligenceReport` assembly (`assemble_corridor_report`, `get_snapshot_storage_uri`) in src/uservice/corridor/operations/survey_service.py (depends on T004, T005, T007)
- [X] T034 [US4] Complete `CorridorFacade` (`list_surveys`, `get_survey_report`, `get_snapshot_image` with strict swarm/project ownership and MinIO bucket/key validation) in src/uservice/corridor/facade/corridor.py (depends on T030, T033)
- [X] T035 [US4] Implement FastAPI routes (`GET /swarms/{swarm_id}/corridor-surveys`, `GET /swarms/{swarm_id}/corridor-surveys/{survey_id}`, `GET /swarms/{swarm_id}/corridor-surveys/{survey_id}/snapshots/{snapshot_id}/image` BFF proxy with `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`, `POST .../recall`, `POST .../emergency-abort`) in src/uservice/corridor/api/routes.py (depends on T034)
- [X] T036 [US4] Extend `TelemetryIngestor` to invoke `corridor_survey_callback` and persist `AuditEvent` records (`ActorType.AGENT`/`COMMANDER`) for corridor trajectory, phase, and override events in src/uservice/telemetry/operations/ingestor.py (depends on T007)
- [X] T037 [US4] Mount `corridor_router` under `/api/v1` and wire `corridor_survey_callback` into `TelemetryIngestor` inside `lifespan()` in src/uservice/main.py (depends on T025, T035, T036)
- [X] T038 [P] [US4] Add `fetchCorridorSurveys`, `fetchCorridorSurveyReport`, `recallCorridorSurvey`, and `emergencyAbortCorridorSurvey` client methods in src/dashboard/js/api.js
- [X] T039 [P] [US4] Add `#corridor-survey-panel` (phase/distance/lead-scout banner, Top-Down Plan and Elevation Profile SVG containers, Recall and Emergency Abort buttons, full snapshot replay filmstrip, findings/branches/decision audit list) and `<dialog id="corridor-abort-modal">` in src/dashboard/index.html and styles in src/dashboard/css/style.css
- [X] T040 [US4] Implement XSS-safe `CorridorController` (`document.createElementNS` dual-projection SVG renderer, authenticated `fetchSnapshotBlobUrl` filmstrip with `URL.revokeObjectURL` cleanup, in-page `<dialog>` confirmation modal, zero `innerHTML`/`confirm()`/`alert()`) in src/dashboard/js/corridor.js (depends on T038, T039)
- [X] T041 [US4] Initialize `CorridorController` and hook active survey polling on swarm selection and order submission in src/dashboard/js/main.js (depends on T040)
- [X] T042 [P] [US4] Extend scripts/virtual_cam_server.py with pose-aware 3D perspective `corridor_scene` renderer (`straight_20m`, `l_turn_20m`, `s_bend_overhang_20m`, `dead_end_12m`, `branch_junction_20m`, `enclosed_start`) driven automatically via Mosquitto MQTT telemetry pose subscription (`telemetry/projects/+/swarms/+/+/navigation` & `alert`) plus optional `POST /pose/{drone_id}` test override, and configure `MQTT_BROKER_HOST`/`MQTT_BROKER_PORT` + `depends_on: [mosquitto]` on `virtual_cam` in docker-compose.yml
- [X] T043 [US4] Create zero-mock Playwright E2E test suite verifying coordinate-free SMEAC order → lead scout assignment → 360° look-around hold → multi-shape 3D discovery (L-turn, S-bend + overhang, dead-end 12 m) → reverse-path return → Recall/Emergency Abort overrides → full MinIO snapshot replay and live dashboard 3D SVG + Corridor Intelligence Report (`<=5 s`) in tests/e2e/prod_corridor_survey.spec.js (depends on T019, T029, T037, T041, T042)

**Checkpoint**: All 4 user stories are complete — full live C2 intelligence materialization, dual-projection 3D SVG dashboard visualization, full snapshot replay, and zero-mock multi-shape E2E verification are operational.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Constitution VI/VII purity checks, security verification, linting, architecture review, and full quickstart validation

- [X] T044 [P] Verify Constitution VI & VII compliance across src/edge/ and src/uservice/ (zero mocks, zero `try/except ImportError`, zero `*_AVAILABLE` flags) and XSS-safe DOM compliance in src/dashboard/js/corridor.js (zero `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`confirm()`/`alert()`)
- [X] T045 [P] Run `ruff check src/edge src/uservice tests/unit/test_corridor_analyzer.py tests/unit/test_corridor_survey_controller.py tests/unit/test_corridor_smeac_and_api.py tests/contract/test_corridor_mqtt_contract.py` and resolve any lint warnings
- [X] T046 Execute all validation scenarios from specs/012-corridor-path-discovery/quickstart.md (hermetic unit/contract/security suites + live multi-shape E2E test) and confirm all pass (depends on T043, T044, T045)
- [X] T047 [P] Run `.agents/agents/uservice-arch-reviewer` review against src/uservice/corridor/, src/uservice/smeac/, and src/edge/, address any architecture findings, and record review notes in specs/012-corridor-path-discovery/plan.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately (`T001`–`T003`).
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — **blocks** all user stories (`T004`–`T009`).
- **Phase 3 (User Story 1 — P1 MVP)**: Depends on Phase 2 (`T010`–`T019`).
- **Phase 4 (User Story 2 — P1)**: Depends on Phase 2 and extends US1 perception/navigation modules (`T017`, `T018`) (`T020`–`T025`).
- **Phase 5 (User Story 3 — P2)**: Depends on Phase 4 navigation loop (`T024`) and Phase 3 edge API (`T019`) (`T026`–`T030`).
- **Phase 6 (User Story 4 — P2)**: Backend DDD (`T033`–`T037`), dashboard (`T038`–`T041`), and virtual cam (`T042`) can start immediately after Phase 2 + `T025`/`T030`; zero-mock E2E (`T043`) integrates all user stories (`T019`, `T029`, `T037`, `T041`, `T042`).
- **Phase 7 (Polish)**: Depends on completion of desired user stories (`T044`–`T047`).

### User Story Dependencies

- **US1 (P1)**: Independent entry point after Foundational (`Phase 2`).
- **US2 (P1)**: Builds on US1 `CorridorVisualAnalyzer` (`T017`) and `CorridorSurveyController` (`T018`).
- **US3 (P2)**: Builds on US2 outbound discovery/boundary hold (`T024`) and US1 edge server (`T019`).
- **US4 (P2)**: Telemetry ingestion, C2 API, dashboard SVG visualization, and `virtual_cam` scene rendering depend only on Foundational (`Phase 2`) + override facade (`T030`), converging in final E2E (`T043`).

### Within Each User Story

- Tests (`T010`–`T012`, `T020`–`T021`, `T026`, `T031`–`T032`) are written first and verified failing before implementation.
- Models/contracts before operations/facades.
- Edge perception (`corridor_analyzer.py`) before flight control (`corridor_survey.py`) before HTTP API (`server.py`).
- Backend DDD storage/operations before facade before FastAPI router before `main.py` wiring.
- Dashboard API client + HTML/CSS markup before `corridor.js` controller before `main.js` integration.

### Parallel Opportunities

- **Phase 1**: `T002` and `T003` run in parallel once `T001` initializes `src/uservice/corridor/`.
- **Phase 2**: `T004`, `T005`, `T007`, and `T008` touch distinct files and run in parallel.
- **Phase 3 (US1)**: `T010`, `T011`, `T012`, `T013`, `T014`, and `T017` all run in parallel.
- **Phase 4 (US2)**: `T020`, `T021`, and `T025` run in parallel.
- **Phase 5 (US3)**: `T026` and `T030` run in parallel with edge override plumbing.
- **Phase 6 (US4)**: `T031`, `T032`, `T038`, `T039`, and `T042` run in parallel while `T033`→`T037` executes backend ingestion/API wiring.
- **Phase 7 (Polish)**: `T044`, `T045`, and `T047` run in parallel prior to final `T046` full quickstart run.

---

## Parallel Examples

### Parallel Example: Phase 2 (Foundational)

```bash
# Run all independent schema, ORM, MQTT contract, and proxy tasks concurrently:
T004: src/uservice/corridor/models/contract/schemas.py
T005: src/uservice/corridor/models/storage/survey.py
T007: src/uservice/telemetry/models/contract/events.py
T008: src/uservice/security/proxy.py
```

### Parallel Example: Phase 3 (User Story 1)

```bash
# Write all US1 tests and independent modules concurrently:
T010: tests/unit/test_corridor_smeac_and_api.py
T011: tests/unit/test_corridor_analyzer.py
T012: tests/unit/test_corridor_survey_controller.py
T013: src/uservice/smeac/operations/smeac_agents.py
T014: src/uservice/smeac/models/contract/schemas.py
T017: src/edge/vision/corridor_analyzer.py
```

### Parallel Example: Phase 6 (User Story 4)

```bash
# Run US4 tests, dashboard markup/API client, and virtual_cam 3D renderer concurrently:
T031: tests/contract/test_corridor_mqtt_contract.py
T032: tests/unit/test_corridor_smeac_and_api.py
T038: src/dashboard/js/api.js
T039: src/dashboard/index.html & src/dashboard/css/style.css
T042: scripts/virtual_cam_server.py
```

---

## Implementation Strategy

### MVP First (Phases 1–3: Setup + Foundational + User Story 1)

1. Complete **Phase 1 (Setup)** (`T001`–`T003`) and **Phase 2 (Foundational)** (`T004`–`T009`).
2. Complete **Phase 3 (User Story 1)** (`T010`–`T019`).
3. **STOP and VALIDATE**: Run US1 unit tests to confirm coordinate-free SMEAC parsing, lead scout assignment, 360° initial sweep while hovering at origin, edge validation gate before departure, and safe `impassable_start` holding.

### Incremental Delivery

1. **Foundation (`Phase 1–2`)** → shared schemas, ORM tables, MQTT envelopes, and MinIO/EdgeSpool snapshot upload ready.
2. **US1 (`Phase 3`)** → MVP coordinate-free intake + 360° initial look-around validation.
3. **US2 (`Phase 4`)** → sub-500 ms adaptive 3D rolling navigation across turns, S-bends, overhangs, forks, and 5 s failsafe boundary holds.
4. **US3 (`Phase 5`)** → distance/dead-end/endurance termination, reverse 3D breadcrumb retracing, and two-tier Recall vs. Emergency Abort overrides.
5. **US4 (`Phase 6`)** → C2 persistence, `<5 s` Corridor Intelligence Report API, XSS-safe dual-projection 3D SVG dashboard + full snapshot replay, and zero-mock multi-shape Playwright E2E.
6. **Polish (`Phase 7`)** → Constitution VI/VII audit, security verification, `ruff`, `uservice-arch-reviewer` review, and full quickstart validation.

### Parallel Team Strategy

Once **Phase 2 (Foundational)** is complete:
- **Edge Autonomy Engineer**: Executes `T011`–`T012`, `T017`–`T024`, `T026`–`T029` across `src/edge/`.
- **Backend / C2 Engineer**: Executes `T010`, `T013`–`T016`, `T025`, `T030`–`T037` across `src/uservice/`.
- **Dashboard & E2E Engineer**: Executes `T038`–`T043` across `src/dashboard/`, `scripts/virtual_cam_server.py`, and `tests/e2e/prod_corridor_survey.spec.js`.

---

## Notes

- `[P]` tasks operate on separate files with no unfinished blocking dependencies.
- Every task includes its exact target file path and story tag (`[US1]`–`[US4]`) where applicable.
- Adhere strictly to Constitution VI (zero mocks in `src/`), Constitution VII (unconditional imports, zero `*_AVAILABLE` flags or fallback branches), and `mandatory-secure-web-skills` (zero `innerHTML`/`confirm()`/`alert()`, strict RBAC + IDOR enforcement, JPEG magic-byte/size checks).
- Every captured visual snapshot is persisted without pruning (`FR-020`); TTL expiration and cleanup remain explicitly out of scope.
