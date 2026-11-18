# Feature Specification: Edge-Autonomous Obstacle Detection and Avoidance

**Feature Branch**: `011-edge-obstacle-avoidance`

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "New feature where drones can automatically detect obstacles on their way and they automatically bypass the obstacle. I want the auto decision and instructions to be given by edge. Part of the feature is to be a e2e nomock test, where we feed a video (tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4) to a drone flying straight and in the video drone has a lamp post in front of it. It is an obstacle. I want the drone to bypass it. The telemetry has to prove that edge system ordered the drone to modify the course to bypass the obstacle. Note: detecting targets that were ordered in order is to be still supported. Thus if drone detects obstacle and that obstacle is the target, it is to fly to.it not bypass. So edge needs to know difference between target and obstacle."

## Clarifications

### Session 2026-11-17

- Q: How should the edge system determine whether a detected object in the forward flight path is an ordered mission target rather than an obstacle to bypass? → A: The edge LLM matches detected object class/label (and optional order attributes) against the active mission order's target specification; if matched, the drone continues target-approach behavior instead of bypassing.
- Q: What bypass maneuver should the edge system command when a non-target obstacle is detected ahead? → A: Dynamic lateral detour (steer left or right toward the clearest open side), then resume the original mission route once clear.
- Q: Where must the edge-issued obstacle avoidance decision and course-modification proof be recorded and verifiable? → A: Both the published flight telemetry stream/log and the central C2/operator audit view.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Edge-Autonomous Obstacle Detection and Bypass (Priority: P1)

While a drone is flying along its planned route, its onboard/edge perception system continuously monitors the forward flight path for physical obstructions. When an obstacle (such as a lamp post, pole, tree, or structure) appears in the drone's path, the edge system autonomously decides that a collision risk exists, computes a safe detour, and issues course-modification instructions directly to the drone so it smoothly bypasses the obstacle and resumes its mission route without requiring ground-station or human intervention.

**Why this priority**: Autonomous collision avoidance at the edge is the core safety and mission-continuity capability of this feature. Without low-latency edge decision-making, drones flying in cluttered environments risk collision before a remote operator or central server can react.

**Independent Test**: Can be tested independently by flying a drone on a straight course while feeding it a real forward-facing video stream containing an obstacle (`tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`), with no mission target matching that obstacle, and verifying that the drone alters its course to bypass the lamp post and records edge-issued avoidance commands in telemetry.

**Acceptance Scenarios**:

1. **Given** a drone is flying straight on an active mission with no target matching a lamp post, **When** the forward video feed (`tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`) shows a lamp post directly ahead in the flight corridor, **Then** the edge system classifies the lamp post as an obstacle, autonomously issues a course-modification command to bypass it, and the drone maneuvers around the obstacle without colliding.
2. **Given** the edge system has issued an obstacle-bypass course modification, **When** the drone has cleared the obstacle, **Then** the edge system guides the drone back toward its original planned flight path so the mission continues.
3. **Given** an avoidance maneuver is executed, **When** an operator or automated verifier inspects the mission telemetry, **Then** the telemetry stream contains an explicit, timestamped record proving that the edge system (rather than a human operator or central planner) ordered the course modification and specifies the bypass direction/action.

---

### User Story 2 - Target vs. Obstacle Discrimination (Priority: P1)

During a mission where the drone has been ordered to locate, approach, or track a specific target (as defined in the active mission order), the edge system must distinguish between mission targets and non-target obstacles. If an object detected directly in the drone's path matches an ordered mission target, the drone must continue flying toward/engaging that target instead of bypassing it. If the detected object does not match any ordered target, it is treated as an obstacle and bypassed.

**Why this priority**: Equal priority to obstacle avoidance because indiscriminate avoidance would break existing target-acquisition missions—a drone ordered to fly to a specific vehicle, person, or structure would otherwise steer away from its own objective upon approaching it.

**Independent Test**: Can be tested independently by issuing a mission order whose target descriptor matches an object present in the forward video feed, and verifying that the edge system classifies the detected object as the ordered target and maintains approach/tracking rather than issuing a bypass command.

**Acceptance Scenarios**:

1. **Given** an active mission order specifying a target (e.g., a vehicle or designated marker) and a non-target obstacle (e.g., a lamp post) appears in the flight path, **When** the edge system detects the lamp post, **Then** it determines the object does not match the ordered target and issues a bypass command.
2. **Given** an active mission order specifying a target that matches the object detected ahead in the flight path, **When** the edge system detects that object, **Then** it classifies the object as the ordered target and commands the drone to proceed toward/track the target rather than bypassing it.
3. **Given** a mission where both an ordered target and an unrelated obstacle are visible in the same forward scene, **When** the edge system evaluates the scene, **Then** it routes the drone around the unrelated obstacle while preserving approach/alignment toward the ordered target.

---

### User Story 3 - End-to-End Real-Media Verification and Telemetry Auditability (Priority: P2)

Operators and quality assurance teams can run an end-to-end verification using real flight video without simulated perception or stubbed flight-control responses, confirming that the full chain—video ingestion, edge obstacle/target classification, edge course-modification decision, drone flight response, and telemetry logging—operates cohesively and produces auditable proof of edge-initiated avoidance.

**Why this priority**: Real-media, end-to-end verification without mocks is essential to prove that perception, edge decision logic, flight execution, and telemetry provenance work together under realistic visual conditions.

**Independent Test**: Can be tested independently by executing the end-to-end scenario with `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4` against the live system components and asserting both physical/simulated flight trajectory deviation around the obstacle and edge-authored avoidance records in the resulting telemetry.

**Acceptance Scenarios**:

1. **Given** the live end-to-end system is running without mocked perception or mocked edge decision-makers, **When** `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4` is streamed as the drone's forward camera feed while the drone is commanded to fly straight, **Then** the drone's telemetry shows an initial straight flight phase, followed by an edge-ordered course modification upon detecting the lamp post, followed by a lateral/vertical bypass trajectory.
2. **Given** the end-to-end avoidance run completes, **When** the telemetry log is audited, **Then** every avoidance command is traceable to the edge decision authority, linked to the detected obstacle event, and distinguishable from operator-issued mission waypoints.

---

### Edge Cases

- **No clear bypass corridor**: What happens when an obstacle spans the entire forward field of view or adjacent space is also obstructed? The edge system must command the drone to decelerate and hold position (hover) safely while raising an obstruction alert to the operator, rather than steering into another hazard.
- **Ambiguous target vs. obstacle confidence**: What happens when a detected object partially resembles an ordered target but confidence is below the target-match threshold? The edge system must default to treating the object as an obstacle (fail-safe) to prevent accidental collision, while reporting the uncertain detection for operator awareness.
- **Multiple sequential or simultaneous obstacles**: What happens when a second obstacle enters the bypass path while the drone is already executing a detour? The edge system must re-evaluate the updated forward corridor and adjust the bypass trajectory until a clear path is achieved.
- **Loss or degradation of video feed**: What happens when the forward visual feed freezes, drops frames, or becomes unreadable during flight? The edge system must detect the perception gap, avoid issuing blind course changes, and transition to a safe hold/hover or operator-fallback state with an alert.
- **Target becomes obstructed mid-approach**: What happens when an obstacle lies directly between the drone and a confirmed ordered target? The drone must bypass the intervening obstacle and then re-acquire and continue toward the target.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The edge system MUST continuously analyze the drone's forward visual feed during active flight to detect physical obstacles in the drone's projected flight corridor.
- **FR-002**: The edge system's LLM MUST evaluate each detected object's class/label (and optional attributes) against the active mission order's target specification to determine whether the object is an ordered target or a non-target obstacle.
- **FR-003**: When a detected object is classified as a non-target obstacle posing a collision risk, the edge system MUST autonomously compute a dynamic lateral detour (steering left or right toward the clearest open side) and issue course-modification instructions directly to the drone without waiting for central server or human operator approval.
- **FR-004**: When a detected object matches an ordered target from the active mission order, the edge system MUST preserve target-approach/tracking behavior and MUST NOT trigger an obstacle-bypass maneuver against that target.
- **FR-005**: After bypassing an obstacle and confirming the forward corridor is clear, the edge system MUST instruct the drone to resume progress toward its active mission destination or target.
- **FR-006**: Every course-modification instruction issued by the edge system for obstacle avoidance MUST be recorded in both the published flight telemetry stream/log and the central C2/operator audit view with an explicit edge-decision provenance marker, timestamp, obstacle classification context, and commanded course adjustment.
- **FR-007**: When no safe bypass corridor is available or forward perception is lost during an active flight, the edge system MUST command the drone to hold/hover safely and emit an operator-visible alert.
- **FR-008**: The system MUST support end-to-end verification using real forward-facing flight video (specifically including `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`) without mocked perception or mocked edge decision-making, producing verifiable telemetry proving edge-ordered obstacle bypass.

### Key Entities

- **Obstacle Detection Event**: Represents a non-target physical object detected in the drone's projected flight path, including object classification, relative position/proximity, confidence, and timestamp.
- **Mission Order Target**: Represents the target specification(s) received in an active mission order (such as target category, visual/semantic descriptor, and priority), used by the edge system to distinguish targets from obstacles.
- **Edge Avoidance Command**: Represents an autonomous flight-course modification generated and issued by the edge system, containing command provenance (identifying the edge system as the decision-maker), maneuver direction/offset, trigger obstacle reference, and timestamp.
- **Flight Telemetry Record**: Represents the auditable time-series log of drone position, heading, velocity, and received commands, enabling post-flight and real-time verification of who ordered each course change and why.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the end-to-end real-video verification using `tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`, the drone detects the lamp post obstacle, executes a bypass maneuver, and completes the run without a simulated collision 100% of the time across verification runs.
- **SC-002**: 100% of edge-initiated bypass maneuvers produce corresponding telemetry records in both the flight telemetry stream and the central C2/operator audit view that unambiguously identify the edge system as the command originator and show a measurable course deviation away from the obstacle's path.
- **SC-003**: In target-acquisition scenarios where an ordered target appears directly ahead of the drone, the edge system correctly classifies the object as the ordered target and maintains approach behavior (zero false-positive bypasses of confirmed targets) at least 95% of the time.
- **SC-004**: The edge system issues a course-modification instruction within 500 milliseconds of an obstacle entering the critical collision-risk zone in the forward video stream, without requiring round-trip communication to a remote operator.

## Assumptions

- Each drone's active mission order (including any target specifications to seek/track) is delivered to the edge system at mission start or upon order update, so the edge system has local access to target definitions for real-time comparison.
- A standard bypass maneuver is a dynamic lateral detour (left or right toward the clearest open side) around the obstacle followed by re-alignment to the planned route once the obstacle is cleared, within the drone's configured flight-envelope limits.
- Forward-facing video is the primary sensing input for this feature; depth or proximity estimation may be derived from the visual stream and/or onboard flight sensors available to the edge unit.
- The end-to-end no-mock test environment uses real video frame streaming (`tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4`) into the live perception, edge decision, flight-control, and telemetry pipeline without stubbing the obstacle detector or edge decision logic.
