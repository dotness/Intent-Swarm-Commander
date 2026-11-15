# Contract: Edge-to-C2 Push MQTT Telemetry Protocol

**Protocol**: MQTT v3.1.1 / v5.0 over TCP (`mosquitto:1883` inside `c2-shared-net`)
**Producers**: Edge Swarm Drone Controllers (`src/edge/telemetry/publisher.py`)
**Consumers**: ISC Backend MQTT Ingestor (`src/uservice/telemetry/operations/ingestor.py`)
**Spec Traceability**: `FR-001`, `FR-002`, `FR-003`, `FR-004`, `FR-007`, `FR-012`, `FR-013`, `SC-001`, `SC-002`, `SC-006`

---

## 1. Topic Hierarchy

All telemetry and sensor events use the scoped topic pattern:

```text
telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/{metric}
```

- `{project_id}`: Tactical theater slug (`^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`; defaults to `"default-theater"`).
- `{swarm_id}`: UUID of the `SwarmInstance`.
- `{drone_id}`: Drone identifier within the swarm (e.g., `drone-1`).
- `{metric}`: One of `navigation`, `battery`, `health`, `detection`, `alert`.

ISC Backend subscribes using wildcard topic filter:
```text
telemetry/projects/+/swarms/+/+/+
```

---

## 2. QoS, Retain, and LWT Policy

| Metric (`{metric}`) | Spool Priority | MQTT QoS | Retain | Rate / Trigger |
|---|---|---|---|---|
| `navigation` | `0` (evictable under DDIL pressure) | `0` | `false` | 1–2 Hz continuous loop |
| `battery` (>= 20%) | `0` (evictable) | `0` | `false` | 0.2 Hz or state change |
| `battery` (< 20% critical) | `1` (preserved) | `1` | `false` | Immediate on threshold crossing |
| `health` (incl. LWT) | `0` (`1` if failure alert) | `0` (LWT: `1`) | `false` (LWT: `true`) | 0.2 Hz / connect & disconnect |
| `detection` | `1` (preserved) | `1` | `false` | Event-driven on YOLO-E detection |
| `alert` | `1` (preserved) | `1` | `false` | Link loss, geofence breach, DDIL spool warning |

**Last Will and Testament (LWT)**:
Each edge client registers an LWT on connect targeting `telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/health`:
```json
{
  "schema_version": "1.0",
  "event_id": "00000000-0000-0000-0000-000000000000",
  "project_id": "default-theater",
  "swarm_id": "550e8400-e29b-41d4-a716-446655440000",
  "drone_id": "drone-1",
  "metric_type": "health",
  "flight_status": "offline_lwt",
  "extra": {"lwt": true, "reason": "ungraceful_disconnect"}
}
```
*(Consumers treat incoming LWT timestamps cleanly as server-receipt UTC if edge clock wasn't stamped at disconnect.)*

---

## 3. Payload Schemas (`application/json`, UTF-8)

### 3.1 `navigation` Payload (`QoS 0`)
```json
{
  "schema_version": "1.0",
  "event_id": "9f3d8a22-6e10-4b2e-941c-0d6c2c38d111",
  "timestamp": "2026-11-14T20:15:02.412Z",
  "project_id": "default-theater",
  "swarm_id": "550e8400-e29b-41d4-a716-446655440000",
  "drone_id": "drone-1",
  "metric_type": "navigation",
  "lat": 52.52145,
  "lon": 13.40612,
  "alt_m": 120.5,
  "heading_deg": 84.2,
  "speed_ms": 14.8,
  "battery_pct": 87.0,
  "flight_status": "patrolling",
  "mission_id": "c7a1f440-9b3a-4d75-9a21-51a63e220001",
  "replayed": false
}
```

### 3.2 `detection` Payload (`QoS 1` Mandatory)
Published upon positive `YoloEInference` match above `confidence_threshold`. `snapshot_uri` points to the MinIO object uploaded prior to publish (or uploaded immediately before backlog flush during DDIL recovery).

```json
{
  "schema_version": "1.0",
  "event_id": "41b2c799-1c02-40ab-85b1-99e001122334",
  "timestamp": "2026-11-14T20:15:18.903Z",
  "project_id": "default-theater",
  "swarm_id": "550e8400-e29b-41d4-a716-446655440000",
  "drone_id": "drone-1",
  "metric_type": "detection",
  "lat": 52.52310,
  "lon": 13.40980,
  "alt_m": 115.0,
  "heading_deg": 90.0,
  "speed_ms": 10.2,
  "battery_pct": 85.4,
  "flight_status": "approaching",
  "mission_id": "c7a1f440-9b3a-4d75-9a21-51a63e220001",
  "target_class": "armored_vehicle",
  "confidence": 0.91,
  "bbox": [210, 145, 340, 260],
  "snapshot_uri": "s3://tactical-snapshots/projects/default-theater/swarms/550e8400-e29b-41d4-a716-446655440000/drones/drone-1/41b2c799-1c02-40ab-85b1-99e001122334.jpg",
  "replayed": false
}
```

### 3.3 `battery`, `health`, and `alert` Payloads
Carry the same base envelope (`schema_version`, `event_id`, `timestamp`, `project_id`, `swarm_id`, `drone_id`, `metric_type`, `lat`, `lon`, `alt_m`, `battery_pct`, `flight_status`, `replayed`) plus metric-specific `extra` dictionary:
- `health`: `extra = {"spool_depth": 0, "evicted_routine_count": 0, "camera_ok": true, "mavsdk_connected": true, "cpu_temp_c": 58.2}`
- `alert`: `extra = {"alert_code": "LOW_BATTERY" | "DDIL_SPOOL_PRESSURE" | "SENSOR_FAULT", "severity": "high" | "critical", "detail": "..."}`

---

## 4. DDIL Buffering, Eviction & Replay Ordering

1. **Outage Detection**: When `paho-mqtt` `is_connected()` is `false` or TCP/publish raises connection failure, `EdgeTelemetryPublisher` persists the exact JSON payload to SQLite `edge_spool` (with `priority=1` for `detection`/`alert` or `battery < 20%`, else `priority=0`).
2. **Capacity Overflow Eviction**: When `edge_spool` hits `EDGE_SPOOL_MAX_RECORDS` or `EDGE_SPOOL_MAX_BYTES`, oldest `priority = 0` (`navigation`, routine `battery`/`health`) rows are deleted first. High-priority `detection` and `alert` records are retained until explicitly drained or unrecoverable storage exhaustion occurs.
3. **Reconnect Live-First + Async Drain**:
   - **Live Stream First**: On MQTT `on_connect`, newly sampled live `navigation`, `detection`, and `alert` messages immediately transmit over the live client so commanders regain zero-lag awareness.
   - **Background Backlog Drain**: An asynchronous worker drains buffered rows (`ORDER BY priority DESC, created_at_utc ASC`) with `replayed: true`, throttled to avoid starving live frames.
4. **Consumer Idempotency**: ISC Backend deduplicates `event_id` within an in-memory rolling LRU set before Memgraph `DetectionEvent` `MERGE` and Parquet batch emission so QoS 1 re-deliveries never create duplicate target lineage nodes.
