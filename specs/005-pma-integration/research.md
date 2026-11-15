# Phase 0 Research: Poor-Man's Artemis.IA (PMA) C4ISR Integration

**Feature**: `005-pma-integration` | **Date**: 2026-11-14 | **Spec**: [spec.md](./spec.md)

This document resolves the architectural, integration, resilience, and compliance decisions required to converge the Poor-Man's Artemis.IA (PMA) 4-phase C4ISR stack into Intent-Swarm-Commander (ISC) on a single-host deployment while strictly adhering to Constitution v1.2.0 and `uservice-template` DDD principles.

---

## R1: Push MQTT Telemetry Bus & Edge SQLite DDIL Spooling

- **Decision**:
  1. Replace synchronous HTTP polling (`GET /telemetry` from `src/uservice/swarm/api/routes.py` -> edge container) with asynchronous push telemetry over **Eclipse Mosquitto** (`:1883`) using `paho-mqtt` on the hierarchical topic `telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/{metric}`.
  2. Enforce split QoS policies: QoS `0` (fire-and-forget) for high-frequency `navigation`, `battery` (normal), and `health` updates; QoS `1` (at-least-once) for `detection` events, critical battery (`< 20%`), and `alert` messages.
  3. Deploy an embedded SQLite write-ahead buffer (`edge_spool` in `src/edge/telemetry/spool.py`) for DDIL resilience. Under link loss, all outgoing MQTT messages and deferred MinIO snapshot paths are written to disk up to a configurable byte/record quota. On quota pressure, **evict oldest routine navigation/health records (`priority = 0`) first** while retaining `detection` and `alert` records (`priority = 1`).
  4. On reconnect, **resume live telemetry and alert publishing immediately** and drain queued backlog asynchronously in bounded background batches (`priority DESC, created_at_utc ASC`) with `event_id` deduplication downstream.
  5. Retain `GET /api/v1/swarms/{swarm_id}/telemetry` on ISC Backend backed by an in-memory live telemetry projection fed by the MQTT subscriber, returning explicit staleness and link status (`mqtt_live | mqtt_stale | degraded_unavailable`) rather than synthetic fallback coordinates.

- **Rationale**:
  Polling scales poorly beyond a handful of drones and stalls backend HTTP handlers when an edge node drops into DDIL blackout. Push MQTT decouples edge flight loops (`src/edge/navigation/flight_controller.py`) from control-plane availability. Embedded SQLite provides atomic crash recovery, priority-indexed selective eviction, and zero external broker dependencies on constrained Raspberry Pi 5 edge nodes.

- **Alternatives Considered**:
  - *Append-only JSONL buffer (`/tmp/edge_buffer.jsonl`, originally noted in `docs/analysis/compatibility_with_pma.md`)*: Rejected because line-oriented JSONL cannot efficiently delete oldest routine `navigation` entries while retaining interleaved `detection`/`alert` records without rewriting the whole file.
  - *FIFO drop-oldest ring buffer*: Rejected because high-rate `navigation` traffic during a prolonged blackout would push out older irreplaceable target `detection` events.
  - *Direct HTTP webhook push with exponential backoff*: Rejected because blocked connection pools or server restarts create backpressure directly on the edge asyncio loop.

---

## R2: Near-Real-Time Micro-Batch Parquet Lakehouse & Sub-2s DuckDB AAR Analytics

- **Decision**:
  1. Run an asynchronous MQTT ingestion subscriber + compactor in `src/uservice/telemetry/` that buffers incoming telemetry events in memory and flushes Apache Parquet files via `pyarrow` every **5–15 seconds** (configurable `PARQUET_FLUSH_INTERVAL_S`, default `10s`, or `500` events max batch) to MinIO (`:9000`, bucket `tactical-telemetry`) using Hive-style partitioning:
     `projects/{project_id}/dt={YYYY-MM-DD}/swarm={swarm_id}/{batch_ts}_{uuid}.parquet`.
  2. Implement `src/uservice/analytics/` using embedded **DuckDB** (`duckdb` + `httpfs`/S3 configuration against internal `minio:9000`) to serve After Action Review (AAR) queries (mission timelines, battery decay curves, trajectory reconstruction, detection summaries) in `< 2.0s` (`SC-004`), paired with 5–15s archival freshness (`SC-002`).
  3. On batch failure or transient MinIO unavailability, write failed Parquet flushes to an explicit retry directory on local container storage and emit explicit degraded health/backlog metrics rather than dropping frames silently.

- **Rationale**:
  Storing 2 Hz multi-drone telemetry directly in PostgreSQL (`asyncpg` / `smeac_orders` database) causes index bloat and lock contention on transactional command workflows. Columnar Parquet files partitioned by `project_id`, `dt`, and `swarm_id` let DuckDB perform partition pruning and vectorized scans over MinIO within tens to hundreds of milliseconds for typical mission sizes while satisfying the 5–15 second visibility target.

- **Alternatives Considered**:
  - *15-minute compaction window*: Rejected because tactical AAR workflows require near-real-time availability within 15 seconds after events occur.
  - *Per-event Parquet upload*: Rejected due to object-store small-file explosion causing DuckDB S3 LIST/GET latency spikes well above 2 seconds.
  - *PostgreSQL / TimescaleDB monolithic storage*: Rejected because it couples analytical scans to operational C2 workflow state and diverges from PMA's open Parquet + DuckDB lakehouse architecture.

---

## R3: Memgraph Knowledge Graph Threat Gating, Audited HITL Override & Deterministic Fallback

- **Decision**:
  1. Introduce domain package `src/uservice/threat/` following `uservice-template` layered boundaries (`api/`, `facade/`, `models/`, `operations/`) backed by **Memgraph** (`:7687` Bolt, official `neo4j` async driver) storing `TacticalProject`, `ThreatZone`, `SwarmMission`, `DroneUnit`, `DetectionEvent`, and `TargetEntity` nodes.
  2. Bind every operational query, threat zone, mission, and detection to a `project_id` theater scope (defaulting to `"default-theater"` when omitted by client callers per `FR-004`).
  3. Enforce manual-only `ThreatZone` deactivation (`FR-006`): `active` transitions from `true` to `false` solely via explicit commander/analyst action (`PATCH /api/v1/threats/{threat_id}/deactivate`) with audited `deactivated_by` and `reason`. Automatic TTL expiration is disallowed.
  4. Integrate `ThreatFacade.evaluate_route_threats()` into `safety_check_activity` (`src/uservice/smeac/operations/safety_activity.py`) using openCypher spatial pre-filtering (`point.distance`) + Shapely polygon/altitude intersection (`min_alt_m <= alt <= max_alt_m`):
     - If one or more active `ThreatZone` intersections occur, attach structured `ThreatConflict` violations, **block automatic execution**, and force `ProcessSmeacWorkflow` into the HITL gate (`workflow.wait_condition` for `hitl_decision`).
     - In `HitlFacade.submit_decision()`, approving an order flagged with `is_threat_override = True` requires a non-empty `rationale` / `override_justification`; empty/blank rationales are rejected with HTTP `422` (`FR-005`, `SC-003`). Approved overrides record immutable audit + graph `[:INTERSECTS_THREAT {overridden: true, override_rationale, hitl_decision_id}]` provenance.
     - During implementation, align the existing parameter bug in `src/uservice/hitl/facade/hitl.py` line 91 (`signal_input=decision_data` vs `signal_workflow(..., arg=...)` in `src/uservice/operation/facade.py`) so HITL signals reliably wake Temporal workflows.
  5. If Memgraph is unreachable or times out, fall back deterministically to `config/restricted_zones.json` + static safety bounds + mandatory HITL escalation (`threat_check_mode = "deterministic_fallback"`, `degraded_mode = true`), surfacing explicit degraded-service status to commanders (`FR-012`).

- **Rationale**:
  Satisfies LTV Node Point `Verification_1_Constraint_Graph` and prevents False Cones (`Agent_Discretion_for_Critical_Safety_Decisions` and `LLM_Self_Reflection_for_Verification`) by gating mission commands with formal spatial graph constraints and immutable human accountability. Deterministic degraded fallback prevents silent "fail-open" blind spots during database partition or DDIL scenarios.

- **Alternatives Considered**:
  - *Hard-block all threat intersections without override*: Rejected per `FR-005` clarification; tactical commanders must be able to assume documented operational risk when mission urgency justifies it.
  - *TTL auto-expiration on ThreatZones*: Rejected per `FR-006` clarification; expiring an SAM or EW zone automatically on a clock introduces lethal false-safe risk.
  - *PostGIS-only spatial tables*: Rejected because multi-hop lineage (`SwarmMission -> INTERSECTS_THREAT`, `DroneUnit -> OBSERVED -> DetectionEvent -> ATTRIBUTED_TO -> TargetEntity`) and copilot graph traversal are first-class property graph workloads in Memgraph.

---

## R4: Edge YOLO-E Visual Snapshots in MinIO & Spatial-Temporal+Class Target Lineage

- **Decision**:
  1. Extend `src/edge/` detection reporting so positive `YoloEInference` detections (`confidence >= threshold`) capture an annotated/cropped JPEG frame (`snapshot`) and upload it to MinIO bucket `tactical-snapshots` (`projects/{project_id}/swarms/{swarm_id}/drones/{drone_id}/{event_id}.jpg`), publishing a QoS 1 MQTT `detection` event carrying `snapshot_uri`, `target_class`, `confidence`, geo-coordinates, and `mission_id`. Under DDIL, retain snapshot locally and reference `snapshot_local_path` in `EdgeSpoolRecord` for deferred upload before clearing the spool entry.
  2. Expose snapshot retrieval strictly through ISC Backend (`GET /api/v1/analytics/detections/{event_id}/snapshot`) as an authenticated stream or proxy (zero direct browser credentials to MinIO, honoring `FR-008`).
  3. On `detection` ingestion in `src/uservice/threat/`, execute an automated Memgraph correlation query within the same `project_id`: link detections of identical `target_class` within configurable spatial radius (`CORRELATION_RADIUS_M`, default `250.0`) and temporal window (`CORRELATION_WINDOW_S`, default `3600`) to an existing canonical `TargetEntity` (with edge metadata `distance_m`, `delta_s`, `match_method="auto_spatio_temporal"`), or instantiate a new `TargetEntity`. Provide `/api/v1/targets/{target_id}/review` so analysts can manually confirm, merge, or split miscorrelated detections (`FR-007`).

- **Rationale**:
  Establishes verifiable visual provenance without bloating MQTT frames or Parquet telemetry rows with base64 blobs, while automated spatial-temporal+class correlation provides instant cross-mission target continuity under analyst supervision.

- **Alternatives Considered**:
  - *Inline base64 images inside MQTT JSON payloads*: Rejected due to broker payload bloat and Parquet row size degradation.
  - *Manual-only analyst linking*: Rejected per `FR-007` clarification because cross-mission target tracking breaks down under multi-swarm detection load.
  - *Neural Re-ID feature embeddings in vector DB*: Deferred as unnecessary infrastructure complexity for MVP integration; spatial-temporal + YOLO class matching is deterministic, explainable, and auditable.

---

## R5: Single-Host Unified Deployment (`c2-shared-net`), Shared Temporal Queues & Unified C2 API Facade

- **Decision**:
  1. Converge core and PMA services in root `docker-compose.yml` onto a single host connected via an explicit Docker bridge network (`c2-shared-net`), replacing `network_mode: host` on application services with explicit DNS service names (`postgres`, `temporal`, `mosquitto`, `minio`, `memgraph`, `backend`, `dashboard`, `edge_drone`) and non-conflicting host ports per `docs/analysis/compatibility_with_pma.md` (`5432` ISC Postgres, `7233`/`8233` Shared Temporal, `1883` Mosquitto, `9000`/`9001` MinIO, `7687`/`3000` Memgraph, `8000` ISC Backend, `8080` Dashboard, `8090` Edge). Add explicit `extra_hosts` / UDP port mappings or compose profile bindings for `drone_sim` (Gazebo/PX4 SITL) so existing simulation remains functional.
  2. Share the single `temporalio/auto-setup` instance (`:7233`) across domains using strictly isolated task queues: `ISC_TASK_QUEUE="isc-smeac-queue"` for SMEAC/HITL workflows and `PMA_TASK_QUEUE="pma-ingestion-queue"` for telemetry/threat archival or verification activities (`FR-011` / Section 9.2 port matrix).
  3. Enforce `FR-008`: Tactical Dashboard (`src/dashboard/`) communicates **exclusively** with ISC Backend (`/api/v1/...`). No browser code calls MinIO, Memgraph, DuckDB, or external PMA endpoints directly.

- **Rationale**:
  Single-host bridge networking eliminates localhost assumptions while fitting laptop/workstation C2 footprints, single Temporal avoids JVM/container RAM duplication, and routing everything through ISC Backend keeps OAuth2 JWT enforcement, RBAC scope checks, CORS policy, and `AuditLog` coverage uniform across all features.

- **Alternatives Considered**:
  - *Keeping `network_mode: host` everywhere*: Rejected because multi-stack service discovery (`mosquitto`, `memgraph`, `minio`) becomes fragile and port collisions with PMA components cannot be cleanly isolated.
  - *Direct browser queries to MinIO presigned external hostnames / Memgraph REST*: Rejected per clarified `FR-008` because it circumvents Auth Gateway middleware and leaks storage/graph topology to the frontend.
  - *Separate Temporal clusters*: Rejected due to unnecessary resource overhead on a single host and port `7233`/`8233` collision.

---

## R6: AI-Assisted SMEAC Copilot, Degraded Modes & Constitution v1.2.0 Production Purity

- **Decision**:
  1. **SMEAC Copilot (`POST /api/v1/smeac/draft`)**: Implement a read-only ADK / `pydantic-ai` agent in `src/uservice/smeac/operations/copilot.py` equipped with scoped read-only tools querying `ThreatFacade` (active threats + recent `DetectionEvent`s), `AnalyticsFacade` (recent DuckDB swarm readiness/AAR stats), and `SwarmFacade` (active swarms). Output structured SMEAC draft paragraphs, source citations (`threat_id`, `event_id`, `target_id`), and `draft_only: true`. **Strict safety invariant (`FR-009`, `SC-005`)**: drafting never creates an executing order or bypasses `ProcessSmeacWorkflow` / safety / HITL gates.
  2. **Explicit Degraded Operation (`FR-012`)**: When LLM API keys/endpoints (`GEMINI_API_KEY`) or Memgraph are unavailable during drafting, return explicit `degraded_mode: true` + `degraded_reasons` with deterministic local baseline context (or structured validation error if intent cannot be satisfied) rather than fabricating tactical intelligence.
  3. **Constitution v1.2.0 Production Purity & Legacy Cleanup (`FR-013`, `SC-007`)**: Refactor existing silent simulation/mock shortcuts currently present in `src/`:
     - `src/edge/api/server.py` (remove simulated fallback drone loop defaults and fail explicitly if hardware/ROS2/configured telemetry adapter is unavailable)
     - `src/edge/vision/camera.py` & `src/edge/vision/inference.py` (remove `"SIMULATION_MODE"` stub paths returning empty simulated loads inside `src/`)
     - `src/edge/navigation/flight_controller.py` (replace `# Mock target coordinate` defaults with explicit configured mission waypoints/target coordinates)
     - `src/uservice/smeac/facade/smeac.py` (remove hardcoded `[13.4050, 52.5200]` / `"placeholder_key"` silent fallback synthesis; if LLM parsing fails, report explicit `degraded_mode` deterministic parser error or explicit structured coordinate requirement without guessing coordinates)
     - `src/dashboard/js/api.js` (remove silent `(0,0) -> (52.5200, 13.4050)` fake coordinate injection and `"holding_at_point_a"` placeholder strings)
  4. **Hermetic Test Isolation (`FR-014`, `SC-007`)**: Build `tests/unit/` and `tests/contract/` fixtures using strictly offline doubles injected via dependency overrides/conftest (`aiosqlite`, local temp Parquet/DuckDB dirs, in-memory MQTT dispatcher doubles, fake Neo4j/Memgraph protocol responses in `tests/`, mocked HTTPX transports in `tests/`) guaranteeing zero outbound network sockets, LLM API requests, or live DB requirements during CI unit/contract execution.

- **Rationale**:
  Enforces LTV Node Point `Verification_2_Abductive_Logic_Gate` and Constitution Principle VI (`Production Code Purity & Test Isolation`), ensuring zero dead simulation stubs leak into flight/command paths while keeping developer/CI feedback loops fast and hermetic.

- **Alternatives Considered**:
  - *Keeping `SIMULATION_MODE` environment switches inside `src/` production modules*: Explicitly forbidden by Constitution v1.2.0 Principle VI; simulation feeds arrive via real external interfaces (e.g., ROS2 Gazebo topic / local Docker Compose hardware emulator container) or inside `tests/` harnesses only.
  - *Allowing Copilot drafts to auto-submit directly to `SwarmCommand` execution*: Forbidden by `FR-009`, `SC-005`, and False Cone `Agent_Discretion_for_Critical_Safety_Decisions`.
