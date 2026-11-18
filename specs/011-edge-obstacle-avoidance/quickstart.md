# Quickstart Validation Guide: Edge-Autonomous Obstacle Detection and Avoidance

**Feature**: `011-edge-obstacle-avoidance` | **Date**: 2026-11-17

## Prerequisites

1. **Test Media Asset**: Verify `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4` exists at the repository root.
2. **Environment**: Python 3.12+ with project dependencies (`uv sync` / `.venv`), `GEMINI_API_KEY` configured for the edge LLM target-vs-obstacle matcher, and Docker Compose stack (PX4 SITL, MQTT broker, PostgreSQL, MinIO, Memgraph, `uservice`, `edge`, `virtual-cam`).

## Validation Scenarios

### 1. Hermetic Unit & Contract Tests
Verify corridor geometry, edge LLM classification schema/fail-safe behavior, `FlightController` bypass state transitions, and MQTT/Audit provenance contracts:

```bash
pytest tests/unit/test_edge_obstacle_avoidance.py tests/contract/test_mqtt_contract.py -v
```

**Expected Outcome**:
- Non-target obstacles in the forward corridor trigger `bypassing` toward the clearest lateral side and transition through `resuming` back to `searching`/`approaching`.
- Objects confirmed as ordered targets by the edge LLM trigger `approaching` (zero bypasses).
- Ambiguous/low-confidence LLM matches fail safe to obstacle bypass.
- All avoidance telemetry events satisfy `SwarmTelemetryEvent` contract with `command_source == "edge_autonomous"`.

### 2. No-Mock End-to-End Video Verification (`drone_fpv_fly_straight_meet_lamp_obstacle.mp4`)
1. Configure `scripts/virtual_cam_server.py` with `VIRTUAL_VIDEO_PATH=tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`.
2. Start the live Docker Compose simulation stack (`src/docker/docker-compose.yml` or E2E runner) with real `src/edge`, PX4 SITL, MQTT, `src/uservice`, and dashboard.
3. Run the Playwright E2E test:

```bash
npx playwright test tests/e2e/prod_obstacle_avoidance.spec.js
```

**Expected Outcome**:
- Drone arms, takes off, and begins flying straight along its ordered route (target set to a non-lamp-post class, e.g., `"truck"`).
- As the lamp post enters the forward corridor in `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`, the edge LLM confirms `"lamp post"` / `"pole"` != `"truck"`, and `FlightController` issues a lateral bypass command via MAVSDK.
- Telemetry trajectory proves an initial straight leg followed by a measurable lateral course deviation, then route resumption.
- Both the MQTT/live telemetry projection (`/api/v1/swarms/{swarm_id}/telemetry`) and the C2 operator audit view (`/api/v1/swarms/{swarm_id}/audit` + dashboard UI) contain timestamped records with `command_source: "edge_autonomous"` and `decision_authority: "edge"`.
- A companion target-discrimination check confirms that when the ordered target matches the detected object class, the drone approaches instead of bypassing.
