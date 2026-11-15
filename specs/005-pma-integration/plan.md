# Implementation Plan: Poor-Man's Artemis.IA (PMA) C4ISR Integration

**Branch**: `005-pma-integration` | **Date**: 2026-11-14 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/005-pma-integration/spec.md)
**Input**: Feature specification from `/specs/005-pma-integration/spec.md`

---

## Summary

Converge the 4-phase Poor-Man's Artemis.IA (PMA) C4ISR telemetry, archival lakehouse, spatial knowledge graph, and AI drafting stack into Intent-Swarm-Commander (ISC) on a single-host `c2-shared-net` Docker topology with shared Temporal queues (`isc-smeac-queue` and `pma-ingestion-queue`):
1. **Push MQTT Telemetry & Edge DDIL Resilience**: Replace synchronous HTTP drone telemetry polling with asynchronous `paho-mqtt` / `aiomqtt` publishing to Eclipse Mosquitto (`telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/{metric}`), backed by an embedded SQLite `edge_spool` implementing priority-aware eviction (evict oldest routine `navigation` frames before `detection`/`alert` records) and live-first + background backlog drain on reconnect.
2. **Micro-Batch Parquet Lakehouse & Sub-2s DuckDB AAR**: Buffer live MQTT streams in `src/uservice/telemetry/` and flush Apache Parquet partitions via PyArrow to MinIO (`tactical-telemetry`) every 5–15 seconds, exposing sub-2s DuckDB After Action Review queries (`src/uservice/analytics/`) through the unified ISC Backend C2 facade.
3. **Memgraph Threat Gating, Target Lineage & Audited HITL Override**: Add `src/uservice/threat/` backed by Memgraph Bolt (`:7687`) scoped by `project_id` (defaulting to `"default-theater"`). Active threats (manual deactivation only, zero TTL) gate `ProcessSmeacWorkflow` via `safety_check_activity`, routing intersections to `HitlFacade` where overrides require non-empty `rationale` justification (`422` otherwise). Correlate YOLO-E MinIO `tactical-snapshots` into cross-mission `TargetEntity` tracks via automated spatial-temporal+class openCypher queries with analyst review/override. When Memgraph or LLM services are unavailable, fail deterministically onto `config/restricted_zones.json` + explicit `degraded_mode: true` reporting.
4. **AI SMEAC Copilot & Constitution v1.2.0 Compliance**: Add read-only ADK / `pydantic-ai` SMEAC drafting (`POST /api/v1/smeac/draft`) returning non-executing `DRAFT` orders with source citations; eliminate legacy `SIMULATION_MODE` / dummy coordinate / placeholder LLM branches in `src/`; enforce strictly hermetic offline `pytest` verification in `tests/`.

---

## Technical Context

**Language/Version**: Python 3.12+ (target runtime Python 3.14 in existing dev container / `.venv`, Ruff `target-version = "py312"` per `pyproject.toml`), Vanilla ES6+ JavaScript / Leaflet (`src/dashboard/`)
**Primary Dependencies**:
- *Existing*: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `pydantic`, `pydantic-ai`, `temporalio`, `httpx`, `shapely`, `python-jose[cryptography]`, `docker`, `opentelemetry-api`
- *PMA Integration Additions (to be validated via `scan_dependencies` before code changes in `/speckit-implement`)*: `paho-mqtt` / `aiomqtt` (MQTT push/ingest), `pyarrow` (Parquet serialization), `duckdb` (in-process AAR OLAP engine), `boto3` (MinIO S3 snapshot & Parquet I/O), `neo4j` (async Bolt driver for Memgraph openCypher)
**Storage & Infrastructure**:
- PostgreSQL (`:5432` ISC transactional workflows & HITL audit; existing)
- Temporal.io (`:7233` gRPC / `:8233` UI, shared cluster, isolated `ISC_TASK_QUEUE="isc-smeac-queue"` & `PMA_TASK_QUEUE="pma-ingestion-queue"`)
- Eclipse Mosquitto (`:1883` MQTT broker on `c2-shared-net`)
- MinIO S3 (`:9000` S3 API / `:9001` Console, buckets `tactical-telemetry` & `tactical-snapshots`)
- Memgraph (`:7687` Bolt / `:3000` Lab, Spatial Knowledge Graph)
- Edge SQLite (`edge_spool` local WAL file for DDIL blackout buffering)
**Testing**: `pytest` (`asyncio_mode = "auto"` per `pyproject.toml`) for `tests/unit/`, `tests/contract/`, `tests/integration/`; Playwright (`playwright.config.js`) for `tests/e2e/` — all unit/contract suites strictly offline and hermetic (`FR-014`).
**Target Platform**: Linux single-host container deployment via Docker Compose (`c2-shared-net` bridge network) + Raspberry Pi 5 edge companion node (`src/edge/`).
**Project Type**: Unified web service + edge companion + vanilla JS tactical dashboard inside single repository.
**Performance Goals**:
- Edge MQTT telemetry publish latency `< 100ms`; Parquet visibility delay `5s–15s` (`PARQUET_FLUSH_INTERVAL_S`, default `10s`).
- DuckDB AAR query latency `< 2000ms` over 10k+ mission telemetry records (`SC-004`).
- Memgraph threat gate + route safety check `< 500ms` (`SC-003` SLA target); live MQTT reconnect prioritized ahead of backlog replay.
**Constraints**:
- Single C2 API boundary (`FR-008`): `src/dashboard/` calls only ISC Backend (`/api/v1/...`), never MinIO, Memgraph, DuckDB, or external PMA endpoints directly.
- Non-conflicting co-located single-host ports per `docs/analysis/compatibility_with_pma.md` (`5432` ISC DB, `7233`/`8233` Temporal, `1883` Mosquitto, `9000`/`9001` MinIO, `7687`/`3000` Memgraph, `8000` Backend, `8080` Dashboard, `8090` Edge).
- Constitution v1.2.0 Principle VI: Zero mocks, stubs, dummy payloads, or silent `SIMULATION_MODE` fallbacks inside `src/`.
**Scale/Scope**: Single-host C4ISR deployment supporting multi-drone tactical swarms (`project_id` theater isolation), ~2 Hz telemetry per active drone, near-real-time 5–15s micro-batch Parquet archival, and multi-mission target lineage.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle / Standard | Pre-Design Check | Post-Design Verification (`research.md`, `data-model.md`, `contracts/`) | Status |
|---|---|---|---|
| **I. Long Term Vision (LTV) & Inverted Cone** | Targets existing LTV Node Points `Verification_1_Constraint_Graph` and `Verification_2_Abductive_Logic_Gate` queried from `ltv_database.db`. | Threat knowledge graph (`src/uservice/threat/`) implements spatial constraint gating (`Verification_1`) and Policy-as-Code HITL verification before dispatch (`Verification_2`). | PASS |
| **II. Cynefin Domain Assessment** | Logged `PMA_C4ISR_Integration` as `Complicated` via `.agents/skills/cynefin-domain-assessor/scripts/assess_domain.py` prior to planning. | Full analytical backward design applied across telemetry, threat graph, analytics, and copilot subsystems appropriate for `Complicated` systems. | PASS |
| **III. OODA Loops for Iterative Validation** | Incremental OODA milestones bound to LTV node points planned (Telemetry bus -> Threat Gate -> Lineage -> Copilot). | Phase-by-phase validation scenarios encoded in `quickstart.md` Scenarios A–F tied to measurable hypotheses. | PASS |
| **IV. Guard Against False Cones** | Rejects `LLM_Self_Reflection_for_Verification` and `Agent_Discretion_for_Critical_Safety_Decisions`. | Safety gate uses deterministic Memgraph + Shapely checks (`safety_check_activity`), mandatory non-empty HITL justification (`422` guard), and non-executing `draft_only: true` Copilot (`FR-009`, `SC-005`). | PASS |
| **V. Script Organization in `scripts/`** | All helper/seeding scripts routed strictly to root `scripts/` (never project root or `src/`). | `scripts/seed_threats.py` (threat graph seeding) and `scripts/verify_pma_stack.py` (optional DuckDB SLA & stack check) placed exclusively under `scripts/`. | PASS |
| **VI. Production Code Purity & Test Isolation** | Audited legacy `SIMULATION_MODE` / dummy coordinate / placeholder LLM branches currently in `src/edge/` (`server.py`, `camera.py`, `inference.py`, `flight_controller.py`), `src/uservice/smeac/facade/smeac.py`, and `src/dashboard/js/api.js`. | Research R6 & design contracts remove silent simulation/fallback defaults from `src/`, mandate explicit `degraded_mode` status reporting (`FR-012`), and enforce strictly offline hermetic fixtures inside `tests/` (`FR-014`). | PASS |
| **Verification & Architecture Standards** | Follows `uservice-template` DDD domain structure (`api/`, `facade/`, `models/{api,contract,storage}`, `operations/`), cross-domain communication strictly via Facades, reviewed later via `.agents/agents/uservice-arch-reviewer`. | New domains (`telemetry`, `threat`, `analytics`) strictly isolate API routes, Facades (`DomainFacade`), Pydantic contracts, SQLAlchemy storage, and Temporal/ADK operations; Temporal bug in `HitlFacade` (`signal_input=` vs `arg=`) flagged for fix in implementation. | PASS |

*(Implementation gate reminder: invoke `scan_dependencies` before adding new libraries to `requirements.txt` during `/speckit-implement`.)*

---

## Project Structure

### Documentation (this feature)

```text
specs/005-pma-integration/
├── plan.md                      # This file (/speckit-plan output)
├── research.md                  # Phase 0 architectural & resilience decisions (R1-R6)
├── data-model.md                # Phase 1 PostgreSQL, SQLite spool, Parquet, MinIO & Memgraph schemas
├── quickstart.md                # Phase 1 end-to-end validation & hermetic test runbook
├── contracts/
│   ├── mqtt-telemetry.md        # Push MQTT topic hierarchy, QoS, LWT & DDIL replay contract
│   └── rest-api.md              # Unified ISC Backend REST C2 facade API contracts
├── checklists/
│   └── requirements.md          # Spec quality validation checklist
└── tasks.md                     # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
docker-compose.yml               # Unified single-host c2-shared-net bridge stack (Postgres, Temporal, Mosquitto, MinIO, Memgraph, Backend, Dashboard, Edge)
.env.example                     # Non-secret config template (MQTT, MinIO, Memgraph Bolt, CORRELATION_*, PARQUET_FLUSH_INTERVAL_S, TASK_QUEUE)
requirements.txt                 # Updated with security-scanned telemetry/lakehouse/graph dependencies

scripts/
├── seed_threats.py              # Standalone threat graph seeding utility for default-theater (Constitution Principle V)
└── verify_pma_stack.py          # Optional E2E smoke validation script against running compose stack

src/
├── edge/
│   ├── telemetry/               # [NEW] Edge push telemetry & DDIL buffering domain
│   │   ├── __init__.py
│   │   ├── publisher.py         # paho-mqtt async publisher + live-first reconnect hook + S3 snapshot uploader
│   │   └── spool.py             # SQLite edge_spool WAL buffer (priority=0 routine eviction, priority=1 preservation)
│   ├── api/
│   │   └── server.py            # [MODIFY] Remove simulated telemetry state; bind real edge loop + spool/health reporting
│   ├── navigation/
│   │   └── flight_controller.py # [MODIFY] Remove mock (0.0,0.0) defaults; emit real telemetry/alert events to EdgeTelemetryPublisher
│   └── vision/
│       ├── camera.py            # [MODIFY] Remove silent SIMULATION_MODE fallback inside production module
│       └── inference.py         # [MODIFY] Remove silent empty simulated inference branch; return bbox/crop for MinIO snapshot upload
│
├── uservice/
│   ├── main.py                  # [MODIFY] Register telemetry, threat & analytics routers + MQTT ingestor & Parquet compactor lifespan
│   ├── database/
│   │   └── engine.py            # [MODIFY] Register ORM model extensions & safe additive column setup
│   ├── security/
│   │   └── proxy.py             # [MODIFY] Pass through /threats, /analytics, /targets, /smeac/draft routes cleanly
│   ├── telemetry/               # [NEW] Push telemetry ingestion & Parquet micro-batch lakehouse domain
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   └── routes.py        # Telemetry health/backlog diagnostics
│   │   ├── facade/
│   │   │   └── telemetry.py     # TelemetryFacade (live MQTT state cache, idempotent ingest, swarm projection)
│   │   ├── models/
│   │   │   ├── contract/
│   │   │   │   └── events.py    # SwarmTelemetryEvent, TelemetryProjectionResponse DTOs
│   │   │   └── storage/
│   │   │       └── live_state.py# Thread/async-safe live projection + Parquet micro-batch memory buffer
│   │   └── operations/
│   │       ├── ingestor.py      # aiomqtt subscriber (telemetry/projects/+/swarms/+/+/+) -> live cache + Threat detection hook + Parquet buffer
│   │       └── compactor.py     # 5-15s PyArrow Parquet writer -> MinIO (tactical-telemetry) + failure retry queue
│   ├── threat/                  # [NEW] Memgraph spatial constraint & target lineage domain
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   └── routes.py        # /api/v1/threats CRUD/deactivate & /api/v1/targets lineage/review
│   │   ├── facade/
│   │   │   └── threat.py        # ThreatFacade (Memgraph openCypher + Shapely checks + deterministic fallback + target correlation)
│   │   ├── models/
│   │   │   └── contract/
│   │   │       └── schemas.py   # ThreatZoneCreate/Response/Deactivate, ThreatConflictDetail, TargetEntityLineage DTOs
│   │   └── operations/
│   │       ├── graph_client.py  # Async Memgraph Bolt client (neo4j driver) with explicit timeout & degraded error signaling
│   │       └── correlator.py    # Spatial-temporal+class TargetEntity matching & analyst split/confirm logic
│   ├── analytics/               # [NEW] DuckDB AAR & MinIO snapshot proxy domain
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   └── routes.py        # GET /api/v1/analytics/aar & GET /api/v1/analytics/detections/{event_id}/snapshot
│   │   ├── facade/
│   │   │   └── analytics.py     # AnalyticsFacade (enforces project_id scoping, coordinates DuckDB & MinIO fetches)
│   │   ├── models/
│   │   │   └── contract/
│   │   │       └── aar.py       # AarQueryRequest, AarQueryResponse, DetectionSnapshotMetadata DTOs
│   │   └── operations/
│   │       ├── duckdb_runner.py # Embedded DuckDB S3/Parquet query runner (<2s SLO)
│   │       └── minio_store.py   # boto3 S3 wrapper for tactical-telemetry & tactical-snapshots
│   ├── smeac/
│   │   ├── api/routes.py        # [MODIFY] Add POST /api/v1/smeac/draft Copilot route
│   │   ├── facade/smeac.py      # [MODIFY] Bind project_id, invoke SMEAC Copilot safely, remove silent placeholder geo fallback
│   │   ├── models/
│   │   │   ├── contract/schemas.py # [MODIFY] Add SmeacDraftRequest/Response, threat_check_mode, degraded_reason
│   │   │   └── storage/smeac.py # [MODIFY] Add project_id, threat_check_mode, degraded_reason, draft_source_refs
│   │   └── operations/
│   │       ├── copilot.py       # [NEW] Read-only ADK/pydantic-ai SMEAC Copilot with Threat/Analytics/Swarm tools (draft_only=True)
│   │       ├── safety_activity.py # [MODIFY] Evaluate ThreatFacade + static baseline fallback; propagate threat_conflicts & degraded_mode
│   │       └── process.py       # [MODIFY] Route threat intersections & degraded-fallback high-risk checks to HITL gate
│   ├── hitl/
│   │   ├── api/routes.py        # [MODIFY] Enforce non-empty rationale on threat overrides; expose threat_conflicts in /pending
│   │   ├── facade/hitl.py       # [MODIFY] Store override flags, validate mandatory justification (422), fix signal_workflow(arg=) bug
│   │   └── models/storage/decision.py # [MODIFY] Add project_id, is_threat_override, threat_zone_ids, override_justification
│   └── swarm/
│       ├── api/routes.py        # [MODIFY] Switch GET /swarms/{id}/telemetry from synchronous HTTP poll to TelemetryFacade live cache
│       └── models/storage/instance.py # [MODIFY] Add project_id (default "default-theater")
│
└── dashboard/                   # Tactical Dashboard (communicates strictly via ISC Backend REST API)
    ├── index.html               # [MODIFY] Add Threat Layer panel, AAR & Target Lineage viewer, SMEAC Copilot "Draft with AI" action, Degraded Banner
    └── js/
        ├── api.js               # [MODIFY] Remove synthetic (52.52, 13.405) telemetry normalization; add /threats, /analytics, /targets, /smeac/draft calls
        ├── map.js               # [MODIFY] Render Memgraph ThreatZone polygons/circles & TargetEntity/DetectionEvent markers + snapshot modal
        ├── hitl.js              # [MODIFY] Display threat_conflicts & require override justification before Approve submission
        └── main.js              # [MODIFY] Wire Copilot non-executing draft -> form populate workflow + Degraded service banner

tests/
├── conftest.py                  # [NEW/UPDATE] Global socket/LLM hermetic guard & offline fake dependencies for unit/contract tests
├── unit/
│   ├── test_edge_spool.py       # SQLite DDIL buffer capacity eviction & live-first replay order
│   ├── test_telemetry_compactor.py # 5-15s PyArrow Parquet compaction, deduplication & project isolation
│   ├── test_threat_gating.py    # Spatial openCypher/Shapely threat check, manual deactivation & deterministic fallback
│   ├── test_target_correlator.py# Spatial-temporal+class correlation & manual confirm/split
│   ├── test_duckdb_aar.py       # PyArrow Parquet + DuckDB sub-2s AAR query correctness on temp files
│   ├── test_smeac_copilot.py    # Non-executing draft contract, citations & degraded fallback
│   └── test_hitl_override.py    # Mandatory rationale validation & signal_workflow invocation
├── contract/
│   ├── test_mqtt_contract.py    # Topic hierarchy, QoS 0 vs 1 mapping, SwarmTelemetryEvent validation
│   ├── test_threat_and_hitl_contract.py # FastAPI TestClient contracts for /threats and HITL 422 enforcement
│   └── test_target_lineage_contract.py  # FastAPI TestClient contracts for /targets and /snapshot proxy
├── integration/
│   └── test_pma_pipeline.py     # In-process end-to-end integration (Ingestor -> Parquet/DuckDB + Threat Gate -> HITL Override)
└── e2e/
    └── pma_c2.spec.js           # Playwright UI tests covering Threat map overlay, HITL justification modal, AAR panel, Copilot Draft
```

**Structure Decision**: Retain ISC's cohesive single-repository Python `src/uservice/` + `src/edge/` + `src/dashboard/` layout while introducing three strictly decoupled `uservice-template` domain packages (`telemetry`, `threat`, `analytics`) alongside targeted extensions to `smeac`, `hitl`, and `swarm`. All new operational helper scripts belong under root `scripts/`, and all tests under `tests/` remain network-isolated during CI unit/contract execution.

---

## Complexity Tracking

> Justifications for architectural additions and Compose topology shifts beyond basic single-container CRUD.

| Violation / Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Three infrastructure containers added to `docker-compose.yml` (`mosquitto`, `minio`, `memgraph`) | Satisfies C4ISR Phases 1–3 (`FR-001`, `FR-002`, `FR-003`, `FR-005`, `FR-006`, `FR-007`): high-throughput MQTT telemetry bus, partitioned Parquet + visual snapshot object store, and spatial property graph. | Multiplexing all telemetry, binary frames, and multi-hop target lineage into PostgreSQL alone violates `SC-004` (`<2s` columnar AAR isolation) and diverges from PMA integration architecture (`docs/analysis/compatibility_with_pma.md`). |
| Migrating `docker-compose.yml` off `network_mode: host` onto bridge `c2-shared-net` (with shared Temporal & explicit queues) | Required so containers resolve internal DNS names (`mosquitto`, `minio`, `memgraph`, `postgres`, `temporal`) without port collision against PMA services while sharing one Temporal engine (`ISC_TASK_QUEUE` vs `PMA_TASK_QUEUE`). | Running separate Temporal servers wastes single-host RAM and collides on port `7233`/`8233`; keeping `host` mode prevents clean container DNS isolation and risks browser bypass of `FR-008`. |
| Embedded SQLite DDIL spool (`src/edge/telemetry/spool.py`) instead of JSONL append log | Required by clarified `FR-012` eviction priority: must delete oldest routine `navigation` rows first while keeping high-priority `detection`/`alert` records and resuming live telemetry ahead of backlog drain. | Append-only `/tmp/edge_buffer.jsonl` cannot selectively evict low-priority middle/head records atomically under Pi 5 power loss without full-file rewrites. |
