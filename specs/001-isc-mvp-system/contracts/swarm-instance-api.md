# Contract: Dedicated Swarm Instance API

**Service**: Swarm Controller (`src/swarm_controller/`) | **Base URL**: `http://gateway:8000/api/v1/swarms/{swarm_id}`

All requests routed through the MCP Auth Gateway. Requires a valid OAuth 2.1 JWT with swarm-scoped permissions.

## Endpoints

### POST /api/v1/swarms/{swarm_id}/orders

Submit a SMEAC order to this swarm's dedicated controller.

**Request**:
```json
{
  "situation": "Enemy AA battery detected at grid 123456. Weather: clear.",
  "mission": "Conduct ISR sweep of grid square 1234.",
  "execution": "Deploy 4-drone recon formation in diamond pattern. Altitude 200m.",
  "admin_logistics": "Return to base on fuel < 20%.",
  "command_signal": "Primary freq 123.4 MHz. Backup: 456.7 MHz."
}
```

**Response** (201 Created):
```json
{
  "order_id": "uuid-order-001",
  "status": "submitted",
  "swarm_instance_id": "uuid-swarm-001",
  "parsed_fields": {
    "situation": "parsed",
    "mission": "parsed",
    "execution": "parsed",
    "admin_logistics": "parsed",
    "command_signal": "parsed"
  },
  "created_at": "2026-07-24T19:05:00Z"
}
```

**Response** (422 Validation Error):
```json
{
  "error": "Incomplete SMEAC order",
  "missing_fields": ["situation", "mission"],
  "message": "Fields 'situation' and 'mission' are required."
}
```

### GET /api/v1/swarms/{swarm_id}/orders/{order_id}

Get the status and details of a submitted SMEAC order, including generated commands.

**Response** (200 OK):
```json
{
  "order_id": "uuid-order-001",
  "status": "verified",
  "commands": [
    {
      "id": "uuid-cmd-001",
      "mission_type": "recon",
      "formation_type": "diamond",
      "target_area": {"type": "Point", "coordinates": [12.3456, 56.7890]},
      "drone_count": 4,
      "altitude_m": 200.0,
      "is_high_impact": false,
      "verification_status": "passed"
    }
  ],
  "constraint_violations": []
}
```

### GET /api/v1/swarms/{swarm_id}/orders/{order_id}/commands

List all generated swarm commands for an order.

### POST /api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide

Submit a HITL decision for a pending high-impact action.

**Request**:
```json
{
  "decision": "approved",
  "rationale": "ROE change authorized by battalion commander."
}
```

**Response** (200 OK):
```json
{
  "decision_id": "uuid-decision-001",
  "decision": "approved",
  "command_status": "executing",
  "decided_at": "2026-07-24T19:10:00Z"
}
```

### GET /api/v1/swarms/{swarm_id}/hitl/pending

List all pending HITL decisions for this swarm.

**Response** (200 OK):
```json
{
  "pending": [
    {
      "decision_id": "uuid-decision-002",
      "command_id": "uuid-cmd-002",
      "action_summary": "ROE change: Weapons free → Weapons hold",
      "affected_drones": ["UAV-Alpha-1", "UAV-Alpha-2"],
      "timeout_seconds": 120,
      "requested_at": "2026-07-24T19:08:00Z"
    }
  ]
}
```

### GET /api/v1/swarms/{swarm_id}/telemetry

Get simulated drone telemetry for the tactical map.

**Response** (200 OK):
```json
{
  "swarm_id": "uuid-swarm-001",
  "drones": [
    {
      "id": "UAV-Alpha-1",
      "position": {"lat": 52.5200, "lng": 13.4050, "alt_m": 200.0},
      "status": "executing",
      "battery_pct": 85,
      "current_mission": "recon"
    }
  ],
  "timestamp": "2026-07-24T19:12:00Z"
}
```

### WebSocket /api/v1/swarms/{swarm_id}/ws

Real-time event stream for this swarm (telemetry updates, HITL requests, status changes).

**Message Types**:
```json
{"type": "telemetry_update", "data": { ... }}
{"type": "hitl_request", "data": { ... }}
{"type": "order_status_change", "data": { ... }}
{"type": "constraint_violation", "data": { ... }}
```

## Error Responses

| Status | Condition |
|--------|-----------|
| 401 | Missing or invalid JWT |
| 403 | Insufficient scope for this swarm |
| 404 | Swarm instance or order not found |
| 409 | Order already in terminal state |
| 422 | Invalid SMEAC fields |
| 503 | Swarm instance not ready |
