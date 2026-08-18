# Contract: Central Provisioning API

**Service**: Provisioner (`src/provisioner/`) | **Base URL**: `http://gateway:8000/api/v1/swarms`

All requests routed through the MCP Auth Gateway. Requires a valid OAuth 2.1 JWT with `swarm:provision` scope.

## Endpoints

### POST /api/v1/swarms

Create a new swarm instance.

**Request**:
```json
{
  "name": "Alpha Recon Swarm",
  "drone_count": 4
}
```

**Response** (201 Created):
```json
{
  "id": "uuid-swarm-001",
  "name": "Alpha Recon Swarm",
  "status": "provisioning",
  "drone_count": 4,
  "endpoint_url": null,
  "created_at": "2026-07-24T19:00:00Z",
  "created_by": "commander-alpha"
}
```

**Response** (201 → polling until ready):
```json
{
  "id": "uuid-swarm-001",
  "name": "Alpha Recon Swarm",
  "status": "ready",
  "drone_count": 4,
  "endpoint_url": "http://gateway:8000/api/v1/swarms/uuid-swarm-001",
  "created_at": "2026-07-24T19:00:00Z",
  "created_by": "commander-alpha"
}
```

### GET /api/v1/swarms

List all swarm instances.

**Response** (200 OK):
```json
{
  "swarms": [
    {
      "id": "uuid-swarm-001",
      "name": "Alpha Recon Swarm",
      "status": "active",
      "drone_count": 4,
      "endpoint_url": "http://gateway:8000/api/v1/swarms/uuid-swarm-001",
      "created_at": "2026-07-24T19:00:00Z"
    }
  ]
}
```

### GET /api/v1/swarms/{swarm_id}

Get details of a specific swarm instance.

**Response** (200 OK): Single swarm object as above.

**Response** (404): `{"error": "Swarm not found"}`

### DELETE /api/v1/swarms/{swarm_id}

Initiate graceful termination of a swarm instance. Transitions to `draining` state.

**Response** (202 Accepted):
```json
{
  "id": "uuid-swarm-001",
  "status": "draining",
  "message": "Swarm termination initiated. Pending orders will complete before shutdown."
}
```

## Error Responses

| Status | Condition |
|--------|-----------|
| 401 | Missing or invalid JWT |
| 403 | Insufficient scope (`swarm:provision` required) |
| 409 | Swarm with same name already exists |
| 503 | Docker daemon unreachable |
