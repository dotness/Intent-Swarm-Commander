# API Contract: Dashboard & Microservice Interaction

**Feature Directory**: `specs/004-playwright-e2e-tests`
**Date**: 2026-09-12

This document defines the API surface validated by the Playwright end-to-end test suite.

## 1. Authentication

### POST `/api/v1/auth/login`
- **Purpose**: Authenticates the tactical commander and issues an ephemeral JIT Bearer token.
- **Request Body**:
  ```json
  {
    "commander_id": "commander-alpha",
    "passphrase": "dev_passphrase"
  }
  ```
- **Response 200 OK**:
  ```json
  {
    "token": "<JWT_STRING>",
    "agent_id": "agent-commander-alpha-<UUID>",
    "expires_at": "2026-09-13T09:00:00.000000+00:00",
    "lifetime_seconds": 86400
  }
  ```
- **Response 401 Unauthorized**:
  ```json
  {
    "detail": "Invalid credentials"
  }
  ```

---

## 2. Swarm Discovery

### GET `/api/v1/swarms`
- **Headers**: `Authorization: Bearer <TOKEN>`
- **Response 200 OK**:
  ```json
  {
    "swarms": [
      {
        "id": "swarm-bravo",
        "name": "Alpha Recon Swarm",
        "status": "ready",
        "drone_count": 4
      }
    ]
  }
  ```

---

## 3. Telemetry

### GET `/api/v1/swarms/{swarm_id}/telemetry`
- **Headers**: `Authorization: Bearer <TOKEN>`
- **Response 200 OK**:
  ```json
  {
    "swarm_id": "swarm-bravo",
    "timestamp": "2026-09-12T11:00:00Z",
    "drones": [
      {
        "id": "drone-01",
        "position": {
          "lat": 52.5200,
          "lon": 13.4050,
          "alt": 50.0
        },
        "battery": 88,
        "mode": "autonomous",
        "speed": 12.4
      }
    ]
  }
  ```

---

## 4. SMEAC Orders

### POST `/api/v1/swarms/{swarm_id}/orders`
- **Headers**:
  - `Authorization: Bearer <TOKEN>`
  - `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "situation": "string",
    "mission": "string",
    "execution": "string",
    "administration": "string",
    "command": "string"
  }
  ```
- **Response 200 OK**:
  ```json
  {
    "order_id": "order-uuid",
    "status": "accepted",
    "swarm_id": "swarm-bravo",
    "commands_generated": 4
  }
  ```

---

## 5. Human-in-the-Loop (HITL) Gate

### GET `/api/v1/swarms/{swarm_id}/hitl/pending`
- **Headers**: `Authorization: Bearer <TOKEN>`
- **Response 200 OK**:
  ```json
  {
    "pending_decisions": [
      {
        "decision_id": "dec-uuid-1",
        "swarm_id": "swarm-bravo",
        "action_description": "Authorize kinetic engagement beyond geofence boundary",
        "risk_level": "critical",
        "requires_role": "commander"
      }
    ]
  }
  ```

### POST `/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide`
- **Headers**:
  - `Authorization: Bearer <TOKEN>`
  - `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "decision": "approved",
    "reason": "Tactical necessity verified"
  }
  ```
- **Response 200 OK**:
  ```json
  {
    "decision_id": "dec-uuid-1",
    "status": "approved",
    "resolved_by": "agent-commander-alpha-1f037fdf"
  }
  ```
