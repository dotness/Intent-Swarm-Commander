# Quickstart Validation Guide: Replace Mocks, Stubs & Hardcodes

**Feature**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/002-replace-mocks-production/spec.md)
**Date**: 2026-07-27

## Prerequisites

- PostgreSQL running on `localhost:5432` (or `DATABASE_URL` env var set)
- Temporal Server running on `localhost:7233` (or `TEMPORAL_HOST`/`TEMPORAL_PORT` env vars set)
- Docker daemon running and accessible
- Python 3.14+ with project virtualenv activated
- `shapely` package installed (for geofencing)
- `docker` Python package installed (for container provisioning)

## Setup

```bash
# 1. Start infrastructure (PostgreSQL, Temporal)
docker compose up -d postgres temporal

# 2. Set environment variables
export DATABASE_URL="postgresql+asyncpg://isc:isc_dev_password@localhost:5432/isc"
export JWT_SECRET="dev-secret-key-change-in-production"
export JWT_ISSUER="isc-idp"

# 3. Start the backend
python -m uvicorn src.uservice.main:app --reload --port 8000

# 4. Serve the dashboard (separate terminal)
python -m http.server 8080 -d src/dashboard
```

---

## Validation Scenarios

### V1: Authentication (FR-001, FR-002)

**Verify**: Dashboard login issues a real JWT; hardcoded tokens are gone.

```bash
# Attempt to access API without a token → should get 401
curl -s http://localhost:8000/api/v1/swarms | jq .
# Expected: {"error": "Missing or invalid Authorization header"}

# Login to get a real token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"commander_id":"commander-alpha","passphrase":"dev-passphrase"}' | jq -r '.token')

# Use the real token
curl -s http://localhost:8000/api/v1/swarms \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: {"swarms": []}
```

**Dashboard check**: Open `http://localhost:8080`, verify a login prompt appears (no auto-authenticated state). After login, verify auth indicator shows real commander ID.

**Codebase check**:
```bash
# Verify no hardcoded tokens remain
grep -r "placeholder-token" src/
# Expected: no results
```

---

### V2: Swarm Creation — Real Docker Containers (FR-010)

**Verify**: Creating a swarm provisions real Docker containers.

```bash
# Create a swarm
curl -s -X POST http://localhost:8000/api/v1/swarms \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"test-swarm","drone_count":2}' | jq .
# Expected: response with real container_id (not "sim-container-...")

# Verify containers are running
docker ps --filter "label=isc-swarm"
# Expected: containers listed with real IDs matching the API response
```

---

### V3: SMEAC Order — RBAC + DB Persistence (FR-004, FR-005, FR-006)

**Verify**: SMEAC orders enforce RBAC and persist to the database.

```bash
# Submit a SMEAC order (with valid token)
SWARM_ID="<swarm-id-from-V2>"
ORDER=$(curl -s -X POST "http://localhost:8000/api/v1/swarms/$SWARM_ID/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "situation":"Enemy positions observed at grid 123456",
    "mission":"Conduct aerial reconnaissance of sector Alpha",
    "execution":"Deploy 2 UAVs in staggered formation at 200m altitude"
  }' | jq .)
echo "$ORDER"
# Expected: {"order_id":"...","status":"submitted",...}

ORDER_ID=$(echo "$ORDER" | jq -r '.order_id')

# Get order status (should be real, not hardcoded)
curl -s "http://localhost:8000/api/v1/swarms/$SWARM_ID/orders/$ORDER_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: real status reflecting workflow progress

# Restart the backend, then re-query — data should persist
# (kill and restart uvicorn, then repeat the GET request)
```

---

### V4: HITL Decision — DB + Temporal Signal (FR-008, FR-009)

**Verify**: HITL decisions are persisted and trigger Temporal signals.

```bash
# Check for pending HITL decisions
curl -s "http://localhost:8000/api/v1/swarms/$SWARM_ID/hitl/pending" \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: list of pending decisions from DB (not in-memory)

# If a decision is pending, submit it
DECISION_ID="<decision-id-from-above>"
curl -s -X POST "http://localhost:8000/api/v1/swarms/$SWARM_ID/hitl/$DECISION_ID/decide" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approved","rationale":"Verified safe for execution"}' | jq .
# Expected: decision recorded, workflow resumes
```

**Dashboard check**: Open the dashboard with a pending HITL decision → the approval modal should appear. Submit a decision → verify the workflow progresses.

---

### V5: Swarm Deletion — Real Container Termination (FR-011)

```bash
# Delete the test swarm
curl -s -X DELETE "http://localhost:8000/api/v1/swarms/$SWARM_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: {"status": "terminated"}

# Verify containers are gone
docker ps --filter "label=isc-swarm"
# Expected: no containers for the deleted swarm
```

---

### V6: Telemetry — Real Data (FR-003)

```bash
# Fetch telemetry (requires active swarm with edge nodes)
curl -s "http://localhost:8000/api/v1/swarms/$SWARM_ID/telemetry" \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: real drone telemetry data (not hardcoded UAV-Alpha-1/2)
```

---

### V7: Security Proxy — Strict Routing (FR-013)

```bash
# Request to a non-existent swarm
curl -s "http://localhost:8000/api/v1/swarms/00000000-0000-0000-0000-000000000000/orders" \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: 404 error (not fallthrough to local routes)
```

---

### V8: Edge Hardware (FR-014, FR-015, FR-016) — On Edge Device Only

```bash
# On the Raspberry Pi 5 with hardware connected:
export SIMULATION_MODE=false

# Start the edge server
python -m src.edge.api.server

# Verify camera produces real frames (check logs)
# Verify YOLO inference runs on real frames (check logs)
# Verify MAVSDK commands are sent (check logs)

# Without hardware, expect clear errors:
# "RuntimeError: Camera hardware required when SIMULATION_MODE=false"
```

---

## Automated Tests

```bash
# Run the full test suite
pytest tests/ -v

# Run only integration tests (requires infrastructure)
pytest tests/integration/ -v

# Run only unit tests (no infrastructure needed)
pytest tests/unit/ -v
```

---

## Success Verification Checklist

- [ ] `grep -r "placeholder-token" src/` returns no results
- [ ] `grep -r "isAuthenticated = true" src/` returns no results  
- [ ] `grep -r "_pending_decisions" src/` returns no results (or only in migration comments)
- [ ] `grep -r "_swarms" src/` returns no results (or only in migration comments)
- [ ] `grep -r "sim-container-" src/` returns no results
- [ ] `grep -r "frame_center_x = 320" src/` returns no results
- [ ] `grep -r "hitl_approved = True" src/` returns no results
- [ ] Backend survives restart with all state preserved
- [ ] Docker containers are created/destroyed for swarm lifecycle
- [ ] Auth middleware rejects requests with missing/invalid tokens
