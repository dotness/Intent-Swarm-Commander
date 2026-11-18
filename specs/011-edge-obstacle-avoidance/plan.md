# Implementation Plan: Edge-Autonomous Obstacle Detection and Avoidance

**Branch**: `011-edge-obstacle-avoidance` | **Date**: 2026-11-17 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/011-edge-obstacle-avoidance/spec.md)

**Input**: Feature specification from `/specs/011-edge-obstacle-avoidance/spec.md`

## Summary

Implement edge-autonomous obstacle detection, LLM-powered target-vs-obstacle discrimination, dynamic lateral bypass maneuvering, and auditable telemetry provenance. During active flight, `src/edge` analyzes forward FPV frames via YOLO-E for all objects in the flight corridor, uses an edge LLM (`EdgeTargetMatcher`) to decide whether a detected object matches the active mission order's target specification, and—for non-target obstacles—autonomously computes and executes a dynamic lateral detour toward the clearest open side via MAVSDK before resuming the mission route. Every edge-issued avoidance command is published over MQTT with `command_source: "edge_autonomous"` and persisted into the C2/operator audit view, verified end-to-end without mocks using `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`.

## Technical Context

**Language/Version**: Python 3.12+ (edge & uservice backend), JavaScript ES2022 (dashboard & Playwright E2E)

**Primary Dependencies**: FastAPI, Pydantic v2, `google-genai`, `ultralytics` (YOLO-E / YOLOv8), `opencv-python-headless`, `mavsdk`, `paho-mqtt`, `aiomqtt`, `sqlalchemy[asyncio]`, `duckdb`, `pyarrow`, `neo4j`, Playwright

**Storage**: PostgreSQL (`audit_events`, `swarm_live_state`), SQLite WAL (`EdgeSpool`), MinIO/Parquet (telemetry archive & snapshots), Memgraph/Neo4j (target correlation)

**Testing**: `pytest` (unit, contract, integration) and Playwright (`npx playwright test`) for no-mock E2E video verification

**Target Platform**: Linux (Raspberry Pi 5 edge node + Docker Compose local simulation with PX4 SITL and Virtual Cam)

**Project Type**: Distributed edge-to-C2 microservice & robotics control system (`src/edge/`, `src/uservice/`, `src/dashboard/`)

**Performance Goals**: Edge obstacle-avoidance command issued within 500 ms of critical-zone entry; 10 Hz edge vision/navigation loop; 5 Hz dashboard telemetry polling

**Constraints**: Constitution VI (zero mocks in `src/`, hermetic unit/contract tests), Constitution VII (single-path success logic, unconditional imports, zero `*_AVAILABLE` flags or fallback branches)

**Scale/Scope**: Single- and multi-drone swarm operations with real-time FPV obstacle avoidance and full C2 telemetry/audit provenance

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Design | Post-Design | Verification Notes |
|-----------|------------|-------------|--------------------|
| **I. Cone of Uncertainty (LTV)** | PASS | PASS | Advances autonomous tactical navigation & obstacle-resilient execution toward the TO-BE autonomous swarm vision. |
| **II. Cynefin Domain Assessment** | PASS | PASS | Classified as *Complicated* (deterministic corridor geometry + MAVSDK actuation + structured LLM semantic classification with fail-safe defaults). |
| **III. Execution via OODA Loops** | PASS | PASS | Directly implements an edge OODA loop: Observe (frame + YOLO-E) → Orient (LLM target-vs-obstacle + corridor clearance) → Decide (lateral bypass / approach / hold) → Act (MAVSDK + telemetry provenance). |
| **IV. Guard Against False Cones** | PASS | PASS | Builds on existing `ultralytics`, `google-genai`, `mavsdk`, and `paho-mqtt` stack; no speculative dependencies. |
| **V. Script Organization** | PASS | PASS | Any virtual-camera or helper scripts stay under `scripts/` (`scripts/virtual_cam_server.py`); root stays clean. |
| **VI. Production Purity & Test Isolation** | PASS | PASS | Zero mocks/stubs in `src/`. No-mock E2E feeds real `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4` into real edge + PX4 SITL + C2 stack. Unit tests use hermetic fixtures in `tests/`. |
| **VII. Single-Path Success Logic** | PASS | PASS | All imports (`google.genai`, `ultralytics`, `mavsdk`, `cv2`, `paho.mqtt`) are unconditional at module top level; zero `*_AVAILABLE` flags or fallback matchers in `src/`. |

## Project Structure

### Documentation (this feature)

```text
specs/011-edge-obstacle-avoidance/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── edge-avoidance-contract.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
├── edge/
│   ├── api/server.py                    # /target, /telemetry extensions for target attributes & avoidance state
│   ├── navigation/flight_controller.py  # Obstacle-avoidance state machine, dynamic lateral bypass, route resumption
│   ├── telemetry/publisher.py           # Publish QoS 1 edge avoidance alert events with provenance
│   └── vision/
│       ├── inference.py                 # Unfiltered frame detection + corridor occupancy/clearance metrics
│       └── target_matcher.py            # NEW: Edge LLM target-vs-obstacle discriminator (google-genai + TTL cache)
├── uservice/
│   ├── operation/audit.py               # AuditEventType extension for edge autonomous bypass
│   ├── swarm/api/routes.py              # Expose edge avoidance provenance in swarm telemetry/audit endpoints
│   └── telemetry/
│       ├── models/contract/events.py    # SwarmTelemetryEvent provenance contract
│       └── operations/ingestor.py       # Persist AuditEvent on edge_autonomous alert ingestion
└── dashboard/
    └── js/main.js                       # Render edge-autonomous avoidance provenance in C2 operator view

scripts/
└── virtual_cam_server.py                # Video streaming support for tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4

tests/
├── unit/test_edge_obstacle_avoidance.py # NEW: Hermetic unit tests for matcher, corridor math, & bypass state machine
├── contract/test_mqtt_contract.py       # Extended: Edge avoidance alert provenance contract validation
└── e2e/prod_obstacle_avoidance.spec.js  # NEW: No-mock Playwright E2E using real video, PX4 SITL, edge, & C2 audit
```

**Structure Decision**: Extends the existing three-tier repository layout (`src/edge/`, `src/uservice/`, `src/dashboard/`) with a focused `target_matcher.py` module in `src/edge/vision/` and dedicated unit, contract, and no-mock E2E test files in `tests/`.

## Complexity Tracking

No Constitution Check violations; no additional complexity justification required.

## LTV Node Point Alignment

- **Node Point**: Edge-Autonomous Tactical Navigation & Resilient Execution (OODA-driven edge perception, LLM target discrimination, and MAVSDK obstacle bypass with C2 provenance).
- **Architecture Review**: Reviewed by `uservice-arch-reviewer`; addressed deferred `cv2` import, `EdgeTargetMatcher` thread-safety/bounded cache/JSON guard, `FlightController` telemetry task cleanup & concurrent LLM classification, `SwarmFacade.get_swarm_audit_events` encapsulation, and single-transaction `TelemetryIngestor` persistence.
