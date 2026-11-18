# Data Model: Edge-Autonomous Obstacle Detection and Avoidance

**Feature**: `011-edge-obstacle-avoidance` | **Date**: 2026-11-17

## Entities

### 1. MissionTargetSpec (Edge Input / Order Context)
Represents the active mission order's target specification delivered to the edge node.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `command_id` | `string` | Required | Active mission/order command identifier |
| `target_object_class` | `string` | Required, non-empty | Ordered target class or semantic description (e.g., `"truck"`, `"person"`) |
| `target_attributes` | `dict[str, str] \| None` | Optional | Optional attributes (color, type, markings) for LLM matching |
| `confidence_threshold` | `float` | `0.0 < x <= 1.0`, default `0.5` | Minimum vision detection confidence |
| `detection_mode` | `enum` | `"intercept" \| "observe"` | Behavior when ordered target is confirmed |

### 2. CorridorDetection (Edge Perception)
Extends `Detection` with spatial corridor metrics computed from the frame.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `detection_id` | `UUID` | Generated per event | Unique identifier linking detection to avoidance command |
| `class_name` | `string` | Required | Detected object class label from vision model |
| `confidence` | `float` | `0.0 <= x <= 1.0` | Vision detector confidence |
| `bbox` | `tuple[int, int, int, int]` | `(x1, y1, x2, y2)` | Bounding box in pixel coordinates |
| `center` | `tuple[int, int]` | `(cx, cy)` | Center pixel of bounding box |
| `area_ratio` | `float` | `0.0 <= x <= 1.0` | Fraction of frame area occupied (proximity proxy) |
| `in_forward_corridor` | `bool` | Derived | True if `bbox` overlaps the central forward flight corridor |

### 3. TargetClassificationResult (Edge LLM Output)
Structured output from the edge LLM target-vs-obstacle matcher.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `detected_class` | `string` | Required | Object class evaluated |
| `is_ordered_target` | `bool` | Required | `True` if object matches `MissionTargetSpec`; `False` if obstacle |
| `confidence` | `float` | `0.0 <= x <= 1.0` | LLM semantic match confidence |
| `rationale` | `string` | Required | Short explanation of match or mismatch |
| `evaluated_by` | `string` | `"edge_llm"` | Provenance of classification decision |

**Validation / Fail-Safe Rule**: If `is_ordered_target` is `True` but `confidence < 0.7`, treat as `False` (non-target obstacle) to prevent collision on ambiguous matches.

### 4. EdgeAvoidanceCommand (Edge Flight Action & Provenance)
Represents an autonomous course modification ordered by the edge system.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `command_source` | `string` | Fixed `"edge_autonomous"` | Proves command originated from edge autonomy |
| `decision_authority` | `string` | Fixed `"edge"` | Authority identifier distinguishing from operator/C2 |
| `action` | `enum` | `"obstacle_bypass" \| "resume_route" \| "obstructed_hold"` | Maneuver ordered by edge |
| `obstacle_class` | `string \| None` | Required for bypass | Class of obstacle triggering maneuver |
| `bypass_direction` | `enum \| None` | `"left" \| "right" \| None` | Chosen clearest lateral direction |
| `previous_heading_deg` | `float` | `0.0 <= x < 360.0` | Drone heading prior to command |
| `commanded_heading_deg` | `float` | `0.0 <= x < 360.0` | New heading ordered by edge |
| `course_delta_deg` | `float` | `-180.0 <= x <= 180.0` | Signed heading change ordered |
| `trigger_detection_id` | `UUID \| None` | Optional | Links to `CorridorDetection.detection_id` |
| `timestamp` | `datetime (UTC)` | ISO-8601 | Time command was issued |

### 5. Flight Telemetry & Audit Projection (C2 / Dashboard)
- **MQTT Event (`SwarmTelemetryEvent`)**: Published on `telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/alert` (QoS 1) with `flight_status = "bypassing" | "resuming" | "obstructed_hold"` and `extra` containing serialized `EdgeAvoidanceCommand` fields.
- **PostgreSQL `AuditEvent`**: Persisted by `TelemetryIngestor` with `actor_type = ActorType.AGENT`, `actor_id = "edge:{drone_id}"`, `details` containing the `EdgeAvoidanceCommand` provenance payload, and exposed to the dashboard audit/telemetry view.

## Navigation State Transitions

```text
searching ──(target confirmed by LLM)──────────────▶ approaching ──(dist <= 5m)──▶ arrived
   ▲   │                                                │
   │   └──(non-target obstacle in corridor)─────────────▼
   │                                                bypassing
   │                                                    │
   │                    (corridor blocked / feed lost)──┼──▶ obstructed_hold
   │                                                    │
   └──────────────────(route resumed)◀──── resuming ◀───┘ (obstacle cleared)
```
