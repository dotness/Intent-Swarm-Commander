# Interface Contracts: Gradual Corridor Path Discovery and Adaptive Survey

**Feature**: `012-corridor-path-discovery` | **Date**: `2026-11-19` | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/spec.md)

## 1. SMEAC Order Intake Contract (`src/uservice/smeac/`)

### `POST /api/v1/swarms/{swarm_id}/orders` (Extended for Coordinate-Free Corridor Surveys)
**Auth**: Bearer JWT (`smeac:create` scope required)

**Request Payload** (Coordinate-Free Example):
```json
{
  "project_id": "default-theater",
  "situation": "Unmapped subterranean industrial corridor ahead of lead drone.",
  "mission": "Go check the corridor next 20 meters and go back; report hazards or vehicles.",
  "execution": "Enter adaptive corridor survey mode, look around before advancing, adapt to turns and low overhangs."
}
```

**Response Payload (`201 Created`)**:
```json
{
  "data": {
    "order_id": "22222222-2222-4222-8222-222222222222",
    "project_id": "default-theater",
    "status": "translated",
    "swarm_instance_id": "11111111-1111-4111-8111-111111111111",
    "parsed_fields": {
      "situation": "parsed",
      "mission": "parsed",
      "execution": "parsed",
      "admin_logistics": "not_provided",
      "command_signal": "not_provided"
    },
    "created_at": "2026-11-19T12:15:00Z",
    "commands": [
      {
        "id": "33333333-3333-4333-8333-333333333333",
        "mission_type": "corridor_survey",
        "formation_type": "line",
        "target_area": {
          "type": "RelativeCorridor",
          "coordinates": []
        },
        "target_object_class": "vehicle",
        "drone_count": 3,
        "altitude_m": 2.5,
        "is_high_impact": false,
        "verification_status": "verified",
        "survey_id": "44444444-4444-4444-8444-444444444444",
        "lead_scout_drone_id": "drone-1",
        "staging_hold_drone_ids": ["drone-2", "drone-3"],
        "survey_params": {
          "target_distance_m": 20.0,
          "distance_defaulted": false,
          "return_to_origin": true,
          "corridor_descriptor": "subterranean industrial corridor",
          "intelligence_focus": ["vehicle", "hazard"],
          "min_altitude_m": 1.2,
          "max_altitude_m": 8.0,
          "cruise_speed_ms": 1.5
        }
      }
    ],
    "reasoning": "Coordinate-free corridor survey of 20m with return-to-origin assigned to lead scout drone-1.",
    "threat_conflicts": [],
    "pending_hitl_decision_id": null
  }
}
```

**Defaults & Validation Errors (`422 Unprocessable Entity`)**:
- When `altitude_m` is omitted (`null`), it defaults to `clamp(2.5, min_altitude_m, max_altitude_m)` and is propagated as `entry_altitude_m` to the edge node (`FR-021`).
- Returns `422 Unprocessable Entity` immediately if `target_distance_m <= 0` (`FR-001`), if `min_altitude_m >= max_altitude_m`, or if an explicitly ordered `altitude_m` falls outside `[min_altitude_m, max_altitude_m]` (`FR-021`):
```json
{
  "detail": "target_distance_m must be strictly positive (> 0); received 0.0"
}
```

---

## 2. Edge Node Corridor Survey Contract (`src/edge/api/server.py`)

### `POST /corridor-survey/start`
Launches `CorridorSurveyController` exclusively on `drone_id` (`lead_scout_drone_id`) at `entry_altitude_m`. For every drone in `staging_hold_drone_ids`, `src/edge/api/server.py` actively stops/cancels any pre-existing vision or navigation tasks, holds the drone safely at staging (`FR-019`), and publishes `flight_status = "survey_staging_hold"` telemetry.

```json
{
  "survey_id": "44444444-4444-4444-8444-444444444444",
  "command_id": "33333333-3333-4333-8333-333333333333",
  "swarm_id": "11111111-1111-4111-8111-111111111111",
  "project_id": "default-theater",
  "drone_id": "drone-1",
  "staging_hold_drone_ids": ["drone-2", "drone-3"],
  "entry_altitude_m": 2.5,
  "target_distance_m": 20.0,
  "distance_defaulted": false,
  "return_to_origin": true,
  "corridor_descriptor": "corridor",
  "intelligence_focus": ["vehicle"],
  "min_altitude_m": 1.2,
  "max_altitude_m": 8.0,
  "cruise_speed_ms": 1.5,
  "look_around_steps": 8,
  "snapshot_interval_s": 0.4,
  "guidance_timeout_s": 5.0
}
```
- **Response (`200 OK`)**:
```json
{
  "status": "accepted",
  "survey_id": "44444444-4444-4444-8444-444444444444",
  "drone_id": "drone-1",
  "staging_hold_drone_ids": ["drone-2", "drone-3"],
  "phase": "initial_look_around"
}
```

### `POST /corridor-survey/{survey_id}/recall`
Signals `CorridorSurveyController.recall()`, ending outbound discovery and immediately starting reverse-path return along verified 3D breadcrumbs (`FR-018`).
- **Response (`200 OK`)**: `{"status": "recalling", "survey_id": "...", "phase": "returning"}`
- **Error (`404 Not Found`)**: if `survey_id` is not active on this edge node.

### `POST /corridor-survey/{survey_id}/emergency-abort`
Signals `CorridorSurveyController.emergency_abort()`, invoking immediate MAVSDK `action.hold()` in place (`FR-018`).
- **Response (`200 OK`)**: `{"status": "aborted", "survey_id": "...", "phase": "emergency_hold"}`

### `GET /corridor-survey/{survey_id}/status`
Returns live edge state for the survey (`phase`, `surveyed_distance_m`, `rel_pose`, `heading_deg`, `snapshot_count`, `decision_count`, `completion_reason`, `last_instruction`).

### `GET /telemetry` (Extended)
Includes `"active_corridor_survey"` summary block whenever a corridor survey controller is active or recently finished on the edge node (existing fields remain unchanged).

---

## 3. MQTT Telemetry & Provenance Contract (`SwarmTelemetryEvent`)

**Topic**: `telemetry/projects/{project_id}/swarms/{swarm_id}/{drone_id}/alert`  
**QoS**: `1` (live-first publish with SQLite WAL `EdgeSpool` DDIL durability)

Every corridor survey event uses canonical `SwarmTelemetryEvent` (`metric_type: "alert"`, `schema_version: "1.0"`) with `extra.command_source` set to `"edge_corridor_survey"` (or `"operator_corridor_override"`), leaving `is_edge_autonomous_alert()` dedicated exclusively to Feature 011 obstacle avoidance. Telemetry `flight_status` follows the canonical 1-to-1 `f"survey_{phase}"` mapping (plus `"survey_staging_hold"` for held staging drones) defined in [data-model.md Section 5.1](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/data-model.md#L192).

### 3.1 `corridor_snapshot` (Emitted for **Every** Captured Snapshot — `FR-020`)
```json
{
  "schema_version": "1.0",
  "event_id": "55555555-5555-4555-8555-555555555555",
  "timestamp": "2026-11-19T12:15:03.200Z",
  "project_id": "default-theater",
  "swarm_id": "11111111-1111-4111-8111-111111111111",
  "drone_id": "drone-1",
  "metric_type": "alert",
  "lat": 47.39775,
  "lon": 8.54561,
  "alt_m": 502.3,
  "heading_deg": 90.0,
  "speed_ms": 1.4,
  "battery_pct": 94.0,
  "flight_status": "survey_outbound_discovery",
  "snapshot_uri": "s3://tactical-snapshots/projects/default-theater/swarms/11111111-1111-4111-8111-111111111111/corridor-surveys/44444444-4444-4444-8444-444444444444/drones/drone-1/66666666-6666-4666-8666-666666666666.jpg",
  "mission_id": "33333333-3333-4333-8333-333333333333",
  "replayed": false,
  "extra": {
    "command_source": "edge_corridor_survey",
    "decision_authority": "edge",
    "survey_event_type": "corridor_snapshot",
    "survey_id": "44444444-4444-4444-8444-444444444444",
    "snapshot_id": "66666666-6666-4666-8666-666666666666",
    "sequence_num": 9,
    "phase": "outbound_discovery",
    "rel_x_m": 6.4,
    "rel_y_m": 0.2,
    "rel_z_m": 2.3,
    "cumulative_distance_m": 6.41,
    "visual_confidence": 0.91,
    "corridor_open": true,
    "estimated_width_m": 3.4,
    "estimated_height_m": 2.8,
    "analysis_latency_ms": 48.2,
    "byte_size": 31420,
    "structural_tags": ["turn_right"],
    "findings": []
  }
}
```

### 3.2 `corridor_trajectory` (Emitted on Every Edge Trajectory Issuance/Modification — `FR-014`)
```json
{
  "command_source": "edge_corridor_survey",
  "decision_authority": "edge",
  "survey_event_type": "corridor_trajectory",
  "survey_id": "44444444-4444-4444-8444-444444444444",
  "decision_id": "77777777-7777-4777-8777-777777777777",
  "sequence_num": 3,
  "action": "trajectory_update",
  "from_phase": "outbound_discovery",
  "to_phase": "outbound_discovery",
  "target_rel_x_m": 9.8,
  "target_rel_y_m": 3.6,
  "target_rel_z_m": 1.9,
  "commanded_heading_deg": 135.0,
  "cleared_distance_m": 4.0,
  "speed_ms": 1.2,
  "trigger_snapshot_ids": ["66666666-6666-4666-8666-666666666666"],
  "analysis_latency_ms": 48.2,
  "rationale": "Corridor turns right (+45 deg) with ceiling overhang; descending to 1.9m within [1.2m, 8.0m] envelope.",
  "breadcrumb": {
    "index": 3,
    "rel_x_m": 6.4,
    "rel_y_m": 0.2,
    "rel_z_m": 2.3,
    "heading_deg": 90.0,
    "cumulative_distance_m": 6.41,
    "estimated_width_m": 3.4,
    "estimated_height_m": 2.8,
    "snapshot_id": "66666666-6666-4666-8666-666666666666"
  }
}
```

### 3.3 `corridor_phase` (Emitted on Every Survey State Transition & Staging Hold)
Carried inside `SwarmTelemetryEvent.extra` (with outer `flight_status` set to `f"survey_{to_phase}"` or `"survey_staging_hold"` per [data-model.md Section 5.1](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/data-model.md#L192)):
```json
{
  "command_source": "edge_corridor_survey",
  "decision_authority": "edge",
  "survey_event_type": "corridor_phase",
  "survey_id": "44444444-4444-4444-8444-444444444444",
  "from_phase": "initial_look_around",
  "to_phase": "outbound_discovery",
  "flight_status": "survey_outbound_discovery",
  "reason": "Validated open corridor heading 90.0 deg after 8-step 360-deg origin sweep",
  "rel_x_m": 0.0,
  "rel_y_m": 0.0,
  "rel_z_m": 2.5,
  "heading_deg": 90.0,
  "cumulative_distance_m": 0.0,
  "staging_hold_drone_ids": ["drone-2", "drone-3"]
}
```

### 3.4 `corridor_report` (Emitted upon Completion or Early Termination — `SC-006`)
Carried inside `SwarmTelemetryEvent.extra` when the survey finishes or terminates early (`completion_reason` matches [data-model.md Section 2.1](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/data-model.md#L53)):
```json
{
  "command_source": "edge_corridor_survey",
  "decision_authority": "edge",
  "survey_event_type": "corridor_report",
  "survey_id": "44444444-4444-4444-8444-444444444444",
  "status": "completed",
  "completion_reason": "distance_reached",
  "surveyed_distance_m": 20.15,
  "requested_distance_m": 20.0,
  "distance_defaulted": false,
  "discovered_path": [
    {
      "index": 1,
      "rel_x_m": 0.0,
      "rel_y_m": 0.0,
      "rel_z_m": 2.5,
      "heading_deg": 90.0,
      "cumulative_distance_m": 0.0,
      "estimated_width_m": 3.4,
      "estimated_height_m": 2.9,
      "snapshot_id": "66666666-6666-4666-8666-666666666666"
    }
  ],
  "structural_features": ["turn_right", "low_overhang"],
  "unexplored_branches": [],
  "snapshot_count": 32,
  "decision_count": 11,
  "finding_count": 2
}
```

### 3.5 `corridor_override` (Emitted on Two-Tier Operator Recall or Emergency Abort — `FR-014`, `FR-018`)
Carried inside `SwarmTelemetryEvent.extra` upon operator override command provenance:
```json
{
  "command_source": "operator_corridor_override",
  "decision_authority": "commander",
  "survey_event_type": "corridor_override",
  "survey_id": "44444444-4444-4444-8444-444444444444",
  "override_type": "recall",
  "commander_id": "commander-1",
  "from_phase": "outbound_discovery",
  "to_phase": "returning",
  "rationale": "Operator initiated safe reverse-path recall via C2 dashboard.",
  "requested_at": "2026-11-19T12:16:04.500Z"
}
```
(`override_type` is `"recall"` or `"emergency_abort"`, with `"to_phase"` equal to `"returning"` or `"emergency_hold"` respectively.)

---

## 4. Central C2 Corridor Survey & Intelligence API (`src/uservice/corridor/api/routes.py`)

All routes enforce JWT auth + RBAC scopes and verify `survey.swarm_instance_id == swarm_id` + `project_id` match (returning `404` on mismatch to prevent IDOR).

| Endpoint | Method | Scope | Description |
|----------|--------|-------|-------------|
| `/api/v1/swarms/{swarm_id}/corridor-surveys` | `GET` | `swarm:read` | List corridor surveys for the swarm (ordered newest first) |
| `/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}` | `GET` | `swarm:read` | Return live progress and full `CorridorIntelligenceReport` (3D path, elevation profile, all snapshots, findings, branches, decision provenance) |
| `/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/snapshots/{snapshot_id}/image` | `GET` | `swarm:read` | Authenticated BFF proxy fetching JPEG from MinIO with `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store` |
| `/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/recall` | `POST` | `smeac:create` | Two-tier Recall: forward recall to edge `/corridor-survey/{survey_id}/recall`, log `AuditEvent` (`commander`), mark recall requested (`FR-018`) |
| `/api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}/emergency-abort` | `POST` | `smeac:create` | Two-tier Emergency Abort: forward emergency hold to edge `/corridor-survey/{survey_id}/emergency-abort`, log `AuditEvent` (`commander`) (`FR-018`) |

**`GET /api/v1/swarms/{swarm_id}/corridor-surveys/{survey_id}` Response Summary**:
```json
{
  "data": {
    "survey_id": "44444444-4444-4444-8444-444444444444",
    "swarm_id": "11111111-1111-4111-8111-111111111111",
    "project_id": "default-theater",
    "lead_scout_drone_id": "drone-1",
    "staging_hold_drone_ids": ["drone-2", "drone-3"],
    "corridor_descriptor": "subterranean industrial corridor",
    "requested_distance_m": 20.0,
    "distance_defaulted": false,
    "surveyed_distance_m": 20.15,
    "return_to_origin": true,
    "min_altitude_m": 1.2,
    "max_altitude_m": 8.0,
    "phase": "completed",
    "status": "completed",
    "completion_reason": "distance_reached",
    "discovered_path": [ ... ],
    "structural_features": [ ... ],
    "unexplored_branches": [ ... ],
    "snapshots": [
      {
        "snapshot_id": "...",
        "sequence_num": 1,
        "phase": "initial_look_around",
        "captured_at": "...",
        "rel_x_m": 0.0,
        "rel_y_m": 0.0,
        "rel_z_m": 2.5,
        "heading_deg": 0.0,
        "cumulative_distance_m": 0.0,
        "visual_confidence": 0.94,
        "corridor_open": false,
        "analysis_latency_ms": 34.5,
        "image_proxy_url": "/api/v1/swarms/11111111-1111-4111-8111-111111111111/corridor-surveys/44444444-4444-4444-8444-444444444444/snapshots/.../image"
      }
    ],
    "decisions": [ ... ],
    "findings": [ ... ]
  }
}
```

---

## 5. Virtual Camera Corridor Scene Control Contract (`scripts/virtual_cam_server.py`)

Used strictly in local simulation / E2E verification (`FR-017`):
- `POST /feed/{drone_id}` supports `"mode": "corridor_scene"` with `"scenario"`: `"straight_20m" | "l_turn_20m" | "s_bend_overhang_20m" | "dead_end_12m" | "branch_junction_20m" | "enclosed_start"`, plus optional `"target_object_asset"` / `"dynamic_return_block"`.
- **Automatic Live MQTT Pose Sync**: In `docker-compose.yml`, the `virtual_cam` service receives `MQTT_BROKER_HOST` and `MQTT_BROKER_PORT` (`depends_on: [mosquitto]`). When running `corridor_scene`, `scripts/virtual_cam_server.py` subscribes directly to local Mosquitto telemetry (`telemetry/projects/+/swarms/+/+/navigation` and `telemetry/projects/+/swarms/+/+/alert`), anchors each active drone/survey's initial ENU coordinates at survey start, and updates the rendered 3D corridor perspective view automatically as the PX4 SITL drone moves — keeping `src/edge/` 100% simulation-unaware.
- **Direct Test Override (Optional)**: `POST /pose/{drone_id}` remains supported (`{"rel_x_m": float, "rel_y_m": float, "rel_z_m": float, "heading_deg": float}`) as an optional direct override for deterministic single-frame or hermetic tests without MQTT.
