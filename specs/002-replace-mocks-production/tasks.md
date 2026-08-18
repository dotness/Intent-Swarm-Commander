# Tasks: Replace Mocks, Stubs & Hardcodes

**Input**: Design documents from `specs/002-replace-mocks-production/`

**Prerequisites**: plan.md (✅), spec.md (✅), research.md (✅), data-model.md (✅), contracts/ (✅), quickstart.md (✅)

**Tests**: Not explicitly requested in the spec — test tasks omitted. Run existing `tests/integration/` suite for validation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New dependencies and base-level helpers needed before any mock replacement begins.

- [X] T001 Add `docker` (Docker SDK) and `shapely` (geofencing) to project dependencies in pyproject.toml
- [X] T002 Add `require_scope()` helper method to `DomainFacade` in src/uservice/base/facade/base.py that validates JWT scopes via `self.user` claims using the existing `verify_scope()` from src/uservice/security/jwt.py
- [X] T003 Add missing fields (`action_summary`, `timeout_seconds`, `status`, `workflow_id`) to `HitlDecision` ORM model in src/uservice/hitl/models/storage/decision.py per data-model.md (workflow_id is needed for T024 to signal the correct Temporal workflow)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Auth login endpoint and dashboard auth module — MUST be complete before user stories because every API call depends on real tokens.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create auth login endpoint `POST /api/v1/auth/login` in a new file src/uservice/security/routes.py — accepts `commander_id` + `passphrase` (validated against `COMMANDER_PASSPHRASE` env var for MVP), calls existing `issue_jit_credential()` from src/uservice/security/jit.py, returns JWT token
- [X] T005 Register the auth router in src/uservice/main.py under `/api/v1`
- [X] T006 Create a new `auth.js` module in src/dashboard/js/auth.js — implements login form submission, stores token in `sessionStorage`, exposes `getAuthHeader()` that returns `{ 'Authorization': 'Bearer ' + token }`, handles 401 by clearing session and prompting re-login
- [X] T007 Add `<script src="js/auth.js">` to src/dashboard/index.html and add a login overlay/modal for initial authentication
- [X] T008a [P] Enforce real hardware in src/edge/navigation/flight_controller.py — check `SIMULATION_MODE` env var; if not `true` and hardware is unavailable, raise `RuntimeError` instead of silent fallback
- [X] T008b [P] Enforce real hardware in src/edge/vision/camera.py — when `SIMULATION_MODE` is not `true` and camera hardware is absent, raise `RuntimeError` in `read_frame()` to satisfy FR-014
- [X] T008c [P] Enforce real hardware in src/edge/vision/inference.py — when `SIMULATION_MODE` is not `true` and model is absent, raise `RuntimeError` in `detect()` to satisfy FR-015

**Checkpoint**: Auth login works end-to-end. Dashboard can obtain a real token. Edge modules fail loudly without hardware unless `SIMULATION_MODE=true`.

---

## Phase 3: User Story 1 — Authenticated Dashboard Operations (Priority: P1) 🎯 MVP

**Goal**: Remove all hardcoded tokens and mock auth state from the dashboard. All API calls use real JWT tokens.

**Independent Test**: Log into dashboard with credentials, verify a real token is issued, confirm that API calls fail with 401 when the token is missing or expired. Run `grep -r "placeholder-token" src/` and confirm zero results.

### Implementation for User Story 1

- [X] T009 [US1] Replace hardcoded `AUTH_HEADER` in src/dashboard/js/api.js — remove `const AUTH_HEADER = { 'Authorization': 'Bearer placeholder-token' }` and replace all usages with `window.AuthModule.getAuthHeader()` from the auth.js module created in T006
- [X] T010 [US1] Replace hardcoded token in src/dashboard/js/hitl.js — change line 77 `'Authorization': 'Bearer placeholder-token'` to use `window.AuthModule.getAuthHeader()` spread
- [X] T011 [US1] Replace mock authentication in src/dashboard/js/auth_indicator.js — remove `isAuthenticated = true` and `commanderId = "commander-default"`, instead read auth state from `window.AuthModule.isAuthenticated()` and `window.AuthModule.getCommanderId()`
- [X] T012 [US1] Wire 401 handling into all `fetch()` calls in src/dashboard/js/api.js — on 401 response, call `window.AuthModule.handleUnauthorized()` to clear session and show login prompt

**Checkpoint**: Dashboard authenticates with real tokens. No hardcoded `placeholder-token` values remain in src/dashboard/.

---

## Phase 4: User Story 2 — Persistent Backend State (Priority: P1)

**Goal**: Replace all in-memory dictionaries with database persistence using existing ORM models. State survives restarts.

**Independent Test**: Create a swarm, submit a SMEAC order, create a HITL decision, restart the backend, and confirm all data is preserved.

### Implementation for User Story 2

- [X] T013 [US2] Activate DB persistence in `SmeacFacade.submit_smeac_order()` in src/uservice/smeac/facade/smeac.py — un-comment the `SmeacOrder` creation and `self.session.add()`/`flush()` block, import `SmeacOrder` from src/uservice/smeac/models/storage/smeac.py
- [X] T014 [US2] Replace hardcoded response in `SmeacFacade.get_order_status()` in src/uservice/smeac/facade/smeac.py — query DB via `self.session.get(SmeacOrder, order_id)`, raise `ResourceDoesNotExist` if not found, return real status with joined commands and violations
- [X] T015 [US2] Replace in-memory `_pending_decisions` dict in src/uservice/hitl/facade/hitl.py — rewrite `create_hitl_request()`, `submit_decision()`, and `get_pending_decisions()` to use `self.session` with the `HitlDecision` ORM model, remove the module-level `_pending_decisions` variable
- [X] T016 [US2] Replace in-memory `_swarms` dict in src/uservice/swarm/operations/create.py — rewrite `provision_swarm()`, `get_swarm()`, and `list_swarms()` to accept an `AsyncSession` parameter and use the `SwarmInstance` ORM model for all CRUD, remove the module-level `_swarms` variable
- [X] T017 [US2] Update src/uservice/swarm/operations/delete.py — replace the import of `_swarms` from create.py with a DB query via session to fetch the `SwarmInstance` record, update status through proper state transitions (`draining` → await pending orders → `terminated`)
- [X] T018 [US2] Update src/uservice/security/proxy.py — replace `from src.uservice.swarm.operations.create import _swarms` with a DB query to look up the `SwarmInstance` by ID using the request's DB session

**Checkpoint**: All state persisted to PostgreSQL. Backend can be restarted and all swarms, orders, and HITL decisions survive.

---

## Phase 5: User Story 3 — Enforced Access Control & Safety Checks (Priority: P1)

**Goal**: Un-comment RBAC checks, integrate Guardian Critic safety verification as a real Temporal activity, and require genuine HITL approval.

**Independent Test**: Attempt operations with different JWT scopes — verify unauthorized users are blocked. Submit a SMEAC order and confirm safety checks execute and can block unsafe orders. Verify HITL waits for real human approval.

### Implementation for User Story 3

- [X] T019 [US3] Activate RBAC in SmeacFacade in src/uservice/smeac/facade/smeac.py — un-comment `self.require_scope("smeac:create")` and `self.require_scope("smeac:read")` (NOTE: using `require_scope()` instead of `require_access()` because the base `DomainFacade` in `src/uservice/base/facade/base.py` uses `require_scope()`)
- [X] T020 [US3] Activate RBAC in HitlFacade in src/uservice/hitl/facade/hitl.py — un-comment `self.require_scope("hitl:decide")` and `self.require_scope("hitl:read")`
- [X] T021 [US3] Create Guardian Critic Temporal activity in src/uservice/smeac/operations/safety_activity.py — wrap the existing `verify_command()` function from src/uservice/swarm/operations/swarm_agents.py as a `@activity.defn` that accepts command data and returns a list of violations
- [X] T022 [US3] Integrate safety activity into `ProcessSmeacWorkflow` in src/uservice/smeac/operations/process.py — replace the empty `for cmd in commands: pass` block with `await workflow.execute_activity("safety_check_activity", cmd, ...)` and block on violations (return error with violation details)
- [X] T023 [US3] Implement real HITL signal handling in `ProcessSmeacWorkflow` in src/uservice/smeac/operations/process.py — replace `hitl_approved = True` with a `@workflow.signal` handler that receives a HITL decision, and `await workflow.wait_condition()` that pauses until the signal is received for high-impact commands
- [X] T024 [US3] Wire HITL decision to Temporal signal in src/uservice/hitl/facade/hitl.py — in `submit_decision()`, after persisting the decision to DB, call `await signal_workflow(workflow_id, "hitl_decision", decision_data)` using the existing `signal_workflow()` from src/uservice/operation/facade.py

**Checkpoint**: RBAC blocks unauthorized access. Safety checks run and can block unsafe commands. HITL requires real human approval via Temporal signals.

---

## Phase 6: User Story 4 — Real-time Drone Telemetry (Priority: P2)

**Goal**: Dashboard shows real telemetry data from drones, not a hardcoded array.

**Independent Test**: Start a swarm with active edge nodes, open the dashboard, verify telemetry data updates every 2 seconds with values that change over time.

### Implementation for User Story 4

- [X] T025 [US4] Create telemetry endpoint `GET /api/v1/swarms/{swarm_id}/telemetry` in src/uservice/swarm/api/routes.py — aggregates telemetry from edge nodes by querying their `/health` or a new `/telemetry` endpoint via `httpx`
- [X] T026 [US4] Replace hardcoded `fetchTelemetry()` in src/dashboard/js/api.js — remove the simulated `drones` array return and implement a real `fetch()` call to `${API_BASE}/swarms/${swarmId}/telemetry` with the auth header
- [X] T027 [P] [US4] Add a `GET /telemetry` endpoint to the edge server in src/edge/api/server.py — returns current position, battery, and mission status from the navigation and vision subsystems

**Checkpoint**: Dashboard shows real, live-updating telemetry data from active drones.

---

## Phase 7: User Story 5 — Real Container Provisioning for Swarms (Priority: P2)

**Goal**: Swarm creation provisions real Docker containers; deletion terminates and removes them.

**Independent Test**: Create a swarm, run `docker ps` to verify real containers. Delete the swarm, verify containers are gone.

### Implementation for User Story 5

- [X] T028 [US5] Replace simulated `container_id` in `provision_swarm()` in src/uservice/swarm/operations/create.py — use `docker.from_env().containers.run()` to start real containers with the swarm's configuration, store the real `container.id` in the DB record, add `isc-swarm` label to containers for identification
- [X] T029 [US5] Implement real container termination in `drain_swarm()` in src/uservice/swarm/operations/delete.py — call `container.stop()` and `container.remove()` via Docker SDK, wait for completion, handle errors (container already stopped, not found), update DB status only after confirmed termination
- [X] T030 [US5] Add error handling for Docker provisioning failures in src/uservice/swarm/operations/create.py — on `docker.errors.DockerException` or `docker.errors.APIError`, set swarm status to `failed`, perform cleanup of any partially created containers, and raise a descriptive error

**Checkpoint**: `docker ps --filter "label=isc-swarm"` shows real containers after swarm creation. Containers are cleaned up on deletion.

---

## Phase 8: User Story 6 — Geofencing Enforcement (Priority: P2)

**Goal**: `check_geofencing()` evaluates drone positions against defined restricted zones instead of always returning `None`.

**Independent Test**: Define a restricted zone, pass a coordinate inside it — verify violation returned. Pass a coordinate outside — verify `None` returned.

### Implementation for User Story 6

- [X] T031 [US6] Create restricted zones configuration file at config/restricted_zones.json — define a JSON schema for zone polygons with `id`, `name`, `polygon` (GeoJSON), `altitude_min_m`, `altitude_max_m`, `active` fields
- [X] T032 [US6] Implement real `check_geofencing()` in src/uservice/swarm/operations/swarm_agents.py — load zones from config/restricted_zones.json, use `shapely.geometry.Point` and `shapely.geometry.shape()` for point-in-polygon intersection, return a `Violation` with zone details if the target area intersects any active zone

**Checkpoint**: Geofencing correctly detects zone violations and returns `None` for safe coordinates.

---

## Phase 9: User Story 7 — Production Edge Hardware Integration (Priority: P3)

**Goal**: Edge modules use real hardware when available and fail clearly when hardware is absent (unless `SIMULATION_MODE=true`).

**Independent Test**: On a Raspberry Pi 5 with hardware connected, verify real camera frames, real detections, and real MAVSDK commands. Without hardware (and `SIMULATION_MODE=false`), verify clear error messages.

### Implementation for User Story 7

- [X] T033 [US7] Replace hardcoded `frame_center_x = 320` in src/edge/navigation/flight_controller.py — derive from `self.camera.width // 2` dynamically
- [X] T034 [US7] Replace simulated `approach_distance_m` decrement in src/edge/navigation/flight_controller.py — integrate with MAVSDK telemetry `async for position in drone.telemetry.position()` to get real distance from target coordinates
- [X] T035 [US7] Implement real yaw command in `_apply_heading_correction()` in src/edge/navigation/flight_controller.py — replace the `pass` with an actual `await drone.action.set_yaw(yaw_deg)` call via MAVSDK when `MAVSDK_AVAILABLE` is True
- [X] T036 [US7] Initialize MAVSDK `System` connection in `FlightController.__init__()` or `start()` in src/edge/navigation/flight_controller.py — connect to the drone via MAVSDK system discovery so telemetry and action commands work
- [X] T037 [US7] Remove FastAPI conditional import stub in src/edge/api/server.py — make FastAPI a hard requirement (no `try/except ImportError`) when `SIMULATION_MODE` is not `true`, raise `RuntimeError` with installation instructions if missing

**Checkpoint**: Edge modules produce real hardware output when hardware is connected. Clear errors when hardware is missing and not in simulation mode.

---

## Phase 10: User Story 8 — Secure API Gateway Routing (Priority: P3)

**Goal**: Security proxy rejects requests to unregistered swarm endpoints instead of falling through to local routes.

**Independent Test**: Send a request to a non-existent swarm ID — verify 404 response instead of local route fallthrough.

### Implementation for User Story 8

- [X] T038 [US8] Replace fallthrough behavior in `swarm_proxy_middleware()` in src/uservice/security/proxy.py — change the `if not swarm_record or not swarm_record.get("endpoint_url"): return await call_next(request)` block to return `JSONResponse(status_code=404, content={"error": "Swarm not found or not available"})` when the swarm doesn't exist in the DB

**Checkpoint**: Requests to unregistered swarm endpoints return 404 instead of falling through. Registered swarms route correctly.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, documentation updates, and final validation.

- [ ] T039 [P] Remove all `# MVP mock` / `# In-memory` / `# Placeholder` / `# For MVP` comments from modified files across src/ that reference the now-removed mock implementations
- [ ] T040 [P] Update src/dashboard/index.html version tag from `v0.1.0 MVP` to `v0.2.0` to reflect production readiness
- [ ] T041 Run quickstart.md validation scenarios end-to-end per specs/002-replace-mocks-production/quickstart.md — execute all V1-V8 validation scenarios and the Success Verification Checklist grep checks
- [ ] T042 Run existing test suite with `pytest tests/ -v` and fix any regressions caused by mock removal

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 (auth module must exist before tokens can be used)
- **US2 (Phase 4)**: Depends on Phase 2 only (DB persistence is independent of dashboard auth)
- **US3 (Phase 5)**: Depends on Phase 2 (RBAC helper) + Phase 4 (DB persistence must be in place before RBAC is enforced on DB-backed operations)
- **US4 (Phase 6)**: Depends on Phase 3 (dashboard auth) + Phase 4 (DB for swarm lookup)
- **US5 (Phase 7)**: Depends on Phase 4 (DB persistence for swarm records)
- **US6 (Phase 8)**: Depends on Phase 1 (shapely dependency)
- **US7 (Phase 9)**: Depends on Phase 2 (SIMULATION_MODE env var)
- **US8 (Phase 10)**: Depends on Phase 4 (DB-backed swarm lookup)
- **Polish (Phase 11)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (Dashboard Auth)**: Phase 2 only → can start immediately after Foundational
- **US2 (DB Persistence)**: Phase 2 only → can start immediately after Foundational, **can run in parallel with US1**
- **US3 (RBAC + Safety)**: Phase 2 + US2 → must wait for DB persistence
- **US4 (Telemetry)**: US1 + US2 → must wait for auth + DB
- **US5 (Docker Containers)**: US2 → must wait for DB persistence
- **US6 (Geofencing)**: Phase 1 only → can start after Setup, **can run in parallel with everything**
- **US7 (Edge Hardware)**: Phase 2 only → can start after Foundational, **can run in parallel with US1/US2**
- **US8 (Proxy Routing)**: US2 → must wait for DB persistence

### Within Each User Story

- Models/schema changes before service/facade changes
- Facade changes before API route changes
- Backend changes before dashboard changes (where both are involved)

### Parallel Opportunities

- **After Phase 1**: US6 (Geofencing) can begin immediately — no dependency on auth or DB
- **After Phase 2**: US1, US2, and US7 can all start in parallel (different files, different layers)
- **After US2**: US3, US5, and US8 can all start in parallel
- **Within US1**: T010 and T011 modify different files and can run in parallel (T009 and T012 both modify `api.js` and must be sequential)
- **Within US3**: T019 and T020 modify different facade files and can run in parallel
- **Within US7**: T033-T036 modify the same file — must be sequential; T037 is independent

---

## Parallel Example: Phase 3 + Phase 4 + Phase 8

```text
# After Phase 2 completes, these can all run in parallel:

# Developer A — User Story 1 (Dashboard Auth):
Task T009: Replace hardcoded AUTH_HEADER in src/dashboard/js/api.js
Task T010: Replace hardcoded token in src/dashboard/js/hitl.js
Task T011: Replace mock auth in src/dashboard/js/auth_indicator.js
Task T012: Wire 401 handling in src/dashboard/js/api.js

# Developer B — User Story 2 (DB Persistence):
Task T013: Activate DB persistence in src/uservice/smeac/facade/smeac.py
Task T014: Replace hardcoded get_order_status in src/uservice/smeac/facade/smeac.py
Task T015: Replace in-memory HITL in src/uservice/hitl/facade/hitl.py
Task T016: Replace in-memory swarms in src/uservice/swarm/operations/create.py
Task T017: Update swarm deletion in src/uservice/swarm/operations/delete.py
Task T018: Update security proxy in src/uservice/security/proxy.py

# Developer C — User Story 6 (Geofencing, can start even earlier):
Task T031: Create restricted zones config
Task T032: Implement real check_geofencing
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T008)
3. Complete Phase 3: US1 — Dashboard Auth (T009-T012)
4. Complete Phase 4: US2 — DB Persistence (T013-T018)
5. Complete Phase 5: US3 — RBAC + Safety (T019-T024)
6. **STOP and VALIDATE**: Run quickstart V1-V4 scenarios. The system now has real auth, real persistence, and real access control.

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 + US2 (parallel) → Auth + Persistence done → Core MVP
3. US3 → RBAC + Safety → Security hardened
4. US4 + US5 + US6 (parallel) → Telemetry, containers, geofencing → Operational features
5. US7 + US8 → Edge hardware + proxy routing → Production-complete
6. Polish → Cleanup + full validation

### Single Developer Strategy

1. Phase 1 → Phase 2 → US1 → US2 → US3 → US4 → US5 → US6 → US7 → US8 → Polish
2. Priority order ensures the most critical mocks are replaced first
3. Each phase checkpoint provides a validatable increment

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The existing ORM models, database engine, JWT middleware, and Temporal infrastructure are already in place — most tasks involve *wiring* these components, not creating new architecture

---

## Phase 12: Convergence

- [X] T043 [CRITICAL] Execute architecture review using .agents/agents/uservice-arch-reviewer to verify strict alignment with architectural design per Constitution II/Verification (missing)
- [X] T044 [HIGH] Run existing test suite with `pytest tests/ -v` and fix any regressions per T042 / Polish (missing)
- [X] T045 [MEDIUM] Run quickstart.md validation scenarios end-to-end per T041 / Polish (missing)
- [X] T046 [LOW] Update src/dashboard/index.html version tag from `v0.1.0 MVP` to `v0.2.0` per T040 / Polish (missing)
- [X] T047 [LOW] Remove all remaining `# MVP mock`, `# In-memory`, `# Placeholder`, or `# For MVP` comments across `src/` per T039 / Polish (missing)
