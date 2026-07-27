# Feature Specification: Replace Mocks, Stubs & Hardcodes with Production Implementations

**Feature Branch**: `002-replace-mocks-production`

**Created**: 2026-07-27

**Status**: Draft

**Input**: User description: "Go over the mocks/stubs/hardcodes todo file and remove all mocks, stubs, or hardcoded data — replace with actual production implementations."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticated Dashboard Operations (Priority: P1)

A commander opens the web dashboard and is authenticated through the real authentication system. The dashboard retrieves a valid security token from the authentication service instead of using a hardcoded placeholder. All API calls from the dashboard (telemetry, HITL decisions) carry the real token. If the token expires or is invalid, the user receives a clear re-authentication prompt.

**Why this priority**: Without real authentication, the system is completely open to unauthorized access. This is the foundational security requirement — nothing else can be trusted if identity and access control are faked.

**Independent Test**: Can be tested by logging into the dashboard, verifying a real token is issued, and confirming that API calls fail with an appropriate error when the token is missing or expired.

**Acceptance Scenarios**:

1. **Given** a commander navigates to the dashboard, **When** they provide valid credentials, **Then** the system issues a real authentication token and the dashboard uses it for all subsequent API calls.
2. **Given** a commander has an expired token, **When** they attempt to fetch telemetry or submit a HITL decision, **Then** the system returns an authentication error and prompts the user to re-authenticate.
3. **Given** an unauthenticated user, **When** they attempt to access dashboard endpoints, **Then** all requests are rejected with a 401 Unauthorized response.

---

### User Story 2 - Persistent Backend State (Priority: P1)

A commander creates a swarm mission, submits SMEAC orders, and manages HITL decisions. All state (swarm records, pending decisions, order statuses) is persisted to the database instead of being held in in-memory dictionaries. When the service restarts, all data is preserved and operations resume from the last known state.

**Why this priority**: In-memory state is lost on any restart, crash, or scaling event. Without persistence, the system cannot be considered operational beyond a single demo session. This is equally critical as authentication.

**Independent Test**: Can be tested by creating a swarm, submitting orders, restarting the backend services, and confirming all state is preserved and retrievable.

**Acceptance Scenarios**:

1. **Given** a commander creates a new swarm, **When** the swarm record is created, **Then** it is persisted in the database and survives service restarts.
2. **Given** a HITL decision is pending, **When** the HITL service restarts, **Then** the pending decision is still available for the commander to act on.
3. **Given** a SMEAC order has been submitted, **When** the commander queries order status, **Then** the system returns the real status from the database, not a hardcoded mock response.
4. **Given** multiple orders exist, **When** the commander retrieves statuses, **Then** each order reflects its actual processing state (pending, in-progress, completed, failed).

---

### User Story 3 - Enforced Access Control & Safety Checks (Priority: P1)

A commander or operator interacts with the system and all RBAC permission checks are enforced in real-time. SMEAC operations validate that the requesting user has the required role and permissions. Safety checks (Guardian Critic) are executed before mission-critical operations proceed. HITL verification requires actual human approval before operations advance.

**Why this priority**: Commented-out RBAC and mocked safety checks represent critical security and safety gaps. In a drone swarm system, bypassing these could result in unauthorized operations or unsafe mission execution.

**Independent Test**: Can be tested by attempting operations with different user roles and verifying that unauthorized users are blocked, safety checks execute and can reject unsafe orders, and HITL approval is genuinely required.

**Acceptance Scenarios**:

1. **Given** a user without commander permissions, **When** they attempt to submit a SMEAC order, **Then** the system rejects the request with a 403 Forbidden response.
2. **Given** a SMEAC order is submitted, **When** the safety check (Guardian Critic) evaluates it, **Then** the safety result determines whether the order proceeds or is blocked.
3. **Given** a mission requires HITL approval, **When** the verification step is reached, **Then** the system pauses and waits for actual human confirmation before proceeding.

---

### User Story 4 - Real-time Drone Telemetry (Priority: P2)

A commander views the dashboard and sees real telemetry data from drones — position, speed, battery, mission status — streamed from the backend telemetry service rather than a hardcoded simulated array.

**Why this priority**: While authentication and persistence are prerequisites, live telemetry is the primary operational value of the dashboard. Without it, the dashboard is non-functional for real missions.

**Independent Test**: Can be tested by running at least one drone (or simulator), verifying that telemetry data flows from the edge to the backend and appears in the dashboard with values that change over time.

**Acceptance Scenarios**:

1. **Given** drones are actively reporting, **When** the dashboard fetches telemetry, **Then** it receives real-time data reflecting actual drone states.
2. **Given** a drone goes offline, **When** the dashboard polls telemetry, **Then** the missing drone's status reflects its unavailability rather than showing stale hardcoded data.
3. **Given** multiple drones are active, **When** the dashboard displays telemetry, **Then** each drone shows individually accurate and distinct data.

---

### User Story 5 - Real Container Provisioning for Swarms (Priority: P2)

A commander creates a swarm and the system provisions actual Docker containers for each swarm agent instead of generating simulated container IDs. When a swarm is deleted, the real containers are terminated and cleaned up.

**Why this priority**: Container provisioning is the mechanism by which drone agents are deployed. Without real provisioning, no actual swarm can operate.

**Independent Test**: Can be tested by creating a swarm, verifying Docker containers are launched with correct configurations, and then deleting the swarm and confirming containers are terminated.

**Acceptance Scenarios**:

1. **Given** a commander creates a swarm with N agents, **When** provisioning runs, **Then** N real Docker containers are started and their IDs are recorded.
2. **Given** a swarm is deleted, **When** termination is initiated, **Then** all associated containers are stopped and removed, with the system waiting for confirmation of completion.
3. **Given** container provisioning fails, **When** the error occurs, **Then** the system reports the failure, performs partial cleanup, and does not leave orphaned containers.

---

### User Story 6 - Geofencing Enforcement (Priority: P2)

A drone operator defines restricted zones, and the geofencing check returns actual zone boundary violations instead of always returning `None`. If a drone's planned or actual trajectory enters a restricted zone, the system flags or blocks the operation.

**Why this priority**: Geofencing is a safety-critical feature for any autonomous drone system. Without it, drones could operate in restricted airspace.

**Independent Test**: Can be tested by defining a restricted zone, plotting a drone path that crosses it, and verifying the system detects and responds to the violation.

**Acceptance Scenarios**:

1. **Given** a restricted zone is defined, **When** a drone's path enters the zone, **Then** `check_geofencing` returns the zone details and the operation is flagged or blocked.
2. **Given** no restricted zones are defined, **When** a drone operates freely, **Then** `check_geofencing` returns `None` as expected.
3. **Given** multiple restricted zones exist, **When** a path intersects any of them, **Then** all violated zones are reported.

---

### User Story 7 - Production Edge Hardware Integration (Priority: P3)

Edge devices run with real hardware integrations — camera feeds via OpenCV, object detection via YOLO, and flight control via MAVSDK — instead of simulation fallbacks. The system gracefully handles hardware unavailability by reporting errors clearly rather than silently switching to simulation mode.

**Why this priority**: Edge hardware integration is essential for field deployment but can still be tested partially through simulation during development. The key change is making simulation an explicit, configurable mode rather than a silent fallback.

**Independent Test**: Can be tested by deploying to an edge device with hardware attached and verifying real camera frames, real detections, and real flight commands are produced.

**Acceptance Scenarios**:

1. **Given** a camera is connected, **When** `read_frame()` is called, **Then** it returns a real camera frame, not a simulated black image.
2. **Given** YOLO/ultralytics is installed and a model is loaded, **When** `detect()` is called with a real frame, **Then** it returns actual detection results.
3. **Given** MAVSDK is installed and connected to a flight controller, **When** a yaw command is issued, **Then** the command is sent to the actual flight controller instead of being a no-op.
4. **Given** hardware is unavailable, **When** the system starts, **Then** it reports a clear error with diagnostic information rather than silently falling back to simulation.
5. **Given** the `frame_center_x` value, **When** the flight controller initializes, **Then** it derives the value from the actual camera resolution instead of using a hardcoded `320`.

---

### User Story 8 - Secure API Gateway Routing (Priority: P3)

The security proxy routes requests to the appropriate microservice endpoints using the dynamic service registry. Requests that do not match a registered endpoint are rejected with an appropriate error, rather than falling through to local routes.

**Why this priority**: The security proxy is the entry point for all external traffic. While it functions for local development, production deployment requires proper routing and rejection of unmatched requests.

**Independent Test**: Can be tested by sending requests to registered and unregistered endpoints and verifying correct routing and rejection behavior.

**Acceptance Scenarios**:

1. **Given** a request targets a registered dynamic endpoint, **When** the proxy receives it, **Then** it routes to the correct microservice.
2. **Given** a request targets an unknown endpoint, **When** the proxy receives it, **Then** it returns a 404 or 503 error instead of falling through to local routes.

---

### Edge Cases

- What happens when the authentication service is temporarily unavailable? (Dashboard should show a clear connection error, not crash.)
- What happens when the database is unreachable during state persistence? (Operations should fail gracefully with queued retries or clear error messages.)
- What happens when Docker daemon is unavailable during container provisioning? (System should report the error and not create partial swarm records.)
- What happens when a hardware component becomes unavailable mid-operation? (Edge should detect the failure and report it rather than silently producing empty data.)
- What happens when RBAC denies access but the user was previously authorized? (Clear session expiry or permission change messaging.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Dashboard MUST authenticate users through the real authentication service and obtain valid tokens for API calls.
- **FR-002**: Dashboard MUST NOT contain any hardcoded authentication tokens or mock identity values.
- **FR-003**: Dashboard telemetry MUST fetch real data from the backend telemetry endpoint, not return hardcoded arrays.
- **FR-004**: SMEAC facade MUST enforce RBAC permission checks on all operations (un-commenting and activating the permission validation).
- **FR-005**: SMEAC facade MUST persist order data to the database instead of using mocked/commented-out persistence.
- **FR-006**: SMEAC `get_order_status` MUST return the actual order status from the database, not a hardcoded mock dictionary.
- **FR-007**: SMEAC process operations MUST execute the Guardian Critic safety check activity before proceeding with mission-critical operations.
- **FR-008**: SMEAC process operations MUST require real HITL verification (actual human approval) instead of hardcoding `hitl_approved = True`.
- **FR-009**: HITL facade MUST use database-backed persistence (and Temporal signals where applicable) instead of in-memory `_pending_decisions` dictionary.
- **FR-010**: Swarm creation MUST provision real Docker containers and persist swarm records to the database instead of using in-memory `_swarms` registry.
- **FR-011**: Swarm deletion MUST terminate actual containers and wait for confirmation instead of simulating instant termination.
- **FR-012**: Geofencing check MUST evaluate drone positions against defined restricted zones instead of always returning `None`.
- **FR-013**: Security proxy MUST reject requests to unregistered endpoints with an appropriate error code instead of falling through to local routes.
- **FR-014**: Edge camera module MUST capture real frames from the connected camera hardware when available.
- **FR-015**: Edge inference module MUST run YOLO detection on real frames when the model is available.
- **FR-016**: Edge flight controller MUST send real MAVSDK commands instead of using no-op placeholders.
- **FR-017**: Edge flight controller MUST derive `frame_center_x` from actual camera resolution instead of hardcoding `320`.
- **FR-018**: Edge flight controller MUST use actual telemetry data for `approach_distance_m` instead of manual simulation decrements.
- **FR-019**: Edge modules MUST report clear errors (with diagnostics) when required hardware is unavailable, instead of silently switching to simulation mode.
- **FR-020**: Edge API server MUST require FastAPI as a dependency and fail with a clear error if it is not installed, instead of running as a stub.

### Key Entities

- **Authentication Token**: A short-lived credential issued by the authentication service, used by the dashboard and API clients to authorize requests. Key attributes: issuer, expiration, associated user/role.
- **Swarm Record**: A persistent record representing a deployed swarm, including agent count, container IDs, status, and creation metadata. Previously held only in memory.
- **Pending Decision**: A HITL decision awaiting human approval, persisted in the database and associated with a specific mission operation. Previously held in an in-memory dictionary.
- **SMEAC Order**: A mission order with lifecycle status (pending, in-progress, completed, failed), persisted in the database. Previously returned hardcoded mock status.
- **Restricted Zone**: A geographic boundary defining an area where drone operations are prohibited. Used by geofencing checks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero hardcoded authentication tokens remain in the codebase — all API calls use dynamically issued tokens from the authentication service.
- **SC-002**: All stateful operations (swarms, HITL decisions, SMEAC orders) survive a full service restart without data loss.
- **SC-003**: 100% of SMEAC operations enforce RBAC — unauthorized requests are rejected within 500ms.
- **SC-004**: Safety checks (Guardian Critic) execute for every mission-critical operation and can block unsafe orders.
- **SC-005**: HITL verification requires actual human interaction — operations do not auto-approve.
- **SC-006**: Dashboard displays real-time telemetry data that updates at least every 2 seconds when drones are active.
- **SC-007**: Swarm creation provisions real containers — `docker ps` confirms running containers matching swarm agent count.
- **SC-008**: Swarm deletion terminates all associated containers — `docker ps` confirms no orphaned containers remain.
- **SC-009**: Geofencing detects zone violations when a drone path intersects a defined restricted zone.
- **SC-010**: Security proxy rejects requests to unregistered endpoints with appropriate error codes (404).
- **SC-011**: Edge modules produce real hardware output (camera frames, detections, flight commands) when hardware is connected.
- **SC-012**: Edge modules fail with clear error messages when required hardware is unavailable, rather than silently degrading to simulation.

## Assumptions

- The project already has a working authentication service (or one that can be integrated) for token issuance and validation.
- A database system (e.g., PostgreSQL) is already provisioned or planned for the backend microservices to persist state.
- Temporal workflow engine is available (or planned) for HITL signal-based decision flows.
- Docker daemon is available and accessible from the swarm microservice for container provisioning.
- MAVSDK, OpenCV, and YOLO/ultralytics are installable on target edge hardware for real hardware integration.
- Simulation mode for edge components may be retained as an explicitly configurable option (e.g., via environment variable) for development and testing, but it must never be the silent default.
- The SMEAC Guardian Critic safety check is defined as a Temporal activity or callable service that can evaluate order safety.
- Geofencing restricted zone definitions are stored in a configuration source or database accessible to the swarm service.
