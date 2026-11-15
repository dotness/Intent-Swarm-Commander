---
description: "Task list for feature implementation: Poor-Man's Artemis.IA (PMA) C4ISR Integration"
---

# Tasks: Poor-Man's Artemis.IA (PMA) C4ISR Integration

**Input**: Design documents from `/specs/005-pma-integration/`
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/mqtt-telemetry.md](./contracts/mqtt-telemetry.md), [contracts/rest-api.md](./contracts/rest-api.md), [quickstart.md](./quickstart.md)

**Tests**: Explicitly included per `FR-014` and `SC-007` in [spec.md](./spec.md) (strictly hermetic, network-isolated test suites with zero outbound internet/API calls).

**Organization**: Tasks are grouped by user story (`US1`–`US4`) in priority order to enable independent implementation, hermetic validation, and incremental MVP delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story mapping (`[US1]`, `[US2]`, `[US3]`, `[US4]`) — used strictly in User Story phases
- Every task includes exact repository file paths

## Path Conventions

- Single unified repository at root: `src/uservice/`, `src/edge/`, `src/dashboard/`, `scripts/`, `tests/`
- Architecture follows `uservice-template` layered DDD packages (`api/`, `facade/`, `models/`, `operations/`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Validate dependencies, configure unified `c2-shared-net` single-host deployment, and scaffold new domain packages.

- [X] T001 Validate new Python dependencies (paho-mqtt, aiomqtt, pyarrow, duckdb, boto3, neo4j) via scan_dependencies and declare pinned versions in requirements.txt and pyproject.toml
- [X] T002 [P] Configure unified single-host c2-shared-net bridge network, shared Temporal task queues (isc-smeac-queue and pma-ingestion-queue), and non-conflicting service ports for postgres, temporal, mosquitto, minio, memgraph, backend, dashboard, edge_drone, and drone_sim in docker-compose.yml
- [X] T003 [P] Add non-secret PMA environment variable defaults (MQTT_BROKER_HOST, MQTT_BROKER_PORT, MINIO_ENDPOINT, MEMGRAPH_BOLT_URI, DEFAULT_PROJECT_ID, PARQUET_FLUSH_INTERVAL_S, CORRELATION_RADIUS_M, CORRELATION_WINDOW_S, EDGE_SPOOL_DB_PATH) in .env.example
- [X] T004 [P] Scaffold uservice-template domain package directories (api, facade, models/contract, models/storage, operations) in src/uservice/telemetry/__init__.py, src/uservice/threat/__init__.py, src/uservice/analytics/__init__.py, and src/edge/telemetry/__init__.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core database extensions, object/graph clients, gateway routing, legacy simulation cleanup (Constitution Principle VI), and hermetic test harness required before any user story begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 [P] Extend SwarmInstance, SmeacOrder, and HitlDecision ORM models with project_id (default "default-theater"), threat_check_mode, degraded_reason, draft_source_refs, is_threat_override, threat_zone_ids, and override_justification in src/uservice/swarm/models/storage/instance.py, src/uservice/smeac/models/storage/smeac.py, src/uservice/hitl/models/storage/decision.py, and src/uservice/database/engine.py
- [X] T006 [P] Implement MinIO S3 storage client wrapper (tactical-telemetry and tactical-snapshots bucket initialization, object upload/fetch, explicit 503 degraded error signaling) in src/uservice/analytics/operations/minio_store.py
- [X] T007 [P] Implement async Memgraph Bolt client (neo4j async driver, TacticalProject/ThreatZone/TargetEntity/DetectionEvent index setup, timeout and degraded_mode error handling) in src/uservice/threat/operations/graph_client.py
- [X] T008 [P] Update reverse-proxy routing middleware to pass through /api/v1/threats, /api/v1/analytics, /api/v1/targets, and /api/v1/smeac/draft to ISC Backend routers in src/uservice/security/proxy.py
- [X] T009 [P] Remove legacy SIMULATION_MODE, dummy telemetry state, and hardcoded fallback coordinates across src/edge/api/server.py, src/edge/vision/camera.py, src/edge/vision/inference.py, src/edge/navigation/flight_controller.py, src/uservice/smeac/facade/smeac.py, and src/dashboard/js/api.js
- [X] T010 Create global hermetic offline test harness (outbound network socket guard and injectable in-memory MQTT, SQLite, temp PyArrow/DuckDB, MinIO, and Memgraph fixtures) in tests/conftest.py

**Checkpoint**: Foundation ready — user story implementation (`US1`–`US4`) can now begin in priority order or parallel streams.

---

## Phase 3: User Story 1 - High-Throughput Push Telemetry & Persistent Mission Archive (Priority: P1) 🎯 MVP

**Goal**: Eliminate per-drone HTTP polling by streaming telemetry over Mosquitto MQTT with edge SQLite DDIL spooling (live-first reconnect + routine eviction) and compacting streams every 5–15s into Hive-partitioned Apache Parquet files in MinIO.

**Independent Test**: Run hermetic MQTT contract, SQLite spool overflow/replay unit tests, and 5–15s Parquet compactor unit tests offline (`pytest tests/contract/test_mqtt_contract.py tests/unit/test_edge_spool.py tests/unit/test_telemetry_compactor.py`), and verify live push projection on `GET /api/v1/swarms/{swarm_id}/telemetry` without HTTP polling or fabricated coordinates.

### Tests for User Story 1 (Hermetic Offline Verification)

> **NOTE**: Write these tests FIRST and verify they FAIL before implementation.

- [X] T011 [P] [US1] Write MQTT topic hierarchy, QoS 0 vs QoS 1 policy, LWT, and SwarmTelemetryEvent schema contract tests in tests/contract/test_mqtt_contract.py
- [X] T012 [P] [US1] Write unit tests for SQLite edge_spool capacity overflow eviction (evicting priority=0 navigation before priority=1 detections/alerts) and live-first + async backlog replay ordering in tests/unit/test_edge_spool.py
- [X] T013 [P] [US1] Write unit tests for 5-15s PyArrow Parquet micro-batch compaction, event_id deduplication, and project_id partition isolation in tests/unit/test_telemetry_compactor.py

### Implementation for User Story 1

- [X] T014 [P] [US1] Define SwarmTelemetryEvent and TelemetryProjectionResponse Pydantic contract DTOs in src/uservice/telemetry/models/contract/events.py
- [X] T015 [P] [US1] Implement SQLite WAL DDIL write-ahead spool (edge_spool table, priority-aware eviction, replay cursor) in src/edge/telemetry/spool.py
- [X] T016 [US1] Implement EdgeTelemetryPublisher (paho-mqtt client, QoS 0/1 routing, LWT registration, live-first reconnect hook, background async spool drain) in src/edge/telemetry/publisher.py and wire into src/edge/navigation/flight_controller.py and src/edge/api/server.py
- [X] T017 [P] [US1] Implement async-safe live telemetry state projection and micro-batch memory buffer in src/uservice/telemetry/models/storage/live_state.py
- [X] T018 [US1] Implement 5-15s PyArrow Parquet micro-batch compactor flushing Hive-partitioned files to MinIO tactical-telemetry bucket in src/uservice/telemetry/operations/compactor.py
- [X] T019 [US1] Implement async MQTT wildcard subscriber (telemetry/projects/+/swarms/+/+/+) with event_id deduplication feeding live projection and Parquet buffer in src/uservice/telemetry/operations/ingestor.py
- [X] T020 [US1] Implement TelemetryFacade (DomainFacade with project_id isolation and staleness/degraded detection) and diagnostics routes in src/uservice/telemetry/facade/telemetry.py and src/uservice/telemetry/api/routes.py
- [X] T021 [US1] Replace synchronous HTTP drone polling in GET /api/v1/swarms/{swarm_id}/telemetry with TelemetryFacade live push projection in src/uservice/swarm/api/routes.py and register telemetry lifespan workers in src/uservice/main.py

**Checkpoint**: User Story 1 (MVP) is complete — continuous push telemetry flows end-to-end with DDIL spool protection and 5–15s persistent Parquet archival.

---

## Phase 4: User Story 2 - Dynamic Battlefield Threat Gating for Mission Orders (Priority: P2)

**Goal**: Replace static geofence-only checks with live Memgraph spatial threat gating (manual deactivation only), enforce mandatory HITL override justification (`422` if blank), provide deterministic `config/restricted_zones.json` degraded fallback, and expose theater threat overlays through the dashboard.

**Independent Test**: Seed or create a `ThreatZone` via `POST /api/v1/threats`, submit an intersecting SMEAC order, confirm `safety_check_activity` blocks auto-approval and enters `pending_hitl`, verify empty HITL approval returns HTTP `422` while documented override succeeds and records provenance, confirm manual deactivation clears subsequent orders, and verify hermetic tests in `tests/unit/test_threat_gating.py`, `tests/unit/test_hitl_override.py`, and `tests/contract/test_threat_and_hitl_contract.py`.

### Tests for User Story 2 (Hermetic Offline Verification)

> **NOTE**: Write these tests FIRST and verify they FAIL before implementation.

- [X] T022 [P] [US2] Write REST contract tests for POST /api/v1/threats, GET /api/v1/threats, PATCH /api/v1/threats/{threat_id}/deactivate, and HITL 422 missing-justification rejection in tests/contract/test_threat_and_hitl_contract.py
- [X] T023 [P] [US2] Write unit tests for Memgraph spatial threat intersection (point.distance + Shapely polygon/altitude check), manual-only deactivation, and deterministic config/restricted_zones.json degraded fallback in tests/unit/test_threat_gating.py
- [X] T024 [P] [US2] Write unit tests for mandatory HITL override justification enforcement and Temporal signal_workflow invocation in tests/unit/test_hitl_override.py

### Implementation for User Story 2

- [X] T025 [P] [US2] Define ThreatZoneCreateRequest, ThreatZoneResponse, ThreatDeactivateRequest, and ThreatConflictDetail Pydantic schemas in src/uservice/threat/models/contract/schemas.py and extend HITL schemas in src/uservice/hitl/models/contract/schemas.py
- [X] T026 [US2] Implement ThreatFacade (create_threat, list_threats, manual-only deactivate_threat, and evaluate_route_threats with openCypher + Shapely and deterministic fallback onto config/restricted_zones.json) in src/uservice/threat/facade/threat.py
- [X] T027 [US2] Implement /api/v1/threats CRUD and manual deactivation endpoints in src/uservice/threat/api/routes.py and mount threat router in src/uservice/main.py
- [X] T028 [US2] Integrate ThreatFacade.evaluate_route_threats into safety_check_activity and update ProcessSmeacWorkflow to block auto-approval on active threat conflicts and route orders to the HITL gate in src/uservice/smeac/operations/safety_activity.py and src/uservice/smeac/operations/process.py
- [X] T029 [US2] Enforce mandatory non-empty rationale (HTTP 422 when blank on is_threat_override=True), record Memgraph INTERSECTS_THREAT override provenance, and fix signal_workflow(workflow_id, "hitl_decision", decision_data) call in src/uservice/hitl/facade/hitl.py and src/uservice/hitl/api/routes.py
- [X] T030 [P] [US2] Create standalone tactical threat seeding CLI script in scripts/seed_threats.py
- [X] T031 [US2] Update Tactical Dashboard map and HITL modal to render active Memgraph ThreatZone overlays, display intersecting threat_conflicts, and require override justification input before approval in src/dashboard/js/map.js, src/dashboard/js/hitl.js, and src/dashboard/index.html

**Checkpoint**: User Story 2 is complete and independently verifiable — dynamic Memgraph threats govern SMEAC validation with audited HITL overrides and deterministic degraded fallback.

---

## Phase 5: User Story 3 - Edge Vision Sensor Fusion & Target Lineage (Priority: P3)

**Goal**: Capture YOLO-E target crops on the edge into MinIO (`tactical-snapshots`), stream QoS 1 detection events, correlate detections across theater missions by target class + spatial-temporal proximity in Memgraph, and expose lineage/snapshots exclusively through ISC Backend.

**Independent Test**: Run `tests/unit/test_target_correlator.py` and `tests/contract/test_target_lineage_contract.py` offline to verify cross-mission entity correlation within `CORRELATION_RADIUS_M` / `CORRELATION_WINDOW_S`, analyst split/confirm review, and authenticated backend snapshot proxying (`GET /api/v1/analytics/detections/{event_id}/snapshot`).

### Tests for User Story 3 (Hermetic Offline Verification)

> **NOTE**: Write these tests FIRST and verify they FAIL before implementation.

- [X] T032 [P] [US3] Write unit tests for automated spatial-temporal+class TargetEntity correlation (CORRELATION_RADIUS_M, CORRELATION_WINDOW_S, same project_id) and analyst confirm/split override in tests/unit/test_target_correlator.py
- [X] T033 [P] [US3] Write REST contract tests for GET /api/v1/targets, GET /api/v1/targets/{target_id}/lineage, POST /api/v1/targets/{target_id}/review, and GET /api/v1/analytics/detections/{event_id}/snapshot in tests/contract/test_target_lineage_contract.py

### Implementation for User Story 3

- [X] T034 [P] [US3] Extend YoloEInference and EdgeTelemetryPublisher to crop JPEG target snapshots, upload to MinIO tactical-snapshots (or queue snapshot_local_path in edge_spool during DDIL), and emit QoS 1 detection MQTT events in src/edge/vision/inference.py and src/edge/telemetry/publisher.py
- [X] T035 [P] [US3] Define TargetEntitySummary, TargetLineageResponse, TargetObservationItem, and TargetReviewRequest DTOs in src/uservice/threat/models/contract/schemas.py
- [X] T036 [US3] Implement openCypher spatial-temporal+class target correlator and analyst confirm/split operations in src/uservice/threat/operations/correlator.py and wire into src/uservice/threat/facade/threat.py and src/uservice/telemetry/operations/ingestor.py
- [X] T037 [US3] Implement /api/v1/targets, /api/v1/targets/{target_id}/lineage, and /api/v1/targets/{target_id}/review in src/uservice/threat/api/routes.py and GET /api/v1/analytics/detections/{event_id}/snapshot proxy route in src/uservice/analytics/api/routes.py
- [X] T038 [US3] Add Target Lineage & Snapshot Evidence inspection modal and map markers in src/dashboard/js/map.js, src/dashboard/js/api.js, and src/dashboard/index.html

**Checkpoint**: User Story 3 is complete — target detections capture visual evidence and preserve traceable multi-mission lineage under `project_id` theater isolation.

---

## Phase 6: User Story 4 - After-Action Review (AAR) Analytics & AI-Assisted SMEAC Drafting (Priority: P4)

**Goal**: Provide sub-2s DuckDB analytical AAR queries over partitioned Parquet datasets and add a non-executing read-only AI SMEAC Copilot (`/api/v1/smeac/draft`) grounded in live threat graph + fleet readiness context with explicit degraded reporting.

**Independent Test**: Verify sub-2s DuckDB AAR query execution on temporary Parquet datasets (`tests/unit/test_duckdb_aar.py`), verify non-executing `draft_only=True` Copilot responses with citations and degraded fallback (`tests/unit/test_smeac_copilot.py`), and confirm dashboard "Draft with AI" populates the order form without launching any drones.

### Tests for User Story 4 (Hermetic Offline Verification)

> **NOTE**: Write these tests FIRST and verify they FAIL before implementation.

- [X] T039 [P] [US4] Write unit tests for DuckDB over Parquet AAR queries (summary, trajectory, battery_decay, detections) verifying <2000ms latency SLO and project_id filtering in tests/unit/test_duckdb_aar.py
- [X] T040 [P] [US4] Write unit and contract tests for POST /api/v1/smeac/draft verifying read-only tool invocation, draft_only=True non-execution invariant, source citations, and explicit degraded_mode fallback in tests/unit/test_smeac_copilot.py

### Implementation for User Story 4

- [X] T041 [P] [US4] Define AarQueryRequest, AarQueryResponse, SmeacDraftRequest, and SmeacDraftResponse DTOs in src/uservice/analytics/models/contract/aar.py and src/uservice/smeac/models/contract/schemas.py
- [X] T042 [US4] Implement embedded DuckDB Parquet query runner (summary, trajectory, battery_decay, detections over MinIO/local Parquet partitions) and AnalyticsFacade in src/uservice/analytics/operations/duckdb_runner.py and src/uservice/analytics/facade/analytics.py
- [X] T043 [US4] Implement GET /api/v1/analytics/aar in src/uservice/analytics/api/routes.py and register analytics router in src/uservice/main.py
- [X] T044 [US4] Implement read-only ADK/pydantic-ai SMEAC Copilot agent querying ThreatFacade, AnalyticsFacade, and SwarmFacade to synthesize non-executing DRAFT orders with source_citations and explicit degraded_mode fallback in src/uservice/smeac/operations/copilot.py, src/uservice/smeac/facade/smeac.py, and src/uservice/smeac/api/routes.py
- [X] T045 [US4] Add AAR Analytics view, AI SMEAC Copilot "Draft with AI" form population flow (requiring explicit HITL submission), and degraded-service status banner in src/dashboard/index.html, src/dashboard/js/main.js, and src/dashboard/js/api.js

**Checkpoint**: All four user stories (`US1`–`US4`) are complete and independently functional through the unified ISC Backend C2 facade.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Full in-process pipeline verification, Playwright E2E coverage, standalone validation scripts, Constitution Principle VI audit, and architecture review.

- [X] T046 [P] Write end-to-end in-process pipeline integration test (MQTT push -> Parquet flush -> DuckDB AAR + Threat Gate -> HITL Override -> Target Lineage) in tests/integration/test_pma_pipeline.py
- [X] T047 [P] Write Playwright UI E2E tests covering Threat map overlay, HITL mandatory override justification, AAR dashboard panel, and SMEAC Copilot draft-to-HITL flow in tests/e2e/pma_c2.spec.js
- [X] T048 [P] Create standalone stack verification and AAR latency benchmark script in scripts/verify_pma_stack.py
- [X] T049 Audit src/ for zero mocks/stubs/dummy tokens/simulation fallbacks (FR-013, SC-007), run .agents/agents/uservice-arch-reviewer architectural check, and execute offline hermetic test suite (pytest tests/unit tests/contract -v) per specs/005-pma-integration/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately (`T001` blocks runtime package installation in Docker/venv; `T002`–`T004` run in parallel).
- **Foundational (Phase 2)**: Depends on Setup (`T001`, `T004`) — **BLOCKS** all user story phases (`US1`–`US4`). `T005`–`T009` run in parallel; `T010` initializes test isolation once package layout & base clients exist.
- **User Story 1 (`P1` 🎯 MVP — Phase 3)**: Depends on Phase 2 completion. Delivers standalone push telemetry, DDIL SQLite spool, and Parquet archival.
- **User Story 2 (`P2` — Phase 4)**: Depends on Phase 2 completion (`T005`, `T007`, `T008`, `T010`). Can execute in parallel with or immediately after US1.
- **User Story 3 (`P3` — Phase 5)**: Depends on Phase 2 (`T006`, `T007`) and integrates edge/ingestor hooks from `US1` (`T016`, `T019`).
- **User Story 4 (`P4` — Phase 6)**: Depends on Phase 2 (`T006`, `T007`) and reads telemetry Parquet / threat entities produced by `US1`–`US3` schemas (hermetic tests remain independent).
- **Polish & Cross-Cutting (Phase 7)**: Depends on all desired user stories (`US1`–`US4`) completing.

### User Story Dependency Graph

```text
Phase 1 (Setup: T001-T004)
   └──► Phase 2 (Foundational: T005-T010)
           ├──► Phase 3 [US1]: Push MQTT + DDIL Spool + Parquet (T011-T021)  <── MVP Scope
           │       └──► Phase 5 [US3]: Vision Snapshots + Target Lineage (T032-T038)
           ├──► Phase 4 [US2]: Memgraph Threat Gating + HITL Override (T022-T031)
           └──► Phase 6 [US4]: DuckDB AAR + AI SMEAC Copilot (T039-T045)  [uses US1/US2/US3 schemas]
                   └──► Phase 7 (Polish, E2E & Compliance Audit: T046-T049)
```

### Within Each User Story

1. Write failing hermetic unit and contract tests FIRST (`T011`–`T013`, `T022`–`T024`, `T032`–`T033`, `T039`–`T040`).
2. Create Pydantic contract DTOs and storage structures (`[P]` tasks).
3. Implement operations & `DomainFacade` business logic (`src/uservice/<domain>/operations/` and `facade/`).
4. Expose FastAPI routes & Temporal/ingestor wiring (`api/`, `main.py`, `process.py`).
5. Update `src/dashboard/` strictly via ISC Backend REST API endpoints (`FR-008`).

---

## Parallel Execution Examples

### Parallel Example: Phase 2 (Foundational)
```bash
# All five foundational modules touch disjoint files and can execute concurrently:
Task: T005 - Extend ORM models (SwarmInstance, SmeacOrder, HitlDecision) in src/uservice/*/models/storage/
Task: T006 - Implement MinIO S3 client in src/uservice/analytics/operations/minio_store.py
Task: T007 - Implement async Memgraph Bolt client in src/uservice/threat/operations/graph_client.py
Task: T008 - Update proxy passthrough in src/uservice/security/proxy.py
Task: T009 - Purge legacy SIMULATION_MODE and dummy fallbacks across src/edge/, src/uservice/smeac/, and src/dashboard/js/api.js
```

### Parallel Example: User Story 1 (`US1`)
```bash
# Write all US1 hermetic test suites first in parallel:
Task: T011 - MQTT topic/QoS/LWT contract tests in tests/contract/test_mqtt_contract.py
Task: T012 - SQLite DDIL edge_spool eviction & replay unit tests in tests/unit/test_edge_spool.py
Task: T013 - PyArrow Parquet 5-15s compaction unit tests in tests/unit/test_telemetry_compactor.py

# Implement edge spool, contract DTOs, and live state store in parallel:
Task: T014 - SwarmTelemetryEvent DTOs in src/uservice/telemetry/models/contract/events.py
Task: T015 - SQLite edge_spool WAL buffer in src/edge/telemetry/spool.py
Task: T017 - Live telemetry projection & batch buffer in src/uservice/telemetry/models/storage/live_state.py
```

### Parallel Example: User Story 2 (`US2`)
```bash
# Write all US2 hermetic tests in parallel:
Task: T022 - Threat & HITL 422 REST contract tests in tests/contract/test_threat_and_hitl_contract.py
Task: T023 - Memgraph threat intersection & fallback tests in tests/unit/test_threat_gating.py
Task: T024 - Mandatory HITL justification unit tests in tests/unit/test_hitl_override.py

# Seed script and contract schemas can advance alongside threat facade wiring:
Task: T025 - Threat & HITL schemas in src/uservice/threat/models/contract/schemas.py and src/uservice/hitl/models/contract/schemas.py
Task: T030 - Standalone threat seeding script in scripts/seed_threats.py
```

### Parallel Example: User Story 3 (`US3`) & User Story 4 (`US4`)
```bash
# US3 tests & edge capture in parallel:
Task: T032 - Target correlation unit tests in tests/unit/test_target_correlator.py
Task: T033 - Target lineage & snapshot REST contract tests in tests/contract/test_target_lineage_contract.py
Task: T034 - Edge YOLO-E snapshot crop & MinIO upload in src/edge/vision/inference.py

# US4 DuckDB AAR tests & Copilot tests in parallel:
Task: T039 - DuckDB AAR unit tests in tests/unit/test_duckdb_aar.py
Task: T040 - SMEAC Copilot non-executing draft tests in tests/unit/test_smeac_copilot.py
Task: T041 - AAR & Copilot DTOs in src/uservice/analytics/models/contract/aar.py and src/uservice/smeac/models/contract/schemas.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete **Phase 1: Setup** (`T001`–`T004`) including `scan_dependencies` validation and unified `c2-shared-net` Compose wiring.
2. Complete **Phase 2: Foundational** (`T005`–`T010`) — critical database extensions, MinIO/Memgraph clients, Principle VI legacy simulation removal, and hermetic test harness.
3. Complete **Phase 3: User Story 1** (`T011`–`T021`).
4. **STOP & VALIDATE MVP**: Run `pytest tests/contract/test_mqtt_contract.py tests/unit/test_edge_spool.py tests/unit/test_telemetry_compactor.py -v`, then against `docker compose up -d` run [quickstart.md](./quickstart.md) Scenario A Steps 1–2, verify flushed Parquet files in MinIO bucket `tactical-telemetry`, and run Scenario E (Scenario A Step 3 `/api/v1/analytics/aar` activates in `US4`).

### Incremental Delivery

1. **MVP Increment (`US1`)**: Push MQTT telemetry, DDIL SQLite spool, 5–15s Parquet archival -> validate `SC-001`, `SC-002`.
2. **Safety Governance Increment (`US2`)**: Memgraph threat gating + manual deactivation + audited HITL override + deterministic fallback -> validate `SC-003`.
3. **ISR Lineage Increment (`US3`)**: Edge YOLO-E MinIO visual snapshots + automated cross-mission `TargetEntity` correlation -> validate `FR-007`.
4. **Decision Support Increment (`US4`)**: Sub-2s DuckDB AAR + non-executing SMEAC Copilot -> validate `SC-004`, `SC-005`.
5. **Release Hardening (`Phase 7`)**: In-process pipeline test, Playwright E2E suite, benchmark validation (`scripts/verify_pma_stack.py`), Principle VI purity audit, and `.agents/agents/uservice-arch-reviewer` review (`SC-006`, `SC-007`).

---

## Notes

- `[P]` marks parallelizable tasks touching disjoint files without unfinished blocking dependencies.
- `[US1]`–`[US4]` labels map exclusively to User Story phases for strict requirement traceability.
- **No mocks, stubs, or silent simulation fallbacks** are permitted inside `src/` (Constitution v1.2.0 Principle VI, `FR-013`). Test doubles remain strictly isolated inside `tests/`.
- Execute `scan_dependencies` before modifying `requirements.txt` during `T001`.
- Suggested MVP scope: **Phase 1 + Phase 2 + Phase 3 (`US1`, T001–T021)**.

---

## Phase 8: Convergence

- [X] T050 Align FlightController._navigation_loop, EdgeTelemetryPublisher.publish_detection, and assign_target to crop JPEG snapshots via crop_detection_jpeg and pass target_class, confidence, bbox, snapshot_bytes, and mission_id in src/edge/navigation/flight_controller.py, src/edge/telemetry/publisher.py, and src/edge/api/server.py per FR-007 (partial)
- [X] T051 Wire edge MAVSDK telemetry_loop to publish navigation and battery SwarmTelemetryEvent updates via _telemetry_publisher.publish_event in src/edge/api/server.py per FR-001 (partial)
- [X] T052 Accept and persist draft_source_refs from Copilot drafts onto SmeacOrder in src/uservice/smeac/models/contract/schemas.py, src/uservice/smeac/facade/smeac.py, and src/dashboard/js/main.js per FR-009 (partial)
