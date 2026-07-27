# Mocks, Stubs, and Hardcoded Data

This document lists all identified locations in the codebase where mock implementations, stubs, in-memory simulations, or hardcoded data are currently used for MVP or local development.

## Frontend Dashboard (`src/dashboard/`)
* **`js/api.js`**:
  * Uses a hardcoded mock token (`AUTH_HEADER = { 'Authorization': 'Bearer placeholder-token' }`).
  * `fetchTelemetry` returns a simulated/hardcoded `drones` array instead of calling the backend telemetry endpoint.
* **`js/auth_indicator.js`**:
  * Mocks authentication by hardcoding `isAuthenticated = true` and `commanderId = "commander-default"`.
* **`js/hitl.js`**:
  * Uses the hardcoded mock token (`'Authorization': 'Bearer placeholder-token'`).
  * Basic countdown timer is simulated for MVP.

## Microservices Backend (`src/uservice/`)
* **`smeac/facade/smeac.py`**:
  * RBAC checks are commented out / placeholders (`# await self.permissions.require_access(...)`).
  * Database persistence is commented out (mocked).
  * `get_order_status` returns a hardcoded mock response dictionary.
* **`smeac/operations/process.py`**:
  * Safety check integration is mocked (Guardian Critic activity not executed).
  * HITL verification is mocked (`hitl_approved = True`).
* **`hitl/facade/hitl.py`**:
  * Uses an in-memory dictionary `_pending_decisions` instead of DB + Temporal signals.
* **`swarm/operations/create.py`**:
  * Uses an in-memory registry `_swarms` instead of a database.
  * Docker container provisioning is simulated (`container_id = f"sim-container-..."`).
* **`swarm/operations/delete.py`**:
  * Swarm termination is simulated (immediately transitions to terminated without waiting).
* **`swarm/operations/swarm_agents.py`**:
  * `check_geofencing` always returns `None` (no restricted zones defined for MVP).
* **`security/proxy.py`**:
  * For MVP, falls through to local routes if no dynamic endpoint is present.

## Edge Services (`src/edge/`)
* **`api/server.py`**:
  * FastAPI server runs as a stub if FastAPI is not available.
* **`vision/camera.py`**:
  * Runs in simulation mode if OpenCV is unavailable.
  * `read_frame()` returns a simulated frame (None / black image placeholder) in simulation mode.
* **`vision/inference.py`**:
  * Runs in simulation mode if YOLO/ultralytics is unavailable.
  * `detect()` returns empty detections in simulation mode.
* **`navigation/flight_controller.py`**:
  * Runs in simulation mode if MAVSDK is unavailable.
  * Frame center is hardcoded (`frame_center_x = 320`).
  * `approach_distance_m` simulation decrements manually instead of using telemetry.
  * Sending yaw commands via MAVSDK is a no-op placeholder.
