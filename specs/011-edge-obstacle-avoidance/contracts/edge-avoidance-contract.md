# Interface Contracts: Edge-Autonomous Obstacle Detection and Avoidance

**Feature**: `011-edge-obstacle-avoidance` | **Date**: 2026-11-17

## 1. Edge API Contract (`src/edge/api/server.py`)

### `POST /target` (Extended)
Accepts the active mission target specification and optional obstacle-avoidance configuration.

```json
{
  "target_object_class": "truck",
  "target_attributes": {"color": "military green"},
  "command_id": "cmd-001",
  "confidence_threshold": 0.5,
  "detection_mode": "intercept",
  "drone_id": "drone-1",
  "obstacle_avoidance_enabled": true
}
```

- `target_attributes`: Optional key-value map passed to the edge LLM for semantic target-vs-obstacle matching.
- `obstacle_avoidance_enabled`: Boolean (default `true`). When enabled, `FlightController` evaluates all frame detections above threshold, delegates target-vs-obstacle classification to the edge LLM, and executes dynamic lateral bypass for non-target obstacles.

### `GET /telemetry` (Extended)
Returns live edge state including current avoidance status and latest edge avoidance command if active:

```json
{
  "status": "bypassing",
  "battery": 98,
  "position": {"lat": 47.3977, "lon": 8.5456, "alt": 505.0, "rel_alt": 15.0},
  "heading": 120.0,
  "speed": 5.0,
  "armed": true,
  "in_air": true,
  "last_avoidance_command": {
    "command_source": "edge_autonomous",
    "decision_authority": "edge",
    "action": "obstacle_bypass",
    "obstacle_class": "traffic light",
    "bypass_direction": "right",
    "previous_heading_deg": 45.0,
    "commanded_heading_deg": 120.0,
    "course_delta_deg": 75.0
  }
}
```

## 2. MQTT Telemetry Event Contract (`SwarmTelemetryEvent`)

**Topic**: `telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/alert`  
**QoS**: `1` (guaranteed delivery + SQLite WAL DDIL spooling)

```json
{
  "schema_version": "1.0",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-11-17T22:30:00Z",
  "project_id": "default-theater",
  "swarm_id": "swarm-1",
  "drone_id": "drone-1",
  "metric_type": "alert",
  "lat": 47.397742,
  "lon": 8.545594,
  "alt_m": 505.0,
  "heading_deg": 120.0,
  "speed_ms": 5.0,
  "battery_pct": 98.0,
  "flight_status": "bypassing",
  "target_class": "lamp post",
  "confidence": 0.86,
  "bbox": [280, 110, 360, 420],
  "mission_id": "cmd-001",
  "replayed": false,
  "extra": {
    "command_source": "edge_autonomous",
    "decision_authority": "edge",
    "action": "obstacle_bypass",
    "obstacle_class": "lamp post",
    "bypass_direction": "right",
    "previous_heading_deg": 45.0,
    "commanded_heading_deg": 120.0,
    "course_delta_deg": 75.0,
    "trigger_detection_id": "7b2c1a00-0000-4000-8000-000000000001",
    "llm_matched_target": false
  }
}
```

## 3. C2 Backend Telemetry & Audit Contract (`src/uservice`)

### `GET /api/v1/swarms/{swarm_id}/telemetry`
- Includes `last_avoidance_event` / `flight_status` per drone in the live telemetry projection when an edge-autonomous avoidance event has been ingested.

### `GET /api/v1/swarms/{swarm_id}/audit` (or `AuditEvent` query)
- Persists an `AuditEvent` whenever `TelemetryIngestor` receives an `alert` event with `extra.command_source == "edge_autonomous"`:
  - `event_type`: `command_executed` (`AuditEventType.COMMAND_EXECUTED`)
  - `actor_type`: `agent` (`ActorType.AGENT`)
  - `actor_id`: `edge:{drone_id}`
  - `details`: Full `extra` provenance payload (`command_source`, `decision_authority`, `action`, `obstacle_class`, `bypass_direction`, `course_delta_deg`, `previous_heading_deg`, `commanded_heading_deg`).
