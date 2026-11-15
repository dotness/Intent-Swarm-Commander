# Research & Technical Decisions: 006-remove-fallback-logic

**Feature**: Enforce Single-Path Success Logic & Remove Fallbacks (`006-remove-fallback-logic`)  
**Date**: 2026-11-15  
**Constitution**: v1.3.0 (Principles I–VII)  
**Cynefin Domain Assessment**: `Single_Path_Success_Refactoring` → `Complicated` (logged in `ltv_database.db`; justifies deterministic backward planning from TO-BE vision `Intent Driven Swarm Commander`)  
**False Cone Check**: `Conditional_Library_And_Runtime_Fallbacks` logged and rejected in `ltv_database.db` (dual-path library shims and degraded fallbacks eliminated).

---

## R1. Unconditional Dependencies, `.venv` Wheel Synchronization & Test Harness Purity

### Decision
Declare and install real wheels for **all** runtime, Edge, and test database packages in `requirements.txt` and `pyproject.toml`, remove `try...except ImportError` guards and `*_AVAILABLE` flags across `src/`, and remove `_ensure_aiosqlite_shim()` from `tests/conftest.py`.

### Verified Current Gap in `.venv` (Python 3.14.4)
- **Installed**: `boto3==1.43.56`, `google-genai==2.14.0`, `pydantic-ai==0.8.1`, `fastapi==0.140.0`, `pytest==9.1.1`, `opentelemetry-api==1.44.0`.
- **Missing**: `shapely`, `duckdb`, `pyarrow`, `aiomqtt`, `neo4j`, `paho-mqtt`, `mavsdk`, `opencv-python-headless`, `ultralytics`, `aiosqlite`.
- **Dependency conflict observed**: Importing `pydantic_ai` in `.venv` currently raises `ModuleNotFoundError: No module named 'opentelemetry._events'` because `.venv` has `opentelemetry-api==1.44.0`, whereas `requirements.txt` specifies `opentelemetry-api>=1.27,<1.34` (`pydantic-ai==0.8.1` relies on the `<1.34` module surface).
- **`requirements.txt` Edge entries**: `opencv-python-headless>=4.9,<5`, `ultralytics>=8.2,<9`, and `mavsdk>=2.0,<3` are currently commented out on lines 22–25 and absent from `pyproject.toml`.

### Implementation Consequence
1. Promote `opencv-python-headless`, `ultralytics`, and `mavsdk` to unconditional dependencies in `requirements.txt` and `pyproject.toml`; include `aiosqlite` for async SQLite test execution (under dev/test or runtime dependencies as appropriate) and keep `google-genai` declared alongside `pydantic-ai`.
2. Synchronize `.venv` with the pinned dependency bounds (`opentelemetry-api>=1.27,<1.34`, plus all missing wheels verified via direct `python -c "import ..."` checks).
3. Delete `_ensure_aiosqlite_shim()` from `tests/conftest.py` so tests bind directly to the real `aiosqlite` wheel. Keep in-memory/local test doubles for external networked brokers/stores (MQTT/S3/Memgraph) strictly inside `tests/conftest.py` per Constitution Principle VI, without any module-import fallback shims.

### Alternatives Considered & Rejected
- *Keeping Edge dependencies commented out with `*_AVAILABLE` flags*: Violates Constitution Principle VII and `spec.md` Q2 (`Option B`).
- *Retaining `_ensure_aiosqlite_shim()` as a backup*: Masks broken virtual environments instead of failing fast on missing wheels.

---

## R2. Single-Engine Geospatial, Parquet Compaction, DuckDB OLAP & MQTT/Graph Clients

### Decision
Eliminate all secondary algorithmic reimplementations and conditional client branches so every backend subsystem executes a single production path:

1. **Swarm Geospatial (`src/uservice/swarm/operations/swarm_agents.py`)**:
   - Remove `try...except ImportError` and `SHAPELY_AVAILABLE`.
   - Import `Point` and `shape` from `shapely.geometry` unconditionally at module top level.
   - Delete custom ray-casting `_point_in_ring` and dual branching in `_polygon_contains`.
   - Remove any static `config/restricted_zones.json` fallback geofencing path in favor of live geospatial/threat validation.
2. **Telemetry Compactor (`src/uservice/telemetry/operations/compactor.py`)**:
   - Remove `PYARROW_AVAILABLE`, `_ISC_COL_HEADER = b"PAR1ISCC"`, `_ISC_COL_FOOTER = b"PAR1"`, and custom binary columnar fallback encoding.
   - Import `pyarrow` and `pyarrow.parquet` unconditionally; emit standard Apache Parquet (`PAR1`) artifacts only.
3. **DuckDB AAR Engine (`src/uservice/analytics/operations/duckdb_runner.py`, `src/uservice/analytics/models/contract/aar.py`)**:
   - Remove `DUCKDB_AVAILABLE`, `"sqlite_olap"` fallback execution, and `blob.startswith(b"PAR1ISCC")` custom header parsing.
   - Import `duckdb` unconditionally and query standard Parquet artifacts directly via DuckDB.
   - Change `AarQueryResponse.engine` default from `"sqlite_olap"` to `"duckdb"`.
4. **Telemetry Ingestor (`src/uservice/telemetry/operations/ingestor.py`)**:
   - Remove `AIOMQTT_AVAILABLE` guard; import `aiomqtt` directly so `_subscribe_loop` runs unconditionally and surfaces broker/subscription errors directly.
5. **Property Graph Client (`src/uservice/threat/operations/graph_client.py`)**:
   - Remove `NEO4J_AVAILABLE` check in `_get_driver()`; import `neo4j` unconditionally so Memgraph Bolt connections require the real driver and raise `MemgraphUnavailableError` directly on failure.

### Alternatives Considered & Rejected
- *Dual-format `PAR1` / `PAR1ISCC` reader compatibility*: Rejected under `spec.md` FR-004/Q1 to prevent orphaned fallback code paths; Parquet files are standard `PAR1` exclusively.

---

## R3. Edge Vision, Autopilot & MQTT Publisher Single-Path (Preserving `EdgeSpool`)

### Decision
Enforce unconditional imports across all `src/edge/` modules while strictly distinguishing **prohibited library/mode fallbacks** from **tactical domain DDIL queueing (`EdgeSpool`)**:

1. **MAVSDK Flight Control (`src/edge/api/server.py`, `src/edge/navigation/flight_controller.py`)**:
   - Remove `MAVSDK_AVAILABLE` (`try...except ImportError`) and mock/bypass execution paths when `mavsdk` is absent; import `mavsdk` unconditionally.
2. **OpenCV Camera Capture (`src/edge/vision/camera.py`)**:
   - Remove `OPENCV_AVAILABLE` (`try...except ImportError`); import `cv2` unconditionally for capture and frame encoding.
3. **YOLOE Inference & ROI Crop (`src/edge/vision/inference.py`)**:
   - Remove `YOLO_AVAILABLE` (`try...except ImportError`) and remove the `PIL.Image` fallback inside `crop_detection_jpeg`; use `ultralytics` and `cv2` unconditionally.
4. **Edge Telemetry Publisher & `EdgeSpool` (`src/edge/telemetry/publisher.py`)**:
   - Remove `PAHO_AVAILABLE` (`try...except ImportError`) and any non-Paho bypass branch; import `paho.mqtt.client` unconditionally.
   - **Retained Tactical Capability (`EdgeSpool`)**: Preserve `EdgeSpool` SQLite WAL DDIL store-and-forward buffering (FR-004). Offline MQTT broker link drops buffer outbound telemetry in `EdgeSpool` and flush on reconnect as intentional tactical behavior — not a library or degraded API mode fallback.

### Rationale
Tactical UAV edge nodes operating in Disconnected, Denied, Intermittent, or Limited (DDIL) RF environments require `EdgeSpool` buffering by domain specification (`005-pma-integration`), whereas silent library import fallbacks mask incomplete edge deployments.

---

## R4. Single-Path Memgraph Evaluation, HTTP `500` Propagation & Degraded Schema/UI Removal

### Decision
Remove static threat baselines, degraded response flags, and `503` degraded catches across Memgraph/MinIO boundaries, failing fast with **HTTP `500 Internal Server Error`**:

1. **Threat Facade (`src/uservice/threat/facade/threat.py`)**:
   - Delete `_point_in_ring`, non-Shapely `_polygon_contains`, `load_static_restricted_zones()`, `_evaluate_static_zones()`, and every `except MemgraphUnavailableError` fallback returning `degraded_mode=True` or `threat_check_mode="deterministic_fallback"`.
   - All threat lookups and route evaluations execute solely against Memgraph (`MemgraphUnavailableError` propagates cleanly).
2. **Telemetry Availability (`src/uservice/telemetry/facade/telemetry.py`, `src/uservice/telemetry/models/storage/live_state.py`, `src/uservice/telemetry/models/contract/events.py`)**:
   - Remove `degraded_mode` from `TelemetryProjectionResponse` and remove `"degraded_unavailable"` from `telemetry_source` (`Literal["mqtt_live", "mqtt_stale"]`).
   - Update `LiveTelemetryStore.get_swarm_drones` / `TelemetryFacade.get_swarm_telemetry_projection` so missing live/stale MQTT telemetry does not emit `"degraded_unavailable"` or `degraded_mode=True` (either return live/stale projection when populated or raise an infrastructure error propagating as `500` when the telemetry pipeline is unavailable).
3. **FastAPI Route & Lifespan Error Propagation (`routes.py`, `src/uservice/main.py`)**:
   - Remove `503` fallback catches and `meta={"degraded_mode": ...}` wrappers from `src/uservice/threat/api/routes.py` (`list_threats_with_meta` simplified to direct Memgraph queries without `fallback_static_zones`), `src/uservice/analytics/api/routes.py`, and `src/uservice/smeac/api/routes.py`.
   - Remove `except MinioUnavailableError` and `except MemgraphUnavailableError` `"continuing degraded"` catches in `src/uservice/main.py` (`lifespan` and `_handle_detection`) so dependency outages fail fast on startup or surface directly.
   - **ASGI HTTP `500` Consistency Note**: In FastAPI/Starlette, unhandled `Exception` subclasses trigger HTTP `500` under `ServerErrorMiddleware` in live ASGI serving, whereas `httpx.ASGITransport(app=app)` defaults to `raise_app_exceptions=True` in tests. Converting upstream infrastructure failures (`MemgraphUnavailableError`, `MinioUnavailableError`, unhandled service `RuntimeError`/`TimeoutError`) via explicit `HTTPException(status_code=500, detail=str(exc))` or a centralized FastAPI app exception handler returning JSON HTTP `500` guarantees deterministic HTTP `500` status codes in both production ASGI servers and hermetic `httpx` tests (preserving `401`/`403`/`404`/`422` domain/auth/validation codes).
4. **Dashboard Degraded UI Cleanup (`src/dashboard/`)**:
   - `src/dashboard/index.html`: Remove `#degraded-banner`.
   - `src/dashboard/js/api.js`: Remove `updateDegradedBanner()`, all calls to it (`submitSmeac`, `fetchThreats`, `fetchAar`, `draftSmeacWithCopilot`), and `fallback_static_zones` fields/returns.
   - `src/dashboard/js/main.js`: Remove `threatRes.fallback_static_zones` argument and `(result.threat_check_mode || "full_graph")` suffix in submission status rendering.
   - `src/dashboard/js/map.js`: Remove `fallbackStaticZones` parameter and rendering loop from `renderThreatZones`.
   - `src/dashboard/js/hitl.js`: Remove `decision.threat_check_mode === 'deterministic_fallback'` UI warning block in `showHitlModal`.

---

## R5. Single-Path AI SMEAC Translation, Copilot & HITL Error Propagation

### Decision
Eliminate placeholder keys, regex/template synthesis fallbacks, and silent exception swallowing in agent, SMEAC, copilot, and HITL flows:

1. **Agent Initialization (`src/uservice/base/agent.py`, `src/uservice/smeac/operations/smeac_agents.py`)**:
   - Remove the `os.environ["GOOGLE_API_KEY"] = "placeholder_key"` fallback in `create_agent()`.
   - Require valid `GEMINI_API_KEY` / `GOOGLE_API_KEY` without substituting fake credentials. To ensure unrelated module imports (e.g., health/telemetry/unit tests that do not execute an LLM run) remain cleanly importable while strictly enforcing live credentials on agent creation/execution, construct the agent on demand or validate key presence without injecting `"placeholder_key"`.
2. **SMEAC Facade & Safety Workflows (`src/uservice/smeac/facade/smeac.py`, `safety_activity.py`, `process.py`)**:
   - Remove the `GEMINI_API_KEY`-missing fallback branch and deterministic regex coordinate fallback (`if not formatted_cmds:`) when parsing SMEAC orders.
   - Remove `try/except` fallback swallowing around Temporal `start_workflow` and `try/except MinioUnavailableError` / `MemgraphUnavailableError` in `generate_smeac_draft`.
   - Remove `threat_check_mode`, `degraded_mode`, and `degraded_reason` tracking from facade methods, Temporal safety activities/workflows, and ORM/Pydantic schemas.
3. **SMEAC Copilot (`src/uservice/smeac/operations/copilot.py`, `src/uservice/smeac/models/contract/schemas.py`)**:
   - Remove deterministic template fallback when `GEMINI_API_KEY` is missing or the LLM fails.
   - Remove `graph_degraded`, `aar_degraded`, `llm_degraded`, `degraded_reasons`, and `"static_baseline"` from `SmeacCitation.source_type`.
4. **HITL Facade (`src/uservice/hitl/facade/hitl.py`)**:
   - Remove broad `except Exception` catch-and-log suppression around Memgraph override recording and Temporal workflow signaling in `submit_decision` so upstream failures propagate directly.
   - Remove `threat_check_mode` and `degraded_reason` columns/fields from HITL ORM and schemas.

---

## R6. Single-Path Temporal Connection & Mandatory Commander Passphrase

### Decision
1. **Temporal Client (`src/uservice/operation/facade.py`)**:
   - Remove the fallback loop over `["127.0.1.1:7233", "127.0.0.1:7233", "localhost:7233"]` in `get_temporal_client`.
   - Connect exclusively to the explicitly configured Temporal endpoint (`TEMPORAL_HOST` / `TEMPORAL_ADDRESS`, failing immediately if unreachable or misconfigured).
2. **Security Authentication (`src/uservice/security/routes.py`)**:
   - Remove `expected_passphrase = "dev_passphrase"` fallback and the `{"dev_passphrase", "dev-passphrase"}` hardcoded dev bypass in `login`.
   - Require `COMMANDER_PASSPHRASE` from environment configuration; propagate a server configuration error (HTTP `500`) if unset rather than authenticating against a hardcoded development passphrase.
