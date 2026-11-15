# Implementation Plan: Enforce Single-Path Success Logic & Remove Fallbacks

**Branch**: `006-remove-fallback-logic` | **Date**: 2026-11-15 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/006-remove-fallback-logic/spec.md)  
**Input**: Feature specification from `/home/remi/Projects/Intent-Swarm-Commander/specs/006-remove-fallback-logic/spec.md`

---

## Summary

Eliminate every dual-path library import fallback (`try...except ImportError`, `*_AVAILABLE` flags, pure-Python ray-casting, custom `PAR1ISCC` Parquet encoding, `sqlite_olap` AAR engine, `PIL.Image` crop fallback, and `_ensure_aiosqlite_shim` in `tests/conftest.py`) and every runtime service/configuration fallback (`config/restricted_zones.json` static threat evaluation, LLM `"placeholder_key"` / regex / template synthesis fallbacks, multi-host Temporal retry loop, `"dev_passphrase"` fallback, silent catch-and-log suppression, and `degraded_mode` / `503` degraded responses) across `src/` and `tests/`. Declare and install real wheels for all dependencies (including `shapely`, `duckdb`, `pyarrow`, `aiomqtt`, `neo4j`, `paho-mqtt`, `opencv-python-headless`, `ultralytics`, `mavsdk`, `aiosqlite`, `google-genai`, and pinned `opentelemetry-api>=1.27,<1.34`), surface upstream infrastructure failures directly as `HTTP 500 Internal Server Error`, strip degraded banners/fields from API schemas, ORM storage, and dashboard UI, while preserving `EdgeSpool` SQLite WAL DDIL buffering as an intentional tactical domain queue.

---

## Technical Context

**Language/Version**: Python `>=3.12` (verified runtime environment `.venv` running Python `3.14.4`), vanilla ES6 JavaScript & HTML5 (`src/dashboard/`)  
**Primary Dependencies**: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `pydantic`, `pydantic-ai`, `google-genai`, `temporalio`, `shapely`, `paho-mqtt`, `aiomqtt`, `pyarrow`, `duckdb`, `boto3`, `neo4j`, `opencv-python-headless`, `ultralytics`, `mavsdk`, `opentelemetry-api>=1.27,<1.34`, `aiosqlite` (test DB)  
**Storage**: PostgreSQL (primary `uservice` ORM via SQLAlchemy), Memgraph (Bolt via `neo4j`), MinIO (S3 via `boto3`), DuckDB over standard Apache Parquet (`PAR1` via `pyarrow.parquet`), local SQLite WAL (`EdgeSpool` DDIL queue only; `aiosqlite` for hermetic test ORM)  
**Testing**: `pytest` & `pytest-asyncio` with hermetic in-memory/local test doubles inside `tests/conftest.py` (using real `aiosqlite`, `shapely`, `pyarrow`, `duckdb` wheels instead of stubs)  
**Target Platform**: Linux microservice control plane (`src/uservice/`) + Linux/Raspberry Pi Edge nodes (`src/edge/`) + Web Tactical C2 Dashboard (`src/dashboard/`)  
**Project Type**: Multi-service web application + Temporal workflow engine + Edge UAV node runtime  
**Performance Goals**: Zero secondary engine overhead; DuckDB analytical queries run natively over `pyarrow` `PAR1` Parquet artifacts; live Memgraph Cypher + Shapely geometry threat evaluation  
**Constraints**: Zero `*_AVAILABLE` flags or `except ImportError` branches in `src/` and `tests/conftest.py`; zero `degraded_mode` / `fallback_static_zones` / `threat_check_mode` fallback fields; upstream failures propagate cleanly (`HTTP 500`); `EdgeSpool` DDIL queue preserved cleanly (FR-004)  
**Scale/Scope**: Full refactoring across `requirements.txt`, `pyproject.toml`, `tests/conftest.py`, 27 backend files (`src/uservice/`), 5 Edge files (`src/edge/`), 5 dashboard files (`src/dashboard/`), and 8 test/verification suites (`tests/`, `scripts/`).

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Constitution Version**: `v1.3.0` (`Ratified 2026-07-24`, `Last Amended 2026-11-15`)
- **Pre-Flight Domain & Vision Gates (`.agents/AGENTS.md`)**:
  - `VERSION` checked (`0.2.0`).
  - Cynefin Domain Assessor logged `Single_Path_Success_Refactoring` → `Complicated` in `ltv_database.db`.
  - False Cone Detector logged `Conditional_Library_And_Runtime_Fallbacks` in `ltv_database.db`.

| Constitution Gate | Pre-Design Status | Post-Design Status | Assessment / Plan Compliance |
|---|---|---|---|
| **Principles I–V** (`uservice` Domain Boundaries, API Envelopes, Safety/HITL Gates, Operational Hygiene) | PASS | PASS | Domain facades (`SwarmFacade`, `ThreatFacade`, `SmeacFacade`, `HitlFacade`, `AnalyticsFacade`, `TelemetryFacade`) and API routers remain intact; mandatory safety/HITL threat gating can no longer be bypassed or downgraded to static rules. |
| **Principle VI** (Hermetic Test Doubles Restricted to `tests/`) | PASS | PASS | All network service test doubles remain strictly in `tests/conftest.py`; additionally removes `_ensure_aiosqlite_shim()` from `tests/conftest.py` so DB tests run on the real `aiosqlite` wheel. |
| **Principle VII** (*Single-Path Success Logic (No Conditional Library Imports or Fallbacks)*) | PASS (Target Objective) | PASS | Eliminates all `try...except ImportError`, `*_AVAILABLE` flags, pure-Python/SQLite/PIL/PAR1ISCC alternate algorithms, static JSON threat fallbacks, LLM placeholder/template/regex fallbacks, Temporal retry loop, `"dev_passphrase"`, and `degraded_mode` / `503` degraded masking. |
| **Single-Path Verification Standard** | PASS | PASS | Verification plan (`quickstart.md`) enforces real wheel imports, zero-hit static `grep` audits for banned fallback patterns, preservation check for `EdgeSpool`, and full `pytest` verification including `HTTP 500` propagation tests. |

---

## Project Structure

### Documentation (this feature)

```text
specs/006-remove-fallback-logic/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output (R1–R6 technical decisions & .venv audit)
├── data-model.md        # Phase 1 output (ORM, DTO & artifact format changes)
├── quickstart.md        # Phase 1 output (import, grep purity & pytest checks)
└── contracts/
    └── rest-api.md      # Phase 1 output (HTTP 500 & degraded field removal contracts)
```

### Source & Test Files Scheduled for Modification

```text
requirements.txt                                          # Unconditional runtime + Edge + test dependencies; pinned opentelemetry-api
pyproject.toml                                            # Synchronized unconditional dependency declarations
tests/conftest.py                                         # Remove _ensure_aiosqlite_shim(); keep service doubles only

src/edge/
├── api/server.py                                         # Unconditional mavsdk import (remove MAVSDK_AVAILABLE)
├── navigation/flight_controller.py                       # Unconditional mavsdk import (remove MAVSDK_AVAILABLE)
├── vision/camera.py                                      # Unconditional cv2 import (remove OPENCV_AVAILABLE)
├── vision/inference.py                                   # Unconditional ultralytics + cv2 crop (remove YOLO_AVAILABLE & PIL fallback)
└── telemetry/publisher.py                                # Unconditional paho.mqtt.client (remove PAHO_AVAILABLE; RETAIN EdgeSpool)

src/uservice/
├── main.py                                               # Remove degraded lifespan/detection catches; centralize HTTP 500 handling if needed
├── base/agent.py                                         # Remove "placeholder_key" assignment; require real Gemini key on run
├── security/routes.py                                    # Remove "dev_passphrase" / {"dev_passphrase", "dev-passphrase"} fallback
├── operation/facade.py                                   # Remove Temporal multi-host fallback list in get_temporal_client
├── swarm/operations/swarm_agents.py                      # Unconditional shapely import; remove SHAPELY_AVAILABLE, _point_in_ring, JSON fallback
├── telemetry/
│   ├── operations/compactor.py                           # Unconditional pyarrow Parquet PAR1 (remove PYARROW_AVAILABLE & PAR1ISCC)
│   ├── operations/ingestor.py                            # Unconditional aiomqtt import (remove AIOMQTT_AVAILABLE)
│   ├── facade/telemetry.py                               # Remove degraded telemetry fallback emission
│   ├── models/storage/live_state.py                      # Remove "degraded_unavailable" return state
│   └── models/contract/events.py                         # Remove degraded_mode & "degraded_unavailable" literal
├── analytics/
│   ├── operations/duckdb_runner.py                       # Unconditional duckdb engine (remove DUCKDB_AVAILABLE, sqlite_olap, PAR1ISCC)
│   ├── models/contract/aar.py                            # Change AarQueryResponse.engine default from "sqlite_olap" to "duckdb"
│   └── api/routes.py                                     # Remove meta.degraded_mode and 503 degraded catches; surface HTTP 500
├── threat/
│   ├── operations/graph_client.py                        # Unconditional neo4j import in _get_driver() (remove NEO4J_AVAILABLE)
│   ├── facade/threat.py                                  # Remove _point_in_ring, static JSON helpers, and Memgraph fallback paths
│   ├── models/contract/schemas.py                        # Remove fallback_static_zones, threat_check_mode, degraded_mode, degraded_reason
│   └── api/routes.py                                     # Remove list_threats_with_meta degraded wrapper & 503 catches; surface HTTP 500
├── smeac/
│   ├── facade/smeac.py                                   # Remove LLM/regex/Temporal/MinIO/Memgraph fallbacks & degraded tracking
│   ├── operations/copilot.py                             # Remove template fallback, "static_baseline", *_degraded & degraded_reasons
│   ├── operations/safety_activity.py                     # Remove threat_check_mode & degraded_mode payload fields
│   ├── operations/process.py                             # Remove threat_check_mode & degraded_mode branching
│   ├── models/contract/schemas.py                        # Remove degraded/fallback fields & "static_baseline" source_type
│   ├── models/storage/smeac.py                           # Drop threat_check_mode & degraded_reason ORM columns
│   └── api/routes.py                                     # Remove degraded meta wrappers; surface HTTP 500 on upstream failures
└── hitl/
    ├── facade/hitl.py                                    # Propagate Memgraph/Temporal errors cleanly; drop degraded fields
    ├── models/contract/schemas.py                        # Remove threat_check_mode & degraded_reason from HitlPendingItem
    ├── models/storage/decision.py                        # Drop threat_check_mode & degraded_reason ORM columns
    └── api/routes.py                                     # Propagate HitlFacade upstream exceptions cleanly as HTTP 500

src/dashboard/
├── index.html                                            # Remove #degraded-banner element
└── js/
    ├── api.js                                            # Remove updateDegradedBanner() and fallback_static_zones handling
    ├── main.js                                           # Remove fallback_static_zones argument & threat_check_mode status text
    ├── map.js                                            # Remove fallbackStaticZones rendering path from renderThreatZones
    └── hitl.js                                           # Remove deterministic_fallback warning block in showHitlModal

tests/ & scripts/
├── tests/unit/test_threat_gating.py                      # Assert live Memgraph gating & error propagation (remove fallback expectations)
├── tests/contract/test_threat_and_hitl_contract.py       # Remove degraded_mode/fallback assertions; assert HTTP 500 on outages
├── tests/unit/test_smeac_copilot.py                      # Assert LLM/upstream error propagation (remove template fallback expectations)
├── tests/unit/test_telemetry_compactor.py                # Assert pyarrow PAR1 output strictly (remove PAR1ISCC assertions)
├── tests/unit/test_duckdb_aar.py                         # Assert duckdb engine strictly (remove sqlite_olap assertions)
├── tests/integration/test_e2e.py                         # Supply required env passphrase/keys & assert single-path contracts
├── tests/integration/test_pma_pipeline.py                # Supply required env & assert Parquet/DuckDB/Memgraph single-path flow
└── scripts/verify_pma_stack.py                           # Update verification assertions for HTTP 500 / single-path contracts
```

**Structure Decision**: Retain the existing modular domain structure (`src/uservice/<domain>/{api,facade,models,operations}`, `src/edge/`, `src/dashboard/`). All refactoring removes alternate code paths in-place without introducing new abstraction layers or shims.

---

## Phased Execution Strategy

1. **Phase 1 — Dependency Manifest & `.venv` Synchronization**: Update `requirements.txt` and `pyproject.toml`, install all missing wheels (`shapely`, `duckdb`, `pyarrow`, `aiomqtt`, `neo4j`, `paho-mqtt`, `opencv-python-headless`, `ultralytics`, `mavsdk`, `aiosqlite`) and align `opentelemetry-api>=1.27,<1.34`, then remove `_ensure_aiosqlite_shim()` from `tests/conftest.py`.
2. **Phase 2 — Single-Engine Edge & Backend Library Consolidation**: Replace all `*_AVAILABLE` / `try...except ImportError` guards and custom algorithms (`_point_in_ring`, `PAR1ISCC`, `sqlite_olap`, `PIL` crop) with unconditional library imports while preserving `EdgeSpool` DDIL spooling.
3. **Phase 3 — Runtime Fallback Elimination & Schema/API/UI Cleanup**: Remove static threat JSON fallbacks, LLM placeholder/regex/template fallbacks, Temporal multi-host retries, `"dev_passphrase"` default, degraded schema/ORM fields, dashboard degraded banners, and `503` degraded catches so infrastructure outages raise `HTTP 500`.
4. **Phase 4 — Test Suite Alignment & Static Purity Verification**: Update affected unit, contract, integration, and verification scripts, run `grep` static audits (`quickstart.md`), and verify the complete suite under `.venv/bin/pytest`.

---

## Complexity Tracking

No Constitution violations or complexity waivers are requested. This plan reduces cyclomatic complexity across all subsystems by deleting secondary code paths.
