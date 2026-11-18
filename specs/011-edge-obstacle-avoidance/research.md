# Phase 0 Research: Edge-Autonomous Obstacle Detection and Avoidance

**Feature**: `011-edge-obstacle-avoidance` | **Date**: 2026-11-17

## Decision 1: Edge Perception — Unified Target & Obstacle Detection

- **Decision**: Extend `YoloEInference.detect()` in `src/edge/vision/inference.py` to support returning all detections above `confidence_threshold` (when `target_class=None` or via a `detect_all()` / unfiltered mode) alongside frame-corridor occupancy metrics (central corridor overlap, bounding-box area ratio, and left/right free-space clearance).
- **Rationale**: Currently `FlightController._navigation_loop()` calls `self.inference.detect(frame, target_class=self.target_class)`, which discards every object that does not exactly match `target_class`. Unfiltered detection in a single inference pass incurs zero extra model-inference overhead while surfacing both potential mission targets and physical obstacles (e.g., lamp posts, poles, vehicles, trees).
- **Alternatives considered**:
  - Running a second dedicated obstacle-segmentation model in parallel: rejected due to Raspberry Pi 5 compute/latency budget (<500 ms reaction requirement).
  - Optical-flow-only obstacle detection: rejected because semantic class labels are required for the edge LLM to distinguish ordered targets from obstacles.

## Decision 2: Edge LLM Target-vs-Obstacle Discrimination

- **Decision**: Introduce an `EdgeTargetMatcher` component in `src/edge/vision/target_matcher.py` using `google-genai` (consistent with `src/uservice/base/agent.py` and `pyproject.toml`) to evaluate whether a detected object's class/label and optional order attributes match the active mission order's target specification. Cache resolved `(mission_id, target_spec, detected_class)` classifications in-memory with a short TTL so repeated frames of the same object class resolve in <1 ms after the first LLM classification, while any new or unseen object class is evaluated by the LLM in real time.
- **Rationale**:
  - Satisfies the requirement that the edge LLM performs target-vs-obstacle matching (e.g., recognizing semantic equivalents like `"vehicle"` ↔ `"truck"`/`"car"`/`"bus"`, or distinguishing `"lamp post"` / `"traffic light"` / `"pole"` from `"truck"`).
  - Keeps steady-state per-frame loop latency well within the 500 ms reaction budget (SC-004) and avoids redundant LLM calls on every 10 Hz video frame.
  - Fails safe per spec Edge Cases: if LLM confidence is below threshold or ambiguous, classify as a non-target obstacle rather than risking collision.
  - Adheres to Constitution VII (single-path unconditional `google.genai` import, no fallback regex/stub matcher in `src/`).
- **Alternatives considered**:
  - Calling the LLM synchronously on every single 100 ms frame for already-seen classes: rejected due to 300–1000 ms network/inference jitter violating the 500 ms reaction SLA.
  - Static string equality (`cls_name.lower() == target_class.lower()`): rejected because it cannot handle semantic target descriptions and violates the clarified requirement that the edge LLM performs matching.

## Decision 3: Dynamic Lateral Bypass & Route Resumption State Machine

- **Decision**: Implement an obstacle-avoidance state machine inside `FlightController` (`src/edge/navigation/flight_controller.py`) with states: `searching`, `approaching`, `bypassing`, `resuming`, `obstructed_hold`, `arrived`, `aborted`.
  - **Collision-risk trigger**: A non-target obstacle whose bounding box overlaps the central forward flight corridor (configurable horizontal band around frame center) and exceeds a proximity/size threshold (bounding-box height or area ratio).
  - **Clearest lateral side selection**: Compare left-half vs. right-half obstacle occupancy in the current frame; steer toward the side with greater open horizontal clearance (relative heading offset `±45°` to `±75°` via MAVSDK `goto_location` or offboard lateral step).
  - **Resumption**: Once the obstacle exits the central forward corridor for a short stability window (e.g., 3 consecutive clear frames) and minimum lateral clearance is achieved, transition to `resuming` to steer back toward the active mission waypoint / original heading, then back to `searching` / `approaching`.
  - **Blocked / Perception-loss fail-safe**: If both left and right corridors are obstructed or `camera.read_frame()` fails repeatedly during active flight, transition to `obstructed_hold`, command MAVSDK hold/hover, and publish an `alert` telemetry event.
- **Rationale**: Reuses the existing MAVSDK `goto_location` pattern already proven in `FlightController._apply_heading_correction()`, avoids altitude conflicts, and directly satisfies User Stories 1 & 2 and Edge Cases.
- **Alternatives considered**:
  - Fixed-direction bypass (always right): rejected in favor of dynamic clearest-side selection (clarified Q2).
  - Vertical climb-over: rejected because forward-facing camera loses horizontal obstacle tracking during pitch/climb maneuvers.

## Decision 4: Telemetry Provenance & C2 Audit Visibility

- **Decision**:
  1. Extend `SwarmTelemetryEvent` (`src/uservice/telemetry/models/contract/events.py`) with optional structured avoidance/command provenance in `extra` (or typed fields) and ensure edge avoidance maneuvers publish a QoS 1 `alert` (or `navigation` + `alert`) event containing:
     - `command_source`: `"edge_autonomous"`
     - `decision_authority`: `"edge"`
     - `action`: `"obstacle_bypass"` | `"resume_route"` | `"obstructed_hold"`
     - `obstacle_class`, `bypass_direction` (`"left"` | `"right"`), `course_delta_deg`, `previous_heading_deg`, `commanded_heading_deg`, `mission_id`, `trigger_detection_id`.
  2. In `TelemetryIngestor` (`src/uservice/telemetry/operations/ingestor.py`), when an `alert` event carries `extra.command_source == "edge_autonomous"`, persist a corresponding `AuditEvent` (`AuditEventType.EDGE_OBSTACLE_BYPASS` or `COMMAND_EXECUTED` with `ActorType.AGENT` and `actor_id = f"edge:{event.drone_id}"`) to PostgreSQL and expose it via the existing swarm telemetry/audit API and dashboard (`src/dashboard/js/main.js`).
- **Rationale**: Satisfies FR-006 and SC-002 (provenance in both published telemetry stream and central C2/operator audit view) with minimal schema disruption and full backward compatibility for existing telemetry consumers.
- **Alternatives considered**:
  - Adding a separate MQTT topic outside `telemetry/projects/+/swarms/+/+/+`: rejected because `WILDCARD_TELEMETRY_TOPIC` and `EdgeSpool` DDIL buffering already guarantee QoS 1 delivery and Parquet archival for `alert` events on the canonical topic.

## Decision 5: No-Mock End-to-End Verification Strategy

- **Decision**: Add `tests/e2e/prod_obstacle_avoidance.spec.js` (mirroring `tests/e2e/prod_fly_detect.spec.js`), configured to feed `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4` through `scripts/virtual_cam_server.py` into the live `src/edge` container/process, connected to PX4 SITL via MAVSDK, MQTT broker, `src/uservice`, PostgreSQL, and the dashboard UI.
- **Rationale**: Exercises the real video frames, real YOLO-E model, real edge LLM target-vs-obstacle discrimination, real MAVSDK course modification, real MQTT ingestion, and real C2 audit/telemetry display with zero mocks.
- **Alternatives considered**:
  - Unit-test-only verification with synthetic numpy frames: insufficient for the user's explicit requirement for a no-mock E2E test using `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`.
