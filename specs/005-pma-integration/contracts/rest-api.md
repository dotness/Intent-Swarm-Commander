# Contract: Unified ISC Backend C2 Facade REST API

**Service**: Intent-Swarm-Commander Backend (`src/uservice/main.py`, port `8000`)
**Base URL**: `http://localhost:8000/api/v1`
**Authentication**: OAuth 2.1 Bearer JWT via existing `auth_gateway_middleware` (`Authorization: Bearer <token>`)
**Envelope Standard**: `Response[T]` (`{"data": ..., "meta": ...}`) and `PaginatedResponse[T]` (`src/uservice/base/models/api/response.py`) unless noted for backwards-compatible dashboard contracts.
**Architecture Constraint (`FR-008`)**: Tactical Dashboard interacts **exclusively** with these endpoints; direct browser access to Memgraph, MinIO, DuckDB, or external PMA endpoints is prohibited.

---

## 1. Dynamic Threat Knowledge Graph Endpoints (`src/uservice/threat/api/routes.py`)

### 1.1 `POST /api/v1/threats`
Register a new dynamic `ThreatZone` in Memgraph (never expires automatically via TTL per `FR-006`).
- **Required Scope**: `threat:write`
- **Request**:
```json
{
  "project_id": "default-theater",
  "name": "Mobile SA-17 Battery North",
  "threat_type": "SAM",
  "severity": "critical",
  "lat": 52.5310,
  "lon": 13.4120,
  "radius_m": 800.0,
  "min_alt_m": 0.0,
  "max_alt_m": 450.0,
  "polygon_geojson": null,
  "source": "sigint-operator"
}
```
- **Response (`201 Created`)**:
```json
{
  "data": {
    "threat_id": "7b9a1200-3d20-4f88-a2b1-771122334455",
    "project_id": "default-theater",
    "name": "Mobile SA-17 Battery North",
    "threat_type": "SAM",
    "severity": "critical",
    "lat": 52.5310,
    "lon": 13.4120,
    "radius_m": 800.0,
    "min_alt_m": 0.0,
    "max_alt_m": 450.0,
    "active": true,
    "created_at": "2026-11-14T20:20:00Z",
    "created_by": "commander-1"
  },
  "meta": {"degraded_mode": false}
}
```
- **Errors**: `503 Service Unavailable` with explicit JSON error (`{"error": "memgraph_unavailable", "detail": "..."}`) when Memgraph Bolt connection fails (no silent fake persistence per `FR-012`/`FR-013`).

### 1.2 `GET /api/v1/threats`
List active (or all) `ThreatZone` nodes in a tactical theater.
- **Required Scope**: `threat:read`
- **Query Params**: `project_id` (default `"default-theater"`), `include_inactive` (`bool`, default `false`).
- **Response (`200 OK`)**:
```json
{
  "data": {
    "project_id": "default-theater",
    "threats": [
      {
        "threat_id": "7b9a1200-3d20-4f88-a2b1-771122334455",
        "name": "Mobile SA-17 Battery North",
        "threat_type": "SAM",
        "severity": "critical",
        "lat": 52.5310,
        "lon": 13.4120,
        "radius_m": 800.0,
        "min_alt_m": 0.0,
        "max_alt_m": 450.0,
        "active": true
      }
    ],
    "fallback_static_zones": []
  },
  "meta": {"degraded_mode": false, "source": "memgraph"}
}
```
- **Degraded Behavior (`FR-012`)**: If Memgraph is unreachable during read, returns static baseline zones from `config/restricted_zones.json` under `fallback_static_zones` with `meta: {"degraded_mode": true, "source": "deterministic_baseline_fallback", "reason": "..."}` rather than silent empty array or synthetic threats.

### 1.3 `PATCH /api/v1/threats/{threat_id}/deactivate`
Explicit manual deactivation of an active `ThreatZone` (`FR-006`).
- **Required Scope**: `threat:write`
- **Request**:
```json
{
  "project_id": "default-theater",
  "reason": "SEAD confirmed battery neutralized by ground recon visual report."
}
```
*(Validation: `reason` required, `min_length=5`.)*
- **Response (`200 OK`)**:
```json
{
  "data": {
    "threat_id": "7b9a1200-3d20-4f88-a2b1-771122334455",
    "active": false,
    "deactivated_at": "2026-11-14T20:45:00Z",
    "deactivated_by": "commander-1",
    "deactivation_reason": "SEAD confirmed battery neutralized by ground recon visual report."
  }
}
```
- **Errors**: `404 Not Found` if `threat_id` missing in `project_id`; `422` if `reason` blank.

---

## 2. Live Push Telemetry Projection (`src/uservice/swarm/api/routes.py`)

### 2.1 `GET /api/v1/swarms/{swarm_id}/telemetry`
Read live pushed drone telemetry collected from Mosquitto MQTT (replaces legacy synchronous edge HTTP polling & removes synthetic `(0,0)` / fallback normalization).
- **Required Scope**: `swarm:read`
- **Response (`200 OK`)**:
```json
{
  "swarm_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "default-theater",
  "telemetry_source": "mqtt_live",
  "degraded_mode": false,
  "last_seen_utc": "2026-11-14T20:15:02Z",
  "drones": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000-drone-1",
      "drone_id": "drone-1",
      "status": "patrolling",
      "battery_pct": 87.0,
      "position": {"lat": 52.52145, "lng": 13.40612, "alt_m": 120.5},
      "heading": 84.2,
      "speed": 14.8,
      "current_mission": "patrolling",
      "stale": false
    }
  ]
}
```
- **Degraded Behavior**: When no live MQTT frames have arrived within `TELEMETRY_STALE_THRESHOLD_S` or Mosquitto subscriber is disconnected, returns `telemetry_source: "mqtt_stale"` / `"degraded_unavailable"`, `degraded_mode: true`, and zero fabricated positions.

---

## 3. DuckDB AAR Analytics & Snapshots (`src/uservice/analytics/api/routes.py`)

### 3.1 `GET /api/v1/analytics/aar`
Execute sub-2s DuckDB analytical queries directly over MinIO partitioned Parquet telemetry (`SC-004`).
- **Required Scope**: `analytics:read`
- **Query Params**:
  - `project_id`: `str` (default `"default-theater"`)
  - `swarm_id`: `str | None`
  - `query_type`: `"summary" | "trajectory" | "battery_decay" | "detections"` (default `"summary"`)
  - `start_time`: `datetime | None` (ISO-8601 UTC)
  - `end_time`: `datetime | None` (ISO-8601 UTC)
  - `limit`: `int` (default `500`, max `5000`)
- **Response (`200 OK`)**:
```json
{
  "data": {
    "project_id": "default-theater",
    "query_type": "summary",
    "row_count": 3,
    "query_duration_ms": 142.6,
    "records": [
      {
        "drone_id": "drone-1",
        "event_count": 420,
        "min_battery_pct": 71.2,
        "max_alt_m": 135.0,
        "detection_count": 2,
        "first_seen": "2026-11-14T20:05:00Z",
        "last_seen": "2026-11-14T20:12:00Z"
      }
    ]
  },
  "meta": {"degraded_mode": false, "engine": "duckdb-parquet"}
}
```

### 3.2 `GET /api/v1/analytics/detections/{event_id}/snapshot`
Retrieve MinIO detection visual crop safely through ISC Backend (`FR-007`, `FR-008`).
- **Required Scope**: `analytics:read`
- **Response (`200 OK`)**: `image/jpeg` binary stream (`Cache-Control: private, max-age=300`) fetched from MinIO `tactical-snapshots`.
- **Errors**: `404 Not Found` if `event_id` or snapshot object missing; `503` if MinIO unreachable.

---

## 4. Target Entity Lineage (`src/uservice/threat/api/routes.py`)

### 4.1 `GET /api/v1/targets`
List tracked `TargetEntity` nodes correlated across missions inside `project_id` (`FR-007`).
- **Required Scope**: `analytics:read`
- **Query Params**: `project_id` (default `"default-theater"`), `target_class` (`str | None`), `status` (`str | None`).
- **Response (`200 OK`)**: `Response[list[TargetEntitySummary]]` containing `target_id`, `canonical_class`, `status`, `observation_count`, `first_seen_at`, `last_seen_at`, `last_lat`, `last_lon`, `latest_snapshot_api_path`.

### 4.2 `GET /api/v1/targets/{target_id}/lineage`
Retrieve chronological chain of `DetectionEvent`s attributed to `target_id` across swarms and missions.
- **Required Scope**: `analytics:read`
- **Response (`200 OK`)**:
```json
{
  "data": {
    "target_id": "a1122334-5566-7788-99aa-bbccddeeff00",
    "project_id": "default-theater",
    "canonical_class": "armored_vehicle",
    "status": "auto_correlated",
    "observations": [
      {
        "event_id": "41b2c799-1c02-40ab-85b1-99e001122334",
        "swarm_id": "550e8400-e29b-41d4-a716-446655440000",
        "mission_id": "c7a1f440-9b3a-4d75-9a21-51a63e220001",
        "drone_id": "drone-1",
        "confidence": 0.91,
        "lat": 52.52310,
        "lon": 13.40980,
        "detected_at": "2026-11-14T20:15:18Z",
        "match_method": "auto_spatio_temporal",
        "distance_m": 0.0,
        "delta_s": 0.0,
        "verified_by_analyst": false,
        "snapshot_url": "/api/v1/analytics/detections/41b2c799-1c02-40ab-85b1-99e001122334/snapshot"
      }
    ]
  }
}
```

### 4.3 `POST /api/v1/targets/{target_id}/review`
Human analyst confirmation or correction (split miscorrelated `event_id` into its own `TargetEntity`) (`FR-007`).
- **Required Scope**: `analytics:write`
- **Request**:
```json
{
  "project_id": "default-theater",
  "action": "confirm",
  "event_id": null,
  "rationale": "Confirmed hull markings match Track-01 across sorties."
}
```
*(Allowed `action`: `"confirm" | "split_event"`; `event_id` required when `action == "split_event"`.)*
- **Response (`200 OK`)**: Updated lineage summary.

---

## 5. AI-Assisted SMEAC Copilot Drafting (`src/uservice/smeac/api/routes.py`)

### 5.1 `POST /api/v1/smeac/draft`
Invoke read-only `DynamicAgentLoop` over Memgraph threats, recent target lineage, and DuckDB swarm readiness to generate a **non-executing** reviewable SMEAC draft (`FR-009`, `SC-005`).
- **Required Scope**: `smeac:create`
- **Request**:
```json
{
  "project_id": "default-theater",
  "swarm_id": "550e8400-e29b-41d4-a716-446655440000",
  "commander_intent": "Recon northern ridge for armored column while avoiding known SAM threat.",
  "focus_lat": 52.53,
  "focus_lon": 13.41,
  "focus_radius_m": 3000.0
}
```
- **Response (`200 OK`)**:
```json
{
  "data": {
    "draft_only": true,
    "status": "draft",
    "project_id": "default-theater",
    "situation": "...",
    "mission": "...",
    "execution": "...",
    "admin_logistics": "...",
    "command_signal": "...",
    "source_citations": [
      {"type": "ThreatZone", "id": "7b9a1200-3d20-4f88-a2b1-771122334455", "summary": "Mobile SA-17 Battery North (radius 800m, critical)"},
      {"type": "TargetEntity", "id": "a1122334-5566-7788-99aa-bbccddeeff00", "summary": "armored_vehicle last seen 20:15Z"}
    ]
  },
  "meta": {"degraded_mode": false, "degraded_reasons": []}
}
```
- **Degraded Behavior (`FR-012`)**: If Gemini API key is unconfigured/unreachable or Memgraph is offline, never hallucinates live threat intelligence or silent fake defaults; returns `503 Service Unavailable` when LLM synthesis is required and unavailable, OR deterministic baseline template draft strictly flagged `meta.degraded_mode = true` with explicit `degraded_reasons`.

---

## 6. Enhanced HITL Threat Conflict & Audited Override (`src/uservice/hitl/api/routes.py`)

### 6.1 `GET /api/v1/swarms/{swarm_id}/hitl/pending` *(Extended)*
Existing endpoint enriched with structured dynamic threat conflict data (`FR-005`):
```json
{
  "pending": [
    {
      "decision_id": "d4455667-8899-4aaa-bbbb-ccccddddeeee",
      "command_id": "11223344-5566-4777-8888-999900001111",
      "action_summary": "RECON to (52.5310, 13.4120) intersects ThreatZone 'Mobile SA-17 Battery North'",
      "timeout_seconds": 600,
      "status": "pending",
      "is_threat_override": true,
      "requires_override_justification": true,
      "threat_conflicts": [
        {
          "threat_id": "7b9a1200-3d20-4f88-a2b1-771122334455",
          "name": "Mobile SA-17 Battery North",
          "threat_type": "SAM",
          "severity": "critical",
          "distance_m": 0.0
        }
      ]
    }
  ]
}
```

### 6.2 `POST /api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide` *(Extended Validation)*
- **Required Scope**: `hitl:decide`
- **Request**:
```json
{
  "decision": "approved",
  "rationale": "Authorized tactical transit at 120m AGL under SEAD suppression window 20:30-20:45Z."
}
```
- **Guard Rule (`FR-005`, `SC-003`)**:
  - When the `HitlDecision` record has `is_threat_override == true` and `decision == "approved"`: if `rationale` is `null`, empty, or whitespace-only, return **HTTP `422 Unprocessable Entity`**:
    ```json
    {
      "detail": "Mandatory override justification ('rationale') is required to approve a mission intersecting active dynamic threat zones."
    }
    ```
  - On valid override approval, store immutable audit entry + update Memgraph `(:SwarmMission)-[:INTERSECTS_THREAT {overridden: true, override_rationale, hitl_decision_id}]->(:ThreatZone)`.
