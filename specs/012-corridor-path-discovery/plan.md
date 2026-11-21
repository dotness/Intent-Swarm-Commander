# Implementation Plan: Gradual Corridor Path Discovery and Adaptive Survey

**Branch**: `012-corridor-path-discovery` | **Date**: `2026-11-19` | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/spec.md)

**Input**: Feature specification from `/specs/012-corridor-path-discovery/spec.md`

## Summary

Implement coordinate-free, edge-autonomous 3D corridor path discovery, adaptive survey navigation, reverse-path return, full snapshot persistence, and live C2 intelligence visualization. When a commander submits a coordinate-free SMEAC order such as *"go check the corridor next 20 meters and go back"*, the backend SMEAC parser extracts a `corridor_survey` command with `RelativeCorridor` geometry, rejects non-positive distances (`<= 0`), defaults omitted distance to `20.0 m`, assigns a single lead scout (`drone-1`) while holding remaining swarm drones at staging (`FR-019`), and dispatches the survey to `src/edge`. At the starting point, `CorridorSurveyController` performs a mandatory 8-heading `360°` yaw look-around sweep while holding safely until `CorridorVisualAnalyzer` (deterministic sub-500 ms OpenCV 5×3 spatial-clearance analysis + YOLO-World/`EdgeTargetMatcher` object discrimination) validates an opening (`SC-002`, `SC-007`). During continuous rolling 3D flight along straight, curved, L-shaped, S-bend, forked, and elevation-varying passages within configurable `[min_altitude_m, max_altitude_m]` bounds (`FR-021`), every captured snapshot is uploaded to MinIO (`FR-020`), trajectory updates are published over QoS 1 MQTT with snapshot-linked provenance (`FR-014`), cleared-segment boundaries enforce a `5 s` guidance-outage failsafe return (`SC-004`, `SC-007`), and `src/uservice/corridor/` materializes the `CorridorIntelligenceReport` for live dual-projection 3D SVG rendering and two-tier Recall / Emergency Abort control in `src/dashboard/`.

## Technical Context

**Language/Version**: Python 3.12+ (edge node & C2 backend microservices), JavaScript ES2022 (dashboard UI & Playwright E2E)

**Primary Dependencies**: FastAPI, Pydantic v2, `pydantic-ai`, `google-genai`, `temporalio`, `sqlalchemy[asyncio]`, `asyncpg`, `ultralytics` (YOLO-World), `opencv-python-headless`, `numpy`, `mavsdk`, `paho-mqtt`, `aiomqtt`, `boto3`, Playwright (zero new packages beyond `pyproject.toml`)

**Storage**: PostgreSQL (`swarm_commands`, `corridor_surveys`, `corridor_snapshots`, `corridor_trajectory_decisions`, `corridor_findings`, `audit_events`, `swarm_live_states`), MinIO `tactical-snapshots` (all captured survey JPEGs without TTL pruning), SQLite WAL (`EdgeSpool` DDIL spooling)

**Testing**: `pytest` (unit, contract, hermetic API/security tests) and Playwright (`npx playwright test`) for no-mock multi-shape E2E video verification

**Target Platform**: Linux (Raspberry Pi 5 edge companion computer + Docker Compose simulation stack with PX4 SITL, Virtual Cam, Mosquitto, MinIO, PostgreSQL, Temporal, Memgraph)

**Project Type**: Distributed edge-to-C2 microservice, Temporal orchestration, and robotics control system (`src/edge/`, `src/uservice/`, `src/dashboard/`)

**Performance Goals**: `<=500 ms` edge snapshot-to-trajectory update latency (`SC-007`), `5.0 s` cleared-segment guidance-outage failsafe timeout (`SC-004`, `SC-007`), `<=5.0 s` post-mission `CorridorIntelligenceReport` availability (`SC-006`), `>=2.5 Hz` survey snapshot cadence, `10 Hz` edge flight-control loop

**Constraints**: Constitution VI (zero mocks/stubs in `src/`, hermetic unit/contract tests), Constitution VII (single-path success logic, unconditional top-level imports, zero `*_AVAILABLE` flags or fallback branches), `mandatory-secure-web-skills` (JWT/RBAC + IDOR scoping + zero `innerHTML`/`confirm()`/`alert()`), full snapshot persistence (`FR-020` — TTL expiration & automated storage cleanup explicitly out of scope)

**Scale/Scope**: Single designated lead scout per corridor order inside single- or multi-drone swarms (remaining drones held safely at staging), arbitrary positive survey distances bounded dynamically by real-time battery return reserve

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design | Post-Design | Verification Notes |
|-----------|------------|-------------|--------------------|
| **I. Cone of Uncertainty (LTV)** | PASS | PASS | Directly advances autonomous GPS-denied navigation, edge-authored trajectory intelligence, and C2 situational awareness toward the TO-BE swarm vision. |
| **II. Cynefin Domain Assessment** | PASS | PASS | Logged `Corridor_3D_Path_Discovery` as **Complicated** via `assess_domain.py` prior to design (deterministic OpenCV clearance geometry + MAVSDK 3D breadcrumbs + structured DDD persistence). |
| **III. Execution via OODA Loops** | PASS | PASS | Operationalizes an explicit 3D OODA loop: Observe (360°/periodic snapshots) → Orient (OpenCV 5×3 free-space + YOLO/LLM intelligence) → Decide (edge 3D trajectory/branch/altitude/return instruction) → Act (MAVSDK + QoS 1 MQTT provenance). |
| **IV. Guard Against False Cones** | PASS | PASS | Uses existing `opencv-python-headless`, `ultralytics`, `google-genai`, `mavsdk`, and `paho-mqtt` stack already in `pyproject.toml`; rejects unverified ROS/VLM-per-frame hype. |
| **V. Script Organization** | PASS | PASS | Simulation virtual-camera extensions live strictly in `scripts/virtual_cam_server.py`; root directory remains clean. |
| **VI. Production Purity & Test Isolation** | PASS | PASS | Zero mocks/stubs in `src/`. No-mock E2E streams multi-shape corridor visuals from `scripts/virtual_cam_server.py` through live `src/edge`, PX4 SITL, Mosquitto, MinIO, `src/uservice`, and dashboard. Unit/contract tests remain hermetic in `tests/`. |
| **VII. Single-Path Success Logic** | PASS | PASS | Unconditional top-level imports in `corridor_analyzer.py`, `corridor_survey.py`, and `src/uservice/corridor/`; zero `try/except ImportError`, zero `*_AVAILABLE` flags, zero fallback matchers/simulators in `src/`. |

## Project Structure

### Documentation (this feature)

```text
specs/012-corridor-path-discovery/
├── plan.md                                  # This file (/speckit-plan command output)
├── research.md                              # Phase 0 output (/speckit-plan command)
├── data-model.md                            # Phase 1 output (/speckit-plan command)
├── quickstart.md                            # Phase 1 output (/speckit-plan command)
├── contracts/                               # Phase 1 output (/speckit-plan command)
│   └── corridor-survey-contract.md
└── tasks.md                                 # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/
├── edge/
│   ├── api/server.py                        # Extended: /corridor-survey/start (with active staging_hold_drone_ids task cancellation + survey_staging_hold telemetry), /{id}/recall, /{id}/emergency-abort, /{id}/status, /telemetry
│   ├── navigation/corridor_survey.py        # NEW: CorridorSurveyController (360° sweep, 3D rolling discovery, 5s failsafe, reverse breadcrumbs, overrides)
│   ├── telemetry/publisher.py               # Extended: full survey snapshot MinIO upload + QoS 1 corridor telemetry/provenance events
│   └── vision/corridor_analyzer.py          # NEW: CorridorVisualAnalyzer (<500ms OpenCV 5x3 clearance/3D geometry + YOLO/LLM intelligence)
├── uservice/
│   ├── corridor/                            # NEW DDD domain package (uservice-template compliant)
│   │   ├── __init__.py
│   │   ├── api/routes.py                    # Survey queries, BFF snapshot image proxy, recall & emergency-abort endpoints
│   │   ├── facade/corridor.py               # CorridorFacade (RBAC, swarm/project scoping, edge override forwarding, report assembly)
│   │   ├── models/contract/schemas.py       # Pydantic v2 contracts (CorridorSurveyParams, CorridorIntelligenceReport, override responses)
│   │   ├── models/storage/survey.py         # SQLAlchemy ORM models (CorridorSurvey, CorridorSnapshot, CorridorTrajectoryDecision, CorridorFinding)
│   │   └── operations/survey_service.py     # Atomic ingestion projection & report compilation operations
│   ├── database/engine.py                   # Register corridor ORM tables & idempotent swarm_commands.survey_params migration
│   ├── main.py                              # Mount corridor_router & wire TelemetryIngestor corridor_survey_callback (suppress HITL on survey_* statuses)
│   ├── security/proxy.py                    # Pass-through routing for /corridor-surveys endpoints
│   ├── smeac/
│   │   ├── facade/smeac.py                  # Coordinate-free survey validation (reject <=0 distance, 20m default), lead scout assignment, skip empty geo threat check
│   │   ├── models/contract/command.py       # MissionType.CORRIDOR_SURVEY + SwarmCommand.survey_params
│   │   ├── models/contract/schemas.py       # CorridorSurveyResponse fields & CorridorSurveyParams DTO exposure
│   │   ├── operations/process.py            # Dispatch corridor_survey commands to edge POST /corridor-survey/start
│   │   └── operations/smeac_agents.py       # RelativeCorridor GeoJSON type & coordinate-free SMEAC prompt rules
│   └── telemetry/
│       ├── models/contract/events.py        # Corridor survey event validators/helpers preserving Feature 011 compatibility
│       └── operations/ingestor.py           # Persist AuditEvent + invoke corridor_survey_callback on corridor survey MQTT events
└── dashboard/
    ├── index.html                           # Add Corridor Survey & Intelligence panel + in-page override confirmation dialog
    ├── css/style.css                        # Dual-projection 3D SVG, filmstrip, and override badge styling
    └── js/
        ├── api.js                           # Corridor survey list/report, BFF image fetch, recall & emergency-abort API calls
        ├── corridor.js                      # NEW: XSS-safe SVG top-down plan & elevation profile renderer, snapshot filmstrip, override controls
        └── main.js                          # Initialize CorridorController and poll active corridor surveys alongside telemetry

docker-compose.yml                           # Extended: virtual_cam service configured with MQTT_BROKER_HOST/MQTT_BROKER_PORT & depends_on mosquitto

scripts/
└── virtual_cam_server.py                    # Extended: Mosquitto MQTT telemetry pose subscriber (navigation & alert) driving 3D perspective corridor_scene rendering + optional POST /pose/{drone_id} override

tests/
├── unit/
│   ├── test_corridor_analyzer.py            # NEW: <500ms frame analysis, turns/overhangs/dead-end/forks/degraded-feed tests
│   ├── test_corridor_survey_controller.py   # NEW: 360° hold, 3D altitude bounds, 5s guidance timeout, reverse breadcrumbs, recall vs abort
│   └── test_corridor_smeac_and_api.py       # NEW: Coordinate-free SMEAC intake, <=0 rejection, 20m default, lead scout, IDOR & RBAC tests
├── contract/
│   └── test_corridor_mqtt_contract.py       # NEW: QoS 1 corridor telemetry/provenance envelopes & Feature 011 compatibility
└── e2e/
    └── prod_corridor_survey.spec.js         # NEW: Zero-mock multi-shape corridor E2E + dashboard 3D SVG & snapshot replay verification
```

**Structure Decision**: Extends the existing three-tier repository layout (`src/edge/`, `src/uservice/`, `src/dashboard/`) with a dedicated `src/uservice/corridor/` DDD domain package matching existing `smeac/`, `swarm/`, `telemetry/`, and `analytics/` patterns, plus cleanly isolated `corridor_analyzer.py` and `corridor_survey.py` edge modules so Feature 011 obstacle avoidance remains completely unaffected.

## Security Design & Verification Plan

Following `mandatory-secure-web-skills`:

1. **Authentication, RBAC & IDOR Ownership Enforcement**:
   - Every C2 corridor survey endpoint requires a valid Bearer JWT validated by `auth_gateway_middleware` and enforces explicit scopes via `require_scopes`: `swarm:read` on `GET` survey/report/snapshot endpoints and `smeac:create` on `POST .../recall` and `POST .../emergency-abort`.
   - `CorridorFacade` validates `survey.swarm_instance_id == swarm_id` and `survey.project_id == active_project_id` on every survey and snapshot fetch, returning `404` on mismatch to prevent cross-swarm or cross-tenant IDOR.
2. **Input Sanitization, File/MinIO Security & SQL Safety**:
   - All database interactions use SQLAlchemy 2.0 ORM and bound queries exclusively (zero SQL string concatenation).
   - Snapshot object keys (`projects/{project_id}/swarms/{swarm_id}/corridor-surveys/{survey_id}/drones/{drone_id}/{snapshot_id}.jpg`) enforce strict UUID formatting, `PROJECT_SLUG_RE`, `_DRONE_ID_RE`, and `validate_object_key()` to block path traversal (`..`, `\`, `/`).
   - Uploaded snapshot payloads MUST pass JPEG magic-byte verification (`\xff\xd8\xff`) and a `<= 5 MB` size cap. The authenticated BFF image proxy (`/snapshots/{snapshot_id}/image`) returns `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store` so MinIO credentials never reach the browser.
   - Non-positive `target_distance_m <= 0`, inverted altitude bounds (`min_altitude_m >= max_altitude_m`), and explicit `altitude_m` outside `[min_altitude_m, max_altitude_m]` fail closed with HTTP `422` (omitted `altitude_m` defaults to `clamp(2.5, min_altitude_m, max_altitude_m)`).
3. **XSS-Safe Frontend & No Native Popups (`src/dashboard/`)**:
   - `src/dashboard/js/corridor.js` MUST build all DOM and SVG geometry exclusively via `document.createElement()`, `document.createElementNS()`, `textContent`, `setAttribute()`, and `replaceChildren()`. Zero `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, or `eval()`.
   - Operator Recall / Emergency Abort confirmation MUST use an in-page HTML `<dialog>` modal; zero native `confirm()`, `alert()`, or `prompt()`.
   - Snapshot `blob:` URLs fetched via `fetchSnapshotBlobUrl()` are explicitly tracked and released via `URL.revokeObjectURL()`.
4. **Testing Network Binding**:
   - Hermetic test servers bind strictly to `127.0.0.1` / `localhost` (`0.0.0.0` prohibited in test harnesses).
5. **Tracked `TODO(security)` Global Deferrals (Explicitly Out of Feature 012 Scope)**:
   - `TODO(security)`: Central `src/uservice/main.py` CORS wildcard origins (`allow_origins=["*"]`) and global API rate-limiting middleware are tracked at platform level outside Feature 012.
   - `TODO(security)`: Frontend JWT storage migration from `localStorage`/`sessionStorage` (`src/dashboard/js/auth.js`) to `HttpOnly`/`Secure`/`SameSite` cookies and backend PostgreSQL mTLS enforcement are tracked at platform level outside Feature 012.
   - `TODO(security)`: Automated snapshot retention TTL and storage cleanup policies are explicitly out of scope per `FR-020`.
6. **Verification Plan**:
   - Static check verifying zero `innerHTML`/`confirm()`/`alert()` in `src/dashboard/js/corridor.js` and zero `ImportError`/`*_AVAILABLE` flags in `src/`.
   - Automated unit/API security tests verifying `401`/`403` scope failures, cross-swarm IDOR `404`, non-positive distance `422`, path-traversal key rejection, and JPEG magic-byte validation.

## Complexity Tracking

No Constitution Check violations exist; all architectural choices fit cleanly within the existing `uservice-template` DDD structure and Raspberry Pi 5 edge architecture without adding dependencies or bypassing single-path purity rules.

## LTV Node Point Alignment & Governance

- **Cynefin Domain Assessment**: Logged `Corridor_3D_Path_Discovery` as **Complicated** via `.agents/skills/cynefin-domain-assessor/scripts/assess_domain.py` (`2026-11-19`).
- **Aligned LTV Node Points**:
  - `MINT_UAV_Simulation_Validation` (autonomous closed-loop UAV visual navigation and perception-to-action validation in simulation prior to field deployment)
  - `Isaac_Lab_Safety_Corridor_Certified` (verifiable 3D safety corridor bounds and latency tolerances)
  - `CBF_SCIFF_Dual_Safety_Active` (enforced physical vertical/lateral clearance constraints and rule-based command validation)
- **Architecture Review Gate**: Implementation MUST be reviewed by `.agents/agents/uservice-arch-reviewer` prior to completion to confirm strict DDD separation (`Router → Facade → Operations → Storage`) and Constitution VI/VII compliance.

### Architecture Review Notes (`uservice-arch-reviewer`)

Reviewed `src/uservice/corridor/`, `src/uservice/smeac/`, `src/uservice/security/proxy.py`, `src/uservice/telemetry/`, `src/edge/`, `src/dashboard/`, `scripts/virtual_cam_server.py`, and `docker-compose.yml` via `uservice-arch-reviewer`, and applied the following remediations:

1. **RBAC, Cross-Swarm/Cross-Tenant IDOR & HTTP Error Mapping**:
   - `SmeacFacade.get_order_status()` now validates `record.swarm_instance_id == swarm_id` (`404` on mismatch); `SmeacFacade.submit_smeac_order()` validates `SwarmInstance` existence and `swarm_row.project_id == project_id` BEFORE inserting `SmeacOrder` (`404` in `src/uservice/smeac/api/routes.py` without orphan rows).
   - `src/uservice/corridor/api/routes.py` catches `PermissionError` -> `403` across all five corridor endpoints and `CorridorEdgeUnavailableError` -> `502` on `/recall` and `/emergency-abort`.
   - `ingest_corridor_event()` enforces `str(survey.swarm_instance_id) == str(event.swarm_id) and survey.project_id == event.project_id` and validates incoming `snapshot_uri` values against `MinioStore.SNAPSHOT_BUCKET`, `validate_object_key()`, and the expected survey prefix before insertion.
   - `swarm_proxy_middleware()` in `src/uservice/security/proxy.py` replaces substring matching with exact `parts[5]` path-segment matching and moves imports to top level.
2. **DDD Separation, Performance & State-Machine Safety**:
   - Extracted MinIO S3 URI/size/JPEG validation (`fetch_verified_snapshot_bytes`) and edge HTTP override forwarding (`resolve_swarm_edge_endpoint`, `forward_override_to_edge`) from `CorridorFacade` into `src/uservice/corridor/operations/survey_service.py`.
   - Eliminated N+1 per-survey `COUNT` queries in `list_swarm_surveys()` using `GROUP BY survey_id` aggregates; appended `?project_id=...` to `image_proxy_url` in `assemble_corridor_report()`.
   - Added `_TERMINAL_SURVEY_PHASES` guards in `_ingest_snapshot_event()`, `_ingest_trajectory_event()`, `_ingest_phase_event()`, and `_ingest_report_event()` plus duplicate `operator_emergency_abort` decision deduplication so out-of-order/DDIL-replayed MQTT messages cannot revert terminal survey states.
   - Passed `commander_id` through override forwarding to `edge/api/server.py` and `CorridorSurveyController.recall()` / `emergency_abort()`.
3. **Edge Controller & Server Hardening (`src/edge/`)**:
   - Removed the test-only `_external_guidance_lock_s` hook from `src/edge/navigation/corridor_survey.py` and rejected `drone=None` in `__init__` (`Constitution VI`).
   - Refreshed live `self.battery_pct` via `_read_pose_snapshot()` on every `step_outbound()` iteration (with explicit `is not None` handling for `0.0` readings), offloaded OpenCV/YOLO frame analysis & JPEG encoding via `asyncio.to_thread()`, and completed `recall()` interrupts during `initial_look_around` cleanly through `run_return_leg("operator_recall")` -> `SurveyPhase.COMPLETED`.
   - Wired `EdgeTargetMatcher()` in `src/edge/api/server.py`, removed global `_telemetry_publisher.drone_id` mutation, added UUID/drone-ID/rationale validators, and failed closed with HTTP `503` when no controller is attached to the scout drone.
   - Moved safe top-level imports in `src/uservice/smeac/facade/smeac.py` and `src/uservice/smeac/operations/process.py` (preserving activity-scoped DB/HTTP imports for Temporal sandbox safety), and made `dispatch_edge_mission_activity` fail fast when a corridor survey lacks `endpoint_url`.
4. **Dashboard & Virtual Camera Security Hardening**:
   - Replaced `galleryEl.innerHTML = ""` in `src/dashboard/js/main.js` with `galleryEl.replaceChildren()`; restricted `fetchSnapshotBlobUrl()` in `src/dashboard/js/api.js` to relative `/api/v1/` paths with `401` session clearing; deduplicated in-flight filmstrip snapshot fetches in `src/dashboard/js/corridor.js`.
   - Added `Content-Length` size caps (`65536` bytes) and `_validate_local_asset_path()` extension + root-path validation in `scripts/virtual_cam_server.py`.
5. **Pre-existing / Platform-Level Deferrals**:
   - Platform-wide items outside Feature 012 (central wildcard CORS in `src/uservice/main.py`, `localStorage`/`sessionStorage` JWT storage, pre-existing `auth_indicator.js` `innerHTML`, Leaflet CDN SRI headers, PostgreSQL mTLS / DB default env config, and internal edge HTTP auth on port `8090` / `docker-compose.yml`) remain tracked under **Security Verification Plan §5 (`TODO(security)`)**.
