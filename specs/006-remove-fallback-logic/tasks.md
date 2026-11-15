---
description: "Task list for feature implementation: Enforce Single-Path Success Logic & Remove Fallbacks"
---

# Tasks: Enforce Single-Path Success Logic & Remove Fallbacks

**Input**: Design documents from `/specs/006-remove-fallback-logic/`  
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/rest-api.md](./contracts/rest-api.md), [quickstart.md](./quickstart.md)

**Tests**: Test suite alignment and verification tasks are included per `FR-008` and `SC-003`/`SC-004` in [spec.md](./spec.md) to verify single-path production execution, real-wheel usage, and explicit HTTP `500` error propagation.

**Organization**: Tasks are grouped by user story (`US1`–`US3`) in priority order to enable independent implementation, verification, and incremental delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`) — omitted in Setup, Foundational, and Polish phases
- Include exact repository file paths in every task description

## Path Conventions

- Unified repository layout at root: `src/uservice/`, `src/edge/`, `src/dashboard/`, `scripts/`, `tests/`, `requirements.txt`, `pyproject.toml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Synchronize dependency manifests and `.venv` with real wheels for every runtime, Edge, and test package.

- [X] T001 Declare all mandatory runtime, Edge, and test dependencies unconditionally (shapely, duckdb, pyarrow, aiomqtt, neo4j, paho-mqtt, boto3, opencv-python-headless, ultralytics, mavsdk, aiosqlite, google-genai, and opentelemetry-api>=1.27,<1.34) in requirements.txt and pyproject.toml
- [X] T002 Synchronize and install all required wheels in .venv and verify direct unconditional imports per specs/006-remove-fallback-logic/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Remove database/schema/lifespan fallbacks and `aiosqlite` test shim that block single-path story implementation.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Remove _ensure_aiosqlite_shim() and its try/except ImportError stdlib sqlite3 fallback from tests/conftest.py while retaining boundary service test doubles
- [X] T004 [P] Remove threat_check_mode and degraded_reason columns from SmeacOrder and HitlDecision ORM models in src/uservice/smeac/models/storage/smeac.py and src/uservice/hitl/models/storage/decision.py
- [X] T005 [P] Remove fallback_static_zones, threat_check_mode, degraded_mode, degraded_reason, "static_baseline", and "degraded_unavailable" fields/literals and set AarQueryResponse.engine default to "duckdb" across src/uservice/threat/models/contract/schemas.py, src/uservice/smeac/models/contract/schemas.py, src/uservice/hitl/models/contract/schemas.py, src/uservice/telemetry/models/contract/events.py, and src/uservice/analytics/models/contract/aar.py
- [X] T006 Remove except MinioUnavailableError and except MemgraphUnavailableError "continuing degraded" catches from lifespan and _handle_detection in src/uservice/main.py

**Checkpoint**: Foundation ready — user story implementation (`US1`–`US3`) can now begin cleanly in parallel or priority order.

---

## Phase 3: User Story 1 - Fail-Fast Dependency Enforcement Across Core & Edge Modules (Priority: P1) 🎯 MVP

**Goal**: Ensure every Core and Edge module imports its mandatory runtime libraries unconditionally without `*_AVAILABLE` flags or `try...except ImportError` branches, while keeping `EdgeSpool` SQLite WAL DDIL buffering intact.

**Independent Test**: Verify via `.venv/bin/pytest tests/unit/test_edge_spool.py tests/contract/test_mqtt_contract.py`, direct module import checks, and static grep check `grep -rnE "_AVAILABLE|except ImportError" src/edge/ src/uservice/telemetry/operations/ingestor.py src/uservice/threat/operations/graph_client.py tests/conftest.py` (must return zero matches).

### Verification for User Story 1

- [X] T007 [P] [US1] Verify EdgeSpool SQLite WAL DDIL buffering and MQTT contract tests pass with unconditional paho.mqtt.client imports in tests/unit/test_edge_spool.py and tests/contract/test_mqtt_contract.py

### Implementation for User Story 1

- [X] T008 [P] [US1] Remove MAVSDK_AVAILABLE (try/except ImportError) and conditional fallback branches in src/edge/api/server.py and src/edge/navigation/flight_controller.py
- [X] T009 [P] [US1] Remove OPENCV_AVAILABLE (try/except ImportError) and conditional frame capture/encoding branches in src/edge/vision/camera.py
- [X] T010 [P] [US1] Remove YOLO_AVAILABLE (try/except ImportError) and PIL.Image fallback inside crop_detection_jpeg in src/edge/vision/inference.py
- [X] T011 [P] [US1] Remove PAHO_AVAILABLE (try/except ImportError) and non-Paho publish bypass branches while retaining EdgeSpool SQLite WAL DDIL buffering in src/edge/telemetry/publisher.py
- [X] T012 [P] [US1] Remove AIOMQTT_AVAILABLE (try/except ImportError) guard and conditional _subscribe_loop skip in src/uservice/telemetry/operations/ingestor.py
- [X] T013 [P] [US1] Remove NEO4J_AVAILABLE (try/except ImportError) check in _get_driver() and import neo4j unconditionally in src/uservice/threat/operations/graph_client.py

**Checkpoint**: User Story 1 (MVP) is complete — all Core/Edge dependency guards are removed and services fail fast on missing packages.

---

## Phase 4: User Story 2 - Canonical Single-Engine Execution for Analytics, Archival, and Spatial Safety (Priority: P2)

**Goal**: Execute archival strictly via PyArrow `PAR1` Parquet, analytics strictly via DuckDB (`engine="duckdb"`), and spatial/threat checks strictly via Shapely + Memgraph, removing custom fallbacks, static JSON threat rules, `503` degraded catches, and degraded UI/schema surfaces so upstream outages raise HTTP `500`.

**Independent Test**: Run `.venv/bin/pytest tests/unit/test_telemetry_compactor.py tests/unit/test_duckdb_aar.py tests/unit/test_threat_gating.py tests/contract/test_threat_and_hitl_contract.py -v` and confirm standard `PAR1` Parquet output, `duckdb` AAR execution, live Memgraph HTTP `500` error propagation on outages, and zero `degraded_mode`/`fallback_static_zones`/`sqlite_olap`/`PAR1ISCC` occurrences in schemas or dashboard UI.

### Tests for User Story 2

> **NOTE**: Update test expectations FIRST to match single-path contracts and verify they fail until User Story 2 modules are refactored.

- [X] T014 [P] [US2] Update unit tests in tests/unit/test_telemetry_compactor.py and tests/unit/test_duckdb_aar.py to assert standard pyarrow PAR1 Parquet output and duckdb engine exclusively without PAR1ISCC or sqlite_olap fallbacks
- [X] T015 [P] [US2] Update unit and contract tests in tests/unit/test_threat_gating.py and tests/contract/test_threat_and_hitl_contract.py to assert MemgraphUnavailableError propagation, HTTP 500 on Memgraph/MinIO outages, and removal of degraded_mode, threat_check_mode, and fallback_static_zones

### Implementation for User Story 2

- [X] T016 [P] [US2] Remove PYARROW_AVAILABLE, _ISC_COL_HEADER = b"PAR1ISCC", _ISC_COL_FOOTER = b"PAR1", and custom binary serialization in src/uservice/telemetry/operations/compactor.py
- [X] T017 [P] [US2] Remove DUCKDB_AVAILABLE, "sqlite_olap" fallback engine, and blob.startswith(b"PAR1ISCC") parser in src/uservice/analytics/operations/duckdb_runner.py
- [X] T018 [P] [US2] Remove SHAPELY_AVAILABLE, _point_in_ring, dual _polygon_contains branching, and all runtime config/restricted_zones.json reads from src/uservice/swarm/operations/swarm_agents.py (retaining config/restricted_zones.json on disk only if used by scripts/seed_threats.py)
- [X] T019 [US2] Remove _point_in_ring, non-Shapely _polygon_contains, load_static_restricted_zones(), _evaluate_static_zones(), and all runtime config/restricted_zones.json / except MemgraphUnavailableError static fallback branches from src/uservice/threat/facade/threat.py
- [X] T020 [P] [US2] Remove "degraded_unavailable" and degraded_mode fallback states in src/uservice/telemetry/models/storage/live_state.py and src/uservice/telemetry/facade/telemetry.py
- [X] T021 [P] [US2] Remove list_threats_with_meta degraded wrapper, meta={"degraded_mode": ...}, and 503 degraded catches in src/uservice/threat/api/routes.py and src/uservice/analytics/api/routes.py so upstream outages return HTTP 500
- [X] T022 [P] [US2] Remove #degraded-banner, updateDegradedBanner(), fallback_static_zones handling, fallbackStaticZones map rendering loop, and deterministic_fallback / threat_check_mode UI warnings in src/dashboard/index.html, src/dashboard/js/api.js, src/dashboard/js/main.js, src/dashboard/js/map.js, and src/dashboard/js/hitl.js

**Checkpoint**: User Stories 1 and 2 are complete — analytics, archival, telemetry projection, and spatial threat gating operate exclusively on canonical single engines and propagate infrastructure errors as HTTP `500`.

---

## Phase 5: User Story 3 - Explicit Failure Propagation for Mission Planning, Orchestration, and Security (Priority: P3)

**Goal**: Remove placeholder API keys, regex/template SMEAC fallbacks, silent HITL exception catches, Temporal multi-host retries, and default `"dev_passphrase"` credentials so missing config or upstream outages surface directly as explicit failures (HTTP `500`).

**Independent Test**: Run `.venv/bin/pytest tests/unit/test_smeac_copilot.py tests/unit/test_hitl_override.py -v` and exercise `POST /api/v1/swarms/{swarm_id}/orders`, `POST /api/v1/smeac/draft`, `POST /api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide`, and `POST /api/v1/login` with missing `GEMINI_API_KEY` / `COMMANDER_PASSPHRASE` or simulated upstream errors to confirm immediate explicit failures without regex, template, or dev-credential fallbacks.

### Tests for User Story 3

> **NOTE**: Update test expectations FIRST and verify they fail until User Story 3 modules are refactored.

- [X] T023 [P] [US3] Update unit tests in tests/unit/test_smeac_copilot.py to verify missing GEMINI_API_KEY or upstream LLM/Memgraph/MinIO failures raise explicit exceptions instead of returning template drafts or degraded_reasons

### Implementation for User Story 3

- [X] T024 [P] [US3] Remove os.environ["GOOGLE_API_KEY"] = "placeholder_key" fallback in src/uservice/base/agent.py and update agent initialization in src/uservice/smeac/operations/smeac_agents.py so missing Gemini credentials fail explicitly on invocation
- [X] T025 [P] [US3] Remove deterministic template synthesis fallback, "static_baseline" citations, and graph_degraded, aar_degraded, llm_degraded, and degraded_reasons tracking in src/uservice/smeac/operations/copilot.py
- [X] T026 [US3] Remove GEMINI_API_KEY-missing fallback, regex coordinate fallback (if not formatted_cmds:), try/except around start_workflow, try/except MinioUnavailableError/MemgraphUnavailableError in generate_smeac_draft, and threat_check_mode/degraded_mode/degraded_reason tracking across src/uservice/smeac/facade/smeac.py, src/uservice/smeac/operations/safety_activity.py, src/uservice/smeac/operations/process.py, and src/uservice/smeac/api/routes.py
- [X] T027 [P] [US3] Remove silent except Exception catch-and-log suppression around Memgraph override recording and Temporal signaling and remove threat_check_mode and degraded_reason fields in src/uservice/hitl/facade/hitl.py and src/uservice/hitl/api/routes.py
- [X] T028 [P] [US3] Remove multi-host fallback loop ["127.0.1.1:7233", "127.0.0.1:7233", "localhost:7233"] in get_temporal_client in src/uservice/operation/facade.py
- [X] T029 [P] [US3] Remove expected_passphrase = "dev_passphrase" fallback and {"dev_passphrase", "dev-passphrase"} bypass in login in src/uservice/security/routes.py so missing COMMANDER_PASSPHRASE raises HTTP 500

**Checkpoint**: All three user stories (`US1`, `US2`, `US3`) are complete and independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Align end-to-end integration tests/scripts with strict env & HTTP `500` contracts and run full static purity and test suite verification.

- [X] T030 [P] Update integration suites and stack verification script with required COMMANDER_PASSPHRASE and GEMINI_API_KEY configuration and single-path HTTP 500 assertions in tests/integration/test_e2e.py, tests/integration/test_pma_pipeline.py, and scripts/verify_pma_stack.py
- [X] T031 Run static fallback-purity grep audits, verify EdgeSpool preservation, execute full .venv/bin/pytest verification per specs/006-remove-fallback-logic/quickstart.md, log OODA execution via .agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py against LTV Node Point Verification_1_Constraint_Graph, and run uservice-arch-reviewer architecture check

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1: `T001`–`T002`)**: Starts immediately; blocks Foundational and all User Stories because `.venv` must have all real wheels installed cleanly (`opentelemetry-api<1.34`, `pyarrow`, `duckdb`, `shapely`, `aiosqlite`, Edge wheels).
- **Foundational (Phase 2: `T003`–`T006`)**: Depends on Phase 1; removes shared ORM/DTO degraded fields, `aiosqlite` shim, and lifespan degraded handlers before story-level refactoring begins (`T003`, `T004`, `T005` are mutually parallel; `T006` follows).
- **User Story 1 (`T007`–`T013`)**: Depends on Phase 2; `T007`–`T013` modify distinct files across `src/edge/`, `src/uservice/telemetry/operations/ingestor.py`, `src/uservice/threat/operations/graph_client.py`, and `tests/` and can execute fully in parallel.
- **User Story 2 (`T014`–`T022`)**: Depends on Phase 2 (`T004`, `T005`, `T006`) and `T013` (`graph_client.py` unconditional `neo4j`); tests `T014`–`T015` execute first, followed in parallel by `T016`, `T017`, `T018`, `T020`, `T022`, with `T019` (`threat/facade/threat.py`) and `T021` (`threat/analytics routes.py`) completing route alignment.
- **User Story 3 (`T023`–`T029`)**: Depends on Phase 2 (`T004`, `T005`) and `T019` (`ThreatFacade` signatures without `threat_check_mode`/`degraded_mode`); test `T023` executes first, then `T024`, `T025`, `T027`, `T028`, `T029` execute in parallel and `T026` integrates across SMEAC facade/activities/routes (note: `T024`–`T029` only depend on Phase 2 + `T019`, and `US2` and `US3` can overlap once `T019` lands).
- **Polish (Phase 6: `T030`–`T031`)**: Depends on all User Stories (`T001`–`T029`) completing; `T031` runs final static audits and `.venv/bin/pytest`.

---

## Parallel Execution Examples

### User Story 1 (`US1` — Unconditional Imports)

```bash
# Run T008–T013 in parallel across disjoint files:
Task: "T008 Remove MAVSDK_AVAILABLE in src/edge/api/server.py and src/edge/navigation/flight_controller.py"
Task: "T009 Remove OPENCV_AVAILABLE in src/edge/vision/camera.py"
Task: "T010 Remove YOLO_AVAILABLE and PIL.Image crop fallback in src/edge/vision/inference.py"
Task: "T011 Remove PAHO_AVAILABLE while retaining EdgeSpool in src/edge/telemetry/publisher.py"
Task: "T012 Remove AIOMQTT_AVAILABLE in src/uservice/telemetry/operations/ingestor.py"
Task: "T013 Remove NEO4J_AVAILABLE in src/uservice/threat/operations/graph_client.py"
```

### User Story 2 (`US2` — Single-Engine Analytics, Archival & Spatial Safety)

```bash
# Run test updates T014–T015 first, then launch T016, T017, T018, T020, T022 in parallel:
Task: "T016 Remove PYARROW_AVAILABLE & PAR1ISCC in src/uservice/telemetry/operations/compactor.py"
Task: "T017 Remove DUCKDB_AVAILABLE & sqlite_olap in src/uservice/analytics/operations/duckdb_runner.py"
Task: "T018 Remove SHAPELY_AVAILABLE & _point_in_ring in src/uservice/swarm/operations/swarm_agents.py"
Task: "T020 Remove degraded_unavailable & degraded_mode in src/uservice/telemetry/"
Task: "T022 Remove degraded banners & static zone UI in src/dashboard/"
```

### User Story 3 (`US3` — Explicit Failure Propagation)

```bash
# Run test update T023 first, then launch T024, T025, T027, T028, T029 in parallel alongside T026:
Task: "T024 Remove placeholder_key in src/uservice/base/agent.py and src/uservice/smeac/operations/smeac_agents.py"
Task: "T025 Remove template fallback & degraded flags in src/uservice/smeac/operations/copilot.py"
Task: "T027 Remove silent exception catches & degraded fields in src/uservice/hitl/facade/hitl.py and src/uservice/hitl/api/routes.py"
Task: "T028 Remove Temporal host loop in src/uservice/operation/facade.py"
Task: "T029 Remove dev_passphrase fallback in src/uservice/security/routes.py"
```

---

## Implementation Strategy

### MVP First (Phase 1 + Phase 2 + User Story 1 Only)

1. Complete **Phase 1 (`T001`–`T002`)** so `.venv` has authentic wheels for all dependencies without conflicts.
2. Complete **Phase 2 (`T003`–`T006`)** to strip ORM/DTO degraded fields, the `aiosqlite` shim, and degraded startup handlers.
3. Complete **Phase 3 (`T007`–`T013`, US1)** to guarantee fail-fast dependency enforcement across all Core and Edge modules.
4. **STOP & VALIDATE**: Run unconditional import checks and `pytest tests/unit/test_edge_spool.py tests/contract/test_mqtt_contract.py`.

### Incremental Delivery

1. Deliver **Phase 1 + 2 + US1 (`T001`–`T013`)** → Fail-fast dependency foundation verified.
2. Add **US2 (`T014`–`T022`)** → Canonical PyArrow `PAR1` + DuckDB + Shapely + Memgraph single-engine safety/analytics verified (`test_telemetry_compactor`, `test_duckdb_aar`, `test_threat_gating`, `test_threat_and_hitl_contract`).
3. Add **US3 (`T023`–`T029`)** → Strict Gemini LLM, Temporal, HITL, and Commander Passphrase error propagation verified (`test_smeac_copilot`).
4. Finish **Polish (`T030`–`T031`)** → Align integration suites and pass all static purity grep checks + full `.venv/bin/pytest`.
