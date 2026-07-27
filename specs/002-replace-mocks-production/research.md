# Research: Replace Mocks, Stubs & Hardcodes

**Feature**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/002-replace-mocks-production/spec.md)
**Date**: 2026-07-27

## Overview

This research consolidates findings on how to replace each mock/stub with real production implementations. Since the codebase already has the required infrastructure (ORM models, database engine, JWT middleware, Temporal facade, Pydantic schemas), the primary research focuses on **wiring patterns** rather than technology selection.

---

## R1: Dashboard Authentication — Real Token Management

**Decision**: Use a login flow that calls a `/api/v1/auth/login` backend endpoint to obtain a JWT, store it in `sessionStorage`, and include it in all API requests. On 401 responses, redirect to re-authenticate.

**Rationale**:
- The backend already has `jwt.py` (decode/validate), `jit.py` (credential issuance), and `middleware.py` (auth enforcement). The dashboard just needs to obtain and use real tokens.
- `sessionStorage` is preferred over `localStorage` because tokens expire quickly (5 min JIT default) and should not persist across browser sessions.
- The existing `auth_gateway_middleware` already validates Bearer tokens and returns 401 for invalid ones.

**Alternatives considered**:
- **OAuth2 PKCE flow**: More secure for public clients, but adds complexity (IdP, redirect URIs) that is premature before a dedicated IdP is deployed. Can be layered on later.
- **Cookie-based sessions**: Would require CSRF protection and changes to the CORS policy. JWT Bearer tokens align with the existing middleware.

---

## R2: SMEAC Facade — Database Persistence & RBAC

**Decision**: Un-comment the existing DB persistence code in `smeac.py`, add a `require_scope()` helper to `DomainFacade`, and replace the hardcoded `get_order_status` with a real DB query.

**Rationale**:
- The `SmeacOrder` ORM model already exists at `smeac/models/storage/smeac.py` with all needed columns.
- The `DomainFacade` base class already has `self.session` (AsyncSession) and `self.user` (dict with JWT claims).
- RBAC can be implemented as scope-based checks using `self.user` claims — the JWT already carries a `scope` field, and `jwt.py` has `verify_scope()` and `extract_scopes()`.

**Alternatives considered**:
- **Dedicated RBAC middleware**: Would centralize authorization but adds a new layer. Scope checks at the facade level are simpler, more granular, and follow the existing pattern.
- **External policy engine (OPA)**: Overkill for the current scope of 3-5 scopes.

---

## R3: HITL Facade — DB + Temporal Signals

**Decision**: Replace the in-memory `_pending_decisions` dict with:
1. Database persistence using the existing `HitlDecision` ORM model.
2. Temporal signals to notify waiting workflows when a decision is made.

**Rationale**:
- The `HitlDecision` ORM model exists at `hitl/models/storage/decision.py`.
- The `operation/facade.py` already has `signal_workflow()` which sends Temporal signals.
- The `ProcessSmeacWorkflow` needs a `@workflow.signal` handler to receive HITL decisions and resume processing.

**Alternatives considered**:
- **Polling-based HITL**: Workflow polls DB for decision changes. Adds latency and unnecessary DB load. Temporal signals are purpose-built for this.
- **WebSocket-based signaling**: Would require the dashboard to maintain a persistent connection. The current HTTP polling + Temporal signals is simpler and more resilient.

---

## R4: Swarm Operations — Docker SDK + DB

**Decision**: Replace in-memory `_swarms` with:
1. DB persistence using the existing `SwarmInstance` ORM model.
2. Docker SDK (`docker-py`) for real container provisioning via `docker.from_env().containers.run()`.

**Rationale**:
- The `SwarmInstance` ORM model exists at `swarm/models/storage/instance.py`.
- Docker SDK is the standard Python interface for Docker operations and aligns with the existing container-based architecture.
- Swarm deletion must call `container.stop()` + `container.remove()` and wait for completion.

**Alternatives considered**:
- **Kubernetes orchestration**: Would provide better scaling but is a much larger change. Docker containers are the current architecture decision.
- **Docker Compose orchestration**: Doesn't support dynamic per-swarm provisioning needed here.

---

## R5: Guardian Critic — Temporal Activity Integration

**Decision**: Convert `verify_command()` from `swarm_agents.py` into a Temporal activity that the `ProcessSmeacWorkflow` executes before HITL verification.

**Rationale**:
- The safety check functions (`check_altitude`, `check_duration`, `check_geofencing`) already exist and are well-structured.
- Running them as a Temporal activity makes them durable, retryable, and auditable.
- The workflow should block on violations (return error) rather than proceeding.

**Alternatives considered**:
- **Inline function call in workflow**: Simpler but loses Temporal durability guarantees and activity-level retry/timeout controls.

---

## R6: Geofencing — Restricted Zone Polygon Checks

**Decision**: Implement `check_geofencing()` using Shapely for point-in-polygon intersection testing against a configurable set of restricted zones stored in the database or a JSON configuration file.

**Rationale**:
- Shapely is the standard Python library for geometric operations and handles polygon intersection efficiently.
- Restricted zones can initially be loaded from a JSON config file (simpler) and later migrated to DB storage.
- The function signature already accepts `target_area: dict | str`, which can carry coordinate data.

**Alternatives considered**:
- **Custom ray-casting implementation**: Reinvents the wheel. Shapely is well-tested and performant.
- **External GIS service**: Adds network dependency for a safety-critical check. Local evaluation is faster and more reliable.

---

## R7: Security Proxy — Strict Routing

**Decision**: Replace the `call_next(request)` fallthrough with a `JSONResponse(status_code=404, ...)` when no dynamic endpoint is found for an unregistered swarm.

**Rationale**:
- The proxy already performs the swarm lookup via `_swarms.get(swarm_id)`. After DB migration, this becomes a DB query.
- Falling through to local routes could expose internal endpoints. Production behavior must be fail-closed.

**Alternatives considered**:
- **503 Service Unavailable**: Could indicate the swarm is temporarily down. But 404 is more accurate when the swarm doesn't exist.

---

## R8: Edge Modules — Fail-Loud Hardware Integration

**Decision**: Replace silent simulation fallbacks with explicit configuration:
1. Add a `SIMULATION_MODE` environment variable (default: `false`).
2. When `SIMULATION_MODE=false` and hardware is unavailable, raise `RuntimeError` with diagnostic information.
3. When `SIMULATION_MODE=true`, allow simulation with clear logging (existing behavior).

**Rationale**:
- The current silent fallback is dangerous — operators won't know they're running on simulated data.
- An explicit environment variable makes simulation an intentional choice.
- The edge API server (`server.py`) should require FastAPI as a hard dependency when not in simulation mode.

**Alternatives considered**:
- **Remove simulation entirely**: Too restrictive — developers need simulation for testing without hardware.
- **Runtime flag via API**: Adds complexity. Environment variable is simpler and set at deploy time.

---

## R9: Flight Controller — Dynamic Frame Center & Real Telemetry

**Decision**:
1. Derive `frame_center_x` from the camera's configured width (`self.camera.width // 2`).
2. Replace manual `approach_distance_m` decrement with actual telemetry from MAVSDK (`drone.telemetry.position()`).
3. Implement `_apply_heading_correction` to send real yaw commands via `drone.action.set_yaw()`.

**Rationale**:
- The `CameraStream` already stores `self.width` and `self.height` — the center point is trivially derived.
- MAVSDK provides telemetry streams and action commands as its core API.

**Alternatives considered**:
- **External telemetry service**: Adds a network dependency between the edge flight controller and a remote service. MAVSDK provides local telemetry directly.

---

## R10: Dashboard Telemetry — Real API Call

**Decision**: Replace the hardcoded `drones` array in `fetchTelemetry()` with a real `fetch()` call to `${API_BASE}/swarms/${swarmId}/telemetry`.

**Rationale**:
- The function signature already accepts `swarmId` and the API base URL is configured.
- A new backend endpoint `/api/v1/swarms/{swarm_id}/telemetry` needs to be created (or the edge telemetry needs to be aggregated).
- The polling interval in `main.js` already handles periodic refreshes.

**Alternatives considered**:
- **WebSocket telemetry stream**: Would provide lower latency but adds complexity. HTTP polling at 2s intervals is sufficient for MVP-to-production transition.
- **Server-Sent Events (SSE)**: Good middle ground but adds server-side complexity. Can be added as a future optimization.
