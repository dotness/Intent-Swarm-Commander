# Data Model: Poor-Man's Artemis.IA (PMA) C4ISR Integration

**Feature**: `005-pma-integration` | **Date**: 2026-11-14 | **Spec**: [spec.md](./spec.md)

This document defines all persistent and streaming schemas across the unified single-host C4ISR deployment: PostgreSQL ORM extensions, Edge SQLite DDIL spool, MQTT/Parquet telemetry records, MinIO object keys, and Memgraph knowledge graph entities.

---

## 1. Theater / Project Isolation Convention (`project_id`)

All cross-cutting records (ORM tables, MQTT topics, MinIO prefixes, Parquet partitions, Memgraph nodes) carry a theater/project identifier:
- **Field**: `project_id: str`
- **Format**: lowercase alphanumeric slug with hyphens (`^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`, max 64 chars).
- **Default**: `"default-theater"` — automatically bound whenever a caller, drone, or dashboard session omits an explicit `project_id` (`FR-004`).

---

## 2. PostgreSQL ORM Extensions (`src/uservice/`)

Extensions to existing SQLAlchemy async models (migrations/table updates registered in `src/uservice/database/engine.py:init_db`):

### 2.1 `SwarmInstance` (`swarm_instances`)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| *(existing fields)* | UUID, timestamps, `name`, `container_id`, `endpoint_url`, `status`, `drone_count`, `created_by` | Unchanged | Base swarm inventory |
| `project_id` *(new)* | `String(64)` | `NOT NULL`, default `"default-theater"`, indexed | Theater scope (`FR-004`) |

### 2.2 `SmeacOrder` (`smeac_orders`)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| *(existing fields)* | UUID, timestamps, `commander_id`, `situation`, `mission`, `execution`, `admin_logistics`, `command_signal`, `swarm_instance_id`, `status` | `OrderStatus` adds `DRAFT = "draft"` (existing enum value already defined!) | Note: `DRAFT` orders created by Copilot are non-executable until submitted (`FR-009`, `SC-005`) |
| `project_id` *(new)* | `String(64)` | `NOT NULL`, default `"default-theater"`, indexed | Theater scope |
| `threat_check_mode` *(new)* | `String(32)` | `NOT NULL`, default `"full_graph"` | Enum: `"full_graph" \| "deterministic_fallback"` |
| `degraded_reason` *(new)* | `Text` | `NULL` | Populated if Memgraph or LLM Copilot operated degraded (`FR-012`) |
| `draft_source_refs` *(new)* | `Text` | `NULL` | JSON array of cited IDs (`threat_id`, `target_id`, `event_id`) when drafted via Copilot |

### 2.3 `HitlDecision` (`hitl_decisions`)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| *(existing fields)* | UUID, timestamps, `swarm_command_id`, `commander_id`, `decision`, `rationale`, `timeout_triggered`, `action_summary`, `timeout_seconds`, `status`, `workflow_id` | Unchanged | HITL audit record |
| `project_id` *(new)* | `String(64)` | `NOT NULL`, default `"default-theater"`, indexed | Theater scope |
| `is_threat_override` *(new)* | `Boolean` | `NOT NULL`, default `False` | `True` when triggered by active `ThreatZone` intersection (`FR-005`) |
| `threat_zone_ids` *(new)* | `Text` | `NULL` | JSON array of conflicting Memgraph `threat_id` strings |
| `override_justification` *(new)* | `Text` | `NULL` (Required non-empty in API/Facade if `is_threat_override=True` and `decision="approved"`) | Mirrored from/validated alongside `rationale` for immutable audit (`SC-003`) |

---

## 3. Edge DDIL Spool Schema (`src/edge/telemetry/spool.py` — SQLite)

Embedded local write-ahead SQLite database (e.g., `EDGE_SPOOL_DB_PATH=/var/lib/isc-edge/spool.db` or configurable path, WAL mode enabled).

### 3.1 Table `edge_spool`
| Column | SQLite Type | Constraints | Description |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Local monotonic sequence |
| `event_id` | `TEXT` | `UNIQUE NOT NULL` | UUIDv4 generated once on edge capture for downstream deduplication |
| `project_id` | `TEXT` | `NOT NULL` | Bound tactical theater (`"default-theater"` default) |
| `swarm_id` | `TEXT` | `NOT NULL` | Target swarm UUID |
| `drone_id` | `TEXT` | `NOT NULL` | Drone identifier |
| `metric_type` | `TEXT` | `NOT NULL` | `"navigation" \| "battery" \| "health" \| "detection" \| "alert"` |
| `priority` | `INTEGER` | `NOT NULL` | `1` for `"detection"` / `"alert"` / low-battery critical; `0` for routine `"navigation"` / `"battery"` / `"health"` |
| `qos` | `INTEGER` | `NOT NULL` | MQTT QoS (`0` or `1`) |
| `topic` | `TEXT` | `NOT NULL` | Full destination MQTT topic |
| `payload_json` | `TEXT` | `NOT NULL` | Serialized `SwarmTelemetryEvent` JSON |
| `snapshot_local_path` | `TEXT` | `NULL` | Optional local JPEG frame pending deferred MinIO upload |
| `created_at_utc` | `TEXT` | `NOT NULL` | ISO-8601 UTC timestamp |
| `attempts` | `INTEGER` | `NOT NULL DEFAULT 0` | Replay delivery attempt count |
| `synced_at_utc` | `TEXT` | `NULL` | Set on broker ACK (or pruned immediately after replay confirmation) |

**Indexes**:
- `idx_edge_spool_drain ON edge_spool(synced_at_utc, priority DESC, created_at_utc ASC)`
- `idx_edge_spool_evict ON edge_spool(priority ASC, created_at_utc ASC)`

**Priority-Aware Eviction & Live-First Replay Rules (`FR-012` / Clarified)**:
1. **Capacity Guard**: Before inserting when count >= `EDGE_SPOOL_MAX_RECORDS` (or DB size >= `EDGE_SPOOL_MAX_BYTES`), delete oldest rows with `priority = 0` (`ORDER BY created_at_utc ASC`). Only if zero `priority = 0` records remain may oldest `priority = 1` records be trimmed with an explicit critical overflow counter bump.
2. **Reconnect Live-First**: Immediately resume publishing live telemetry and live `alert`/`detection` messages directly to MQTT while marking spooled backlog for async background drain.
3. **Async Backlog Drain**: Background task reads `WHERE synced_at_utc IS NULL ORDER BY priority DESC, created_at_utc ASC LIMIT BATCH_SIZE`. If `snapshot_local_path` is set, upload frame to MinIO (`tactical-snapshots`) and inject final `snapshot_uri` before publishing the QoS 1 MQTT message.

---

## 4. Telemetry Event & Lakehouse Parquet Schema (`src/uservice/telemetry/`)

### 4.1 Canonical Streaming Event (`SwarmTelemetryEvent` Pydantic DTO)
| Field | Type | Required | Constraints / Example |
|---|---|---|---|
| `schema_version` | `str` | Yes | `"1.0"` |
| `event_id` | `uuid.UUID` | Yes | Idempotency identifier generated at edge capture |
| `timestamp` | `datetime` (UTC) | Yes | ISO-8601 UTC event capture time |
| `project_id` | `str` | Yes | Default `"default-theater"` |
| `swarm_id` | `str` | Yes | Swarm UUID string |
| `drone_id` | `str` | Yes | e.g. `"drone-1"` |
| `metric_type` | `Literal` | Yes | `"navigation" \| "battery" \| "health" \| "detection" \| "alert"` |
| `lat` | `float` | Yes | `-90.0 <= lat <= 90.0` (WGS84) |
| `lon` | `float` | Yes | `-180.0 <= lon <= 180.0` (WGS84) |
| `alt_m` | `float` | Yes | Altitude in meters MSL/AGL |
| `heading_deg` | `float` | No (`0.0`) | `0.0 <= heading_deg < 360.0` |
| `speed_ms` | `float` | No (`0.0`) | Ground speed m/s |
| `battery_pct` | `float` | No | `0.0 <= battery_pct <= 100.0` |
| `flight_status` | `str` | No (`"active"`) | `"idle" \| "approaching" \| "patrolling" \| "arrived" \| "rth" \| "aborted"` |
| `target_class` | `str \| None` | No | YOLO-E class (present when `metric_type == "detection"`) |
| `confidence` | `float \| None` | No | `0.0 <= confidence <= 1.0` |
| `bbox` | `list[int] \| None` | No | `[x1, y1, x2, y2]` pixel bounds |
| `snapshot_uri` | `str \| None` | No | `s3://tactical-snapshots/projects/.../{event_id}.jpg` |
| `mission_id` | `str \| None` | No | Associated `SmeacOrder` / `SwarmCommand` UUID |
| `replayed` | `bool` | No (`False`) | `True` when drained from DDIL `edge_spool` |
| `extra` | `dict \| None` | No | Metric-specific metadata (e.g., CPU temp, ROS2/MAVSDK link quality, alert reason) |

### 4.2 Apache Parquet Physical Schema (`tactical-telemetry` bucket)
- **Object Key**: `projects/{project_id}/dt={YYYY-MM-DD}/swarm={swarm_id}/{flush_epoch_ms}_{batch_uuid}.parquet`
- **Compaction Flush Trigger**: `PARQUET_FLUSH_INTERVAL_S` (`5–15s`, default `10s`) OR `PARQUET_BATCH_SIZE` (default `500` events).
- **Compression**: `snappy` (optimal DuckDB scan throughput).
- **Columns (`pyarrow.schema`)**:
  - `event_id`: `pa.string()`
  - `timestamp`: `pa.timestamp("us", tz="UTC")`
  - `project_id`: `pa.string()`
  - `swarm_id`: `pa.string()`
  - `drone_id`: `pa.string()`
  - `metric_type`: `pa.string()`
  - `lat`: `pa.float64()`
  - `lon`: `pa.float64()`
  - `alt_m`: `pa.float64()`
  - `heading_deg`: `pa.float32()`
  - `speed_ms`: `pa.float32()`
  - `battery_pct`: `pa.float32()`
  - `flight_status`: `pa.string()`
  - `target_class`: `pa.string()`
  - `confidence`: `pa.float32()`
  - `snapshot_uri`: `pa.string()`
  - `mission_id`: `pa.string()`
  - `replayed`: `pa.bool_()`
  - `extra_json`: `pa.string()`

---

## 5. Visual Evidence Objects (MinIO `tactical-snapshots` bucket)

- **Key Path**: `projects/{project_id}/swarms/{swarm_id}/drones/{drone_id}/{event_id}.jpg`
- **Content-Type**: `image/jpeg`
- **Access Model**: Private bucket (`minio:9000` internal network only). Tactical Dashboard accesses evidence solely via ISC Backend authenticated endpoint `/api/v1/analytics/detections/{event_id}/snapshot` (`FR-008`).

---

## 6. Memgraph Property Graph Schema (`src/uservice/threat/`)

Queried over Bolt (`memgraph:7687`) via openCypher with `project_id` predicate scoping on every read/write.

### 6.1 Node Labels & Properties

| Label | Unique Key | Properties | Lifecycle / Notes |
|---|---|---|---|
| `:TacticalProject` | `project_id` | `project_id: str`, `name: str`, `created_at: datetime` | Auto-merged on first write (`MERGE`) |
| `:ThreatZone` | `threat_id` | `threat_id: str (UUID)`, `project_id: str`, `name: str`, `threat_type: str` (`"SAM"\|"EW"\|"AA"\|"RESTRICTED"\|"WEATHER"`), `severity: str` (`"critical"\|"high"\|"medium"`), `lat: float`, `lon: float`, `location: Point` (Memgraph WGS84 `{latitude, longitude}`), `radius_m: float`, `min_alt_m: float`, `max_alt_m: float`, `polygon_wkt: str \| None`, `active: bool` (default `true`), `source: str`, `created_at: datetime`, `created_by: str`, `deactivated_at: datetime \| None`, `deactivated_by: str \| None`, `deactivation_reason: str \| None` | **No automatic TTL**; `active` only becomes `false` on manual deactivation (`FR-006`) |
| `:SwarmMission` | `command_id` | `command_id: str`, `order_id: str`, `project_id: str`, `swarm_id: str`, `mission_type: str`, `status: str`, `altitude_m: float`, `target_area_geojson: str`, `created_at: datetime` | Synced during SMEAC verification |
| `:DroneUnit` | `(project_id, swarm_id, drone_id)` | `drone_id: str`, `swarm_id: str`, `project_id: str`, `last_seen_at: datetime` | Merged on telemetry/detection ingest |
| `:DetectionEvent` | `event_id` | `event_id: str`, `project_id: str`, `swarm_id: str`, `drone_id: str`, `mission_id: str \| None`, `target_class: str`, `confidence: float`, `lat: float`, `lon: float`, `alt_m: float`, `location: Point`, `snapshot_uri: str \| None`, `detected_at: datetime` | Immutable observation node |
| `:TargetEntity` | `target_id` | `target_id: str (UUID)`, `project_id: str`, `canonical_class: str`, `status: str` (`"auto_correlated"\|"confirmed"\|"split"\|"neutralized"`), `first_seen_at: datetime`, `last_seen_at: datetime`, `last_lat: float`, `last_lon: float`, `observation_count: int` | Aggregated multi-mission tracked entity (`FR-007`) |

### 6.2 Relationships

| Relationship | Direction | Properties | Semantics |
|---|---|---|---|
| `SCOPED_TO` | `(:ThreatZone \| :SwarmMission \| :TargetEntity)-[:SCOPED_TO]->(:TacticalProject)` | — | Theater isolation boundary |
| `INTERSECTS_THREAT` | `(:SwarmMission)-[:INTERSECTS_THREAT]->(:ThreatZone)` | `distance_m: float`, `detected_at: datetime`, `overridden: bool`, `override_rationale: str \| None`, `hitl_decision_id: str \| None` | Provenance of gated safety conflict & override audit |
| `OBSERVED` | `(:DroneUnit)-[:OBSERVED]->(:DetectionEvent)` | `detected_at: datetime` | Sensor platform provenance |
| `CAPTURED_DURING` | `(:DetectionEvent)-[:CAPTURED_DURING]->(:SwarmMission)` | — | Mission-to-detection traceability |
| `ATTRIBUTED_TO` | `(:DetectionEvent)-[:ATTRIBUTED_TO]->(:TargetEntity)` | `match_method: str` (`"auto_spatio_temporal" \| "analyst_confirmed"`), `distance_m: float`, `delta_s: float`, `verified_by_analyst: bool`, `reviewed_by: str \| None`, `reviewed_at: datetime \| None` | Automated + human-reviewed target lineage (`FR-007`) |

### 6.3 Correlation Matching Rule (`TargetEntity` Auto-Lineage)
Upon ingesting `DetectionEvent` `(project_id, target_class, lat, lon, detected_at)`:
1. Query candidate `:TargetEntity` nodes where `project_id == event.project_id` AND `toLower(canonical_class) == toLower(event.target_class)` AND `duration.between(last_seen_at, event.detected_at).seconds <= CORRELATION_WINDOW_S` (default `3600s`) AND `point.distance(point({latitude: last_lat, longitude: last_lon}), point({latitude: event.lat, longitude: event.lon})) <= CORRELATION_RADIUS_M` (default `250.0m`).
2. Select closest spatial-temporal match (`ORDER BY distance_m ASC, delta_s ASC LIMIT 1`), create `(:DetectionEvent)-[:ATTRIBUTED_TO {match_method: "auto_spatio_temporal", ...}]->(target)`, and update `target.last_seen_at`, `last_lat`, `last_lon`, `observation_count += 1`.
3. If no match exists, create a new `TargetEntity` with `status = "auto_correlated"` and `observation_count = 1`.

---

## 7. State Transitions: `SmeacOrder` Verification & HITL Override

```text
  [Copilot /api/v1/smeac/draft]
         │ (never auto-executes)
         ▼
       DRAFT ──(Commander clicks Submit)──► SUBMITTED ──► TRANSLATED
                                                              │
                                                              ▼
                                                  [safety_check_activity]
                                           ┌──────────────────┴──────────────────┐
                                  No violations                      Static OR Dynamic Threat
                                  (full_graph OK)                    OR deterministic_fallback
                                           │                         (high-impact / unsafe / conflict)
                                           ▼                                     │
                                       VERIFIED                                  ▼
                                           │                               PENDING_HITL
                               (non-high-impact)                     ┌───────────┴───────────┐
                                           │                 (Reject / Blank       (Approve + valid
                                           │                  rationale -> 422)     override justification)
                                           │                         │                       │
                                           ▼                         ▼                       ▼
                                       EXECUTING                 REJECTED                EXECUTING
                                                                                     (Audit + Memgraph
                                                                                      override recorded)
```
