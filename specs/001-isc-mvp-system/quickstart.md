# Quickstart: Intent Swarm Commander — MVP Validation Guide

**Feature**: 001-isc-mvp-system | **Date**: 2026-07-24

## Prerequisites

- Docker Engine 24+ and Docker Compose v2+
- Python 3.12+ (for running tests locally)
- A modern web browser (Chrome, Firefox, Edge)
- `curl` or `httpx` (for API testing)

## Start the System

```bash
# From project root
cd src/docker
docker compose up --build -d

# Verify all services are running
docker compose ps
# Expected: gateway, provisioner, dashboard — all "Up"
```

**Expected Services**:

| Service | Port | Status |
|---------|------|--------|
| Gateway (MCP Auth) | 8000 | Healthy |
| Provisioner | 8001 (internal) | Healthy |
| Dashboard | 3000 | Healthy |

## Validation Scenarios

### Scenario 1: Provision a Swarm (FR-014, FR-015, US-6)

```bash
# Get a mock JWT token from the gateway
TOKEN=$(curl -s http://localhost:8000/auth/token \
  -d '{"commander_id": "cmdr-alpha", "scopes": ["swarm:provision"]}' \
  -H "Content-Type: application/json" | jq -r '.token')

# Provision a new swarm
curl -X POST http://localhost:8000/api/v1/swarms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alpha Recon Swarm", "drone_count": 4}'
```

**Expected**: 201 response with swarm ID and `status: "provisioning"`. Poll the GET endpoint until `status: "ready"` and `endpoint_url` is populated. A new Docker container should appear in `docker ps`.

### Scenario 2: Submit a SMEAC Order (FR-001, FR-002, US-1)

```bash
SWARM_ID="<swarm_id from Scenario 1>"

# Get a swarm-scoped token
TOKEN=$(curl -s http://localhost:8000/auth/token \
  -d "{\"commander_id\": \"cmdr-alpha\", \"scopes\": [\"swarm:${SWARM_ID}:orders:write\"]}" \
  -H "Content-Type: application/json" | jq -r '.token')

# Submit SMEAC order
curl -X POST "http://localhost:8000/api/v1/swarms/${SWARM_ID}/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "situation": "Enemy AA battery detected at grid 123456. Weather clear.",
    "mission": "Conduct ISR sweep of grid square 1234.",
    "execution": "Deploy 4-drone recon formation in diamond pattern at 200m altitude.",
    "admin_logistics": "RTB on fuel < 20%.",
    "command_signal": "Primary 123.4 MHz."
  }'
```

**Expected**: 201 response with order ID. The order status should progress through `submitted` → `parsing` → `translated` → `verified` → `executing` within 15 seconds (SC-001).

### Scenario 3: HITL Gate Triggers on High-Impact Action (FR-005, US-2)

```bash
# Submit a SMEAC order that generates a high-impact action (strike mission)
curl -X POST "http://localhost:8000/api/v1/swarms/${SWARM_ID}/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "situation": "HVT identified at compound Delta.",
    "mission": "Neutralize HVT with precision strike.",
    "execution": "Deploy 2-drone strike formation.",
    "admin_logistics": "Confirm BDA post-strike.",
    "command_signal": "Secure channel only."
  }'
```

**Expected**: Order status should reach `pending_hitl`. The dashboard (http://localhost:3000) should display the HITL confirmation modal. Approve or reject via the modal or the API endpoint.

### Scenario 4: Safety Constraint Violation (FR-007, US-4)

```bash
# Submit an order that violates altitude constraints
curl -X POST "http://localhost:8000/api/v1/swarms/${SWARM_ID}/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "situation": "Recon needed in restricted airspace zone.",
    "mission": "Fly through restricted zone Alpha at 5000m.",
    "execution": "Deploy 2-drone patrol at altitude 5000m.",
    "admin_logistics": "N/A",
    "command_signal": "Standard."
  }'
```

**Expected**: Order status should reach `rejected` with constraint violations listed (altitude exceeds maximum, restricted airspace zone).

### Scenario 5: Auth Rejection (FR-003, FR-004, US-3)

```bash
# Attempt to access a swarm without proper scope
BAD_TOKEN=$(curl -s http://localhost:8000/auth/token \
  -d '{"commander_id": "cmdr-beta", "scopes": ["swarm:other-swarm:orders:read"]}' \
  -H "Content-Type: application/json" | jq -r '.token')

curl -X POST "http://localhost:8000/api/v1/swarms/${SWARM_ID}/orders" \
  -H "Authorization: Bearer $BAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"situation": "test", "mission": "test", "execution": "test"}'
```

**Expected**: 403 Forbidden with scope violation error.

### Scenario 6: Dashboard Visualization (FR-008, US-5)

1. Open http://localhost:3000 in a browser
2. Verify all panels are visible: SMEAC Order Panel, Tactical Map, Unit Roster, Action History, Agent Identity indicator, Verification Status
3. Submit a SMEAC order via the UI
4. Verify the tactical map updates with simulated drone positions
5. Verify the audit log shows all actions

### Scenario 7: Edge Autonomous Targeting (FR-019, FR-020, US-7)

```bash
# Submit an order that specifies a target object class for edge detection
curl -X POST "http://localhost:8000/api/v1/swarms/${SWARM_ID}/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "situation": "Enemy vehicle reported in sector 7G.",
    "mission": "Locate and track vehicle.",
    "execution": "Deploy 1 drone to sector 7G and identify object class: vehicle.",
    "admin_logistics": "N/A",
    "command_signal": "Standard."
  }'
```

**Expected**: The drone navigates to the sector. The edge instance (Raspberry Pi mock) reports YOLO-E detection of "vehicle" and autonomously adjusts coordinates to approach the target.

## Run Tests

```bash
# Unit tests
cd /path/to/project
pytest tests/unit/ -v

# Integration tests (requires Docker Compose running)
pytest tests/integration/ -v

# Contract tests
pytest tests/contract/ -v
```

## Cleanup

```bash
cd src/docker
docker compose down -v
```
