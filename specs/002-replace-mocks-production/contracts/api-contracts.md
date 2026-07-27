# API Contracts: Replace Mocks, Stubs & Hardcodes

**Feature**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/002-replace-mocks-production/spec.md)
**Date**: 2026-07-27

## Overview

This document defines the new and modified API contracts required to replace mocks. Most existing endpoints retain their signatures — the changes are internal (real DB queries, real Docker operations). Only a few new endpoints are needed.

---

## New Endpoints

### POST `/api/v1/auth/login`

**Purpose**: Issue a JWT token for dashboard authentication (replaces hardcoded `placeholder-token`).

**Request**:
```json
{
  "commander_id": "string",
  "passphrase": "string"
}
```

**Response (200)**:
```json
{
  "token": "eyJhbGci...",
  "expires_at": "2026-07-27T22:05:00Z",
  "commander_id": "commander-alpha"
}
```

**Response (401)**:
```json
{
  "error": "Invalid credentials"
}
```

**Notes**: Uses the existing `issue_jit_credential()` from `jit.py` internally. Initial implementation can use a simple credential check (env var or config) since a full IdP integration is out of scope.

---

### GET `/api/v1/swarms/{swarm_id}/telemetry`

**Purpose**: Return real-time telemetry for drones in a swarm (replaces hardcoded `drones` array).

**Response (200)**:
```json
{
  "drones": [
    {
      "id": "UAV-Alpha-1",
      "position": {
        "lat": 52.5200,
        "lng": 13.4050,
        "alt_m": 200
      },
      "battery_pct": 85,
      "current_mission": "recon",
      "status": "active",
      "last_seen": "2026-07-27T19:50:00Z"
    }
  ]
}
```

**Notes**: This endpoint aggregates telemetry from edge nodes. The edge API server already has a `/health` endpoint — telemetry data can be pulled from edge nodes via `httpx` or pushed via the existing Temporal workflow infrastructure.

---

## Modified Endpoints (Contract Unchanged, Implementation Changed)

### POST `/api/v1/swarms/{swarm_id}/orders`

**Before**: SMEAC facade skips RBAC and DB persistence.
**After**: Enforces `smeac:create` scope, persists `SmeacOrder` to DB, returns real `order_id`.

**Contract**: No changes to request/response schema. Existing `SmeacOrderCreateRequest` / `SmeacOrderResponse` schemas remain.

---

### GET `/api/v1/swarms/{swarm_id}/orders/{order_id}`

**Before**: Returns hardcoded `{"order_id": ..., "status": "submitted", "commands": [], "constraint_violations": []}`.
**After**: Queries DB for real order status, joins with associated commands and violations.

**Contract**: No changes to `OrderStatusResponse` schema.

---

### POST `/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide`

**Before**: Updates in-memory `_pending_decisions` dict.
**After**: Persists decision to DB via `HitlDecision` ORM model, sends Temporal signal to resume workflow.

**Contract**: No changes to `HitlDecideRequest` / `HitlDecideResponse` schemas.

---

### GET `/api/v1/swarms/{swarm_id}/hitl/pending`

**Before**: Filters in-memory `_pending_decisions` for `status == "pending"`.
**After**: Queries DB for pending decisions filtered by swarm.

**Contract**: No changes.

---

### POST `/api/v1/swarms`

**Before**: Creates swarm record in-memory with simulated `container_id`.
**After**: Provisions real Docker container, persists `SwarmInstance` to DB with real `container_id`.

**Contract**: No changes to `CreateSwarmRequest` / `SwarmResponse` schemas.

---

### DELETE `/api/v1/swarms/{swarm_id}`

**Before**: Instantly sets status to `terminated` in-memory.
**After**: Stops and removes Docker container, waits for completion, updates DB status through `draining → terminated`.

**Contract**: No changes.

---

## Dashboard Client Changes

### Token Management

| Aspect | Before (Mock) | After (Production) |
|--------|---------------|-------------------|
| Auth header | `'Bearer placeholder-token'` | `'Bearer ' + sessionStorage.getItem('isc_token')` |
| Auth state | `isAuthenticated = true` | Check `sessionStorage` for valid token |
| Commander ID | `"commander-default"` | Decoded from JWT claims or login response |
| Token expiry | None | On 401 response → redirect to login |

### Telemetry

| Aspect | Before (Mock) | After (Production) |
|--------|---------------|-------------------|
| `fetchTelemetry()` | Returns hardcoded 2-drone array | Calls `GET /api/v1/swarms/{id}/telemetry` |

---

## Edge API Contracts

No contract changes. The edge server already exposes:
- `POST /target` — receive target assignments
- `GET /target` — get current assignment
- `GET /health` — health check

The internal behavior changes (real camera, real inference, real flight commands) do not affect the API contract.
