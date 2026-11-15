# Quickstart & Validation Guide: PMA C4ISR Integration

**Feature**: `005-pma-integration` | **Prerequisites**: Docker, Docker Compose v2, Python 3.12+ (`.venv`), Node.js (for Playwright E2E).

Use this guide to spin up the unified single-host ISC + PMA stack, seed sample dynamic threats, validate telemetry archival & `< 2s` AAR analytics, verify HITL threat override enforcement, test DDIL resilience, and run the hermetic offline test suite.

---

## 1. Hermetic Offline Verification (CI / Pre-Flight — Zero Network)

Run unit and contract suites without Docker, MQTT, Memgraph, MinIO, or external LLM API keys:

```bash
source .venv/bin/activate
pytest tests/unit tests/contract -v
```

**Expected**: All unit and contract tests pass offline with zero outbound network connections, validating:
- SQLite `edge_spool` priority-aware DDIL eviction (`priority=0` navigation evicted before `priority=1` detections/alerts) and live-first + async replay order.
- Memgraph openCypher constraint evaluation + `deterministic_fallback` explicit `degraded_mode` propagation.
- Mandatory non-empty HITL `rationale` validation (`422` when blank on `is_threat_override=true`).
- Spatial-temporal+class `TargetEntity` auto-correlation matching + manual split/confirm rules.
- DuckDB over Parquet AAR aggregation latency & accuracy using temporary Parquet datasets.

---

## 2. Launch Unified Single-Host Stack (`c2-shared-net`)

Start PostgreSQL, Temporal (shared queues `isc-smeac-queue` / `pma-ingestion-queue`), Eclipse Mosquitto (`:1883`), MinIO (`:9000` / `:9001`), Memgraph (`:7687` / `:3000`), ISC Backend (`:8000`), Dashboard (`:8080`), and Edge Node (`:8090`):

```bash
cp -n .env.example .env
docker compose up -d --build
```

Verify core service health:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:9000/minio/health/live
```

*(MinIO Console UI available at `http://localhost:9001`; Memgraph Lab at `http://localhost:3000`; Temporal UI at `http://localhost:8233`; Tactical Dashboard at `http://localhost:8080`.)*

---

## 3. Seed Sample Theater Threats (Utility Script in `scripts/`)

Obtain a commander JWT token from the ISC Auth endpoint and seed realistic threat zones into `default-theater`:

```bash
export TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "commander-1", "password": "dev-password"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

python3 scripts/seed_threats.py --project-id default-theater --api-url http://localhost:8000
```

Verify active threat list through ISC Backend (single unified facade):

```bash
curl -fsS "http://localhost:8000/api/v1/threats?project_id=default-theater" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 4. Validate User Stories End-to-End

### Scenario A: Push Telemetry -> 15s Parquet Flush -> Sub-2s DuckDB AAR (`US1` + `US4`)
1. Create or reuse a swarm (`POST /api/v1/swarms`) and verify edge telemetry publishes to `telemetry/projects/default-theater/swarms/{swarm_id}/drone-1/navigation`.
2. Poll live telemetry projection through ISC Backend (`GET /api/v1/swarms/{swarm_id}/telemetry`) and confirm `"telemetry_source": "mqtt_live"`.
3. Wait **15 seconds** (one micro-batch compaction window). For `US1`-only MVP validation, verify partitioned Parquet objects appear in MinIO bucket `tactical-telemetry` under `projects/default-theater/dt=.../swarm={swarm_id}/`. Once `US4` (`T043`) is implemented, query DuckDB AAR (`SC-004`):
   ```bash
   curl -w "\nHTTP %{http_code} | Total: %{time_total}s\n" \
     -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/api/v1/analytics/aar?project_id=default-theater&query_type=summary"
   ```
   **Expected**: HTTP `200`, `query_duration_ms < 2000`, `degraded_mode: false`.

### Scenario B: Dynamic Threat Gating & Audited HITL Override (`US2`)
1. Submit a SMEAC order targeting coordinates inside a seeded active `ThreatZone` (from Step 3).
2. Inspect order status (`GET /api/v1/swarms/{swarm_id}/orders/{order_id}`) — verify status transitions to `pending_hitl` (never auto-executed) and displays `threat_conflicts`.
3. Attempt to approve pending HITL decision **without rationale**:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" -X POST \
     "http://localhost:8000/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide" \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"decision": "approved", "rationale": ""}'
   ```
   **Expected**: HTTP `422`.
4. Submit approval **with mandatory justification** (`"rationale": "SEAD suppression window authorized."`) -> HTTP `200`, command advances to `executing`, audit & Memgraph `INTERSECTS_THREAT` override recorded.
5. Manually deactivate the threat (`PATCH /api/v1/threats/{threat_id}/deactivate`) with audit reason -> verify active flag becomes `false` only after explicit operator action.

### Scenario C: Target Detection Snapshot & Multi-Mission Lineage (`US3`)
1. Trigger two positive YOLO-E detections of identical `target_class` within configured proximity/time across two missions in `default-theater`.
2. Query `GET /api/v1/targets?project_id=default-theater` -> confirm a single correlated `TargetEntity` with `observation_count >= 2`.
3. Fetch snapshot via `GET /api/v1/analytics/detections/{event_id}/snapshot` -> verify HTTP `200` `image/jpeg` without direct browser access to MinIO.

### Scenario D: SMEAC Copilot Non-Executing Draft (`US4`)
1. Invoke Copilot draft:
   ```bash
   curl -fsS -X POST "http://localhost:8000/api/v1/smeac/draft" \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"project_id": "default-theater", "commander_intent": "Recon north sector while avoiding active SAM threats"}'
   ```
   **Expected**: HTTP `200` returning `"draft_only": true`, `"status": "draft"`, and `source_citations`. Confirm no order or `SwarmCommand` was dispatched automatically (`GET /api/v1/swarms/{swarm_id}/telemetry` remains idle).

### Scenario E: DDIL Disconnect, Selective Eviction & Live-First Replay
1. Pause Mosquitto (`docker compose pause mosquitto`) for 30s while edge generates routine `navigation` frames plus at least one critical `detection`/`alert`.
2. Unpause Mosquitto (`docker compose unpause mosquitto`).
3. Confirm dashboard immediately shows live position updates (`telemetry_source: "mqtt_live"`), followed by replayed backlog rows (`replayed: true`) appearing in DuckDB AAR within 15 seconds.

### Scenario F: Memgraph Outage Deterministic Degraded Fallback
1. Pause Memgraph (`docker compose pause memgraph`).
2. Submit a SMEAC order inside a zone listed in `config/restricted_zones.json`.
3. **Expected**: Verification falls back cleanly (`threat_check_mode: "deterministic_fallback"`), catches the static zone violation / enforces HITL safety escalation, and explicitly flags `degraded_mode: true` in API responses and dashboard status banners.
4. Unpause Memgraph (`docker compose unpause memgraph`).
