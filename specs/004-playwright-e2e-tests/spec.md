# Feature Specification: Playwright End-to-End Test Suite

**Feature Directory**: `specs/004-playwright-e2e-tests`

**Created**: 2026-09-12

**Status**: Ready for Planning

**Input**: User description: "i want you to create full end to end tests using playwright that will test all features of the system."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Commander Authentication & Session Lifecycle (Priority: P1)

As a tactical drone commander, I need to authenticate securely into the command dashboard so that only authorized personnel can access swarm controls and issue mission orders.

**Why this priority**: Security and role-based access control are prerequisite gateways (FR-009) to all swarm operations. Without passing authentication, no dashboard or swarm commands are accessible.

**Independent Test**: Can be fully tested by attempting login with invalid credentials (verifying rejection), followed by valid credentials (verifying token receipt, modal dismiss, badge update, and session preservation across page reloads).

**Acceptance Scenarios**:

1. **Given** an unauthenticated session on `http://localhost:8080`, **When** the page loads, **Then** the Commander Login modal is displayed with Commander ID and Passphrase fields.
2. **Given** the login modal is visible, **When** the commander enters an incorrect passphrase and submits, **Then** an explicit "Invalid credentials" or error message is displayed and the modal remains open.
3. **Given** the login modal is visible, **When** the commander enters a valid Commander ID (`commander-alpha`) and Passphrase (`dev_passphrase`), **Then** authentication succeeds, a JWT token is stored, the modal disappears immediately, and the top bar shows `Auth: agent-commander-alpha-...`.
4. **Given** an authenticated session, **When** the page is reloaded, **Then** the login modal remains hidden and authentication state persists without prompting for credentials again.

---

### User Story 2 - Swarm Discovery & Real-Time Telemetry Mapping (Priority: P2)

As a tactical commander, I need to inspect active swarms and view live drone coordinates and operational states on the tactical map so that I have complete situational awareness.

**Why this priority**: Real-time visibility into drone locations, altitudes, velocities, and battery states is fundamental before dispatching tactical intents.

**Independent Test**: Can be tested independently by logging in, selecting a swarm from the dropdown, and verifying that map markers appear on the Leaflet map and update periodically with live telemetry data.

**Acceptance Scenarios**:

1. **Given** an authenticated commander, **When** the dashboard initializes, **Then** the Swarm selector dropdown is populated with available swarms retrieved from `/api/v1/swarms`.
2. **Given** available swarms in the dropdown, **When** a swarm (e.g., `swarm-alpha`) is selected, **Then** live telemetry polling begins for `/api/v1/swarms/{swarm_id}/telemetry`.
3. **Given** telemetry data containing drone positions, **When** received by the dashboard, **Then** interactive markers appear on the Leaflet tactical map reflecting the drones' coordinates, operational mode, and battery levels.

---

### User Story 3 - Tactical SMEAC Order Composition and Dispatch (Priority: P3)

As a tactical commander, I need to draft and submit SMEAC (Situation, Mission, Execution, Administration, Command) orders through the dashboard form so that my high-level intent is validated, translated into Swarm Commands, and scheduled for execution.

**Why this priority**: Translating human intent into structured drone commands is the core objective of the Intent Swarm Commander microservice.

**Independent Test**: Can be tested by filling in SMEAC form fields for an active swarm, submitting the order, and verifying successful dispatch and receipt of order confirmation.

**Acceptance Scenarios**:

1. **Given** an active swarm selected, **When** the commander submits an incomplete SMEAC form missing mandatory fields (e.g. empty Situation or Mission), **Then** HTML5 client-side validation prevents submission and alerts the user.
2. **Given** an active swarm selected, **When** the commander fills in valid Situation, Mission, Execution, Administration, and Command fields and clicks Submit, **Then** a POST request is sent to `/api/v1/swarms/{swarm_id}/orders` with the commander's Bearer token.
3. **Given** a successful order submission, **When** the backend accepts the order, **Then** the UI provides positive feedback indicating successful translation and dispatch.

---

### User Story 4 - Human-in-the-Loop (HITL) Critical Action Approval Gate (Priority: P4)

As a mission safety officer or tactical commander, I must be prompted to review, approve, or reject high-impact or ambiguous actions before irreversible kinetic or flight path changes execute.

**Why this priority**: Compliance with ethical AI governance and the EU AI Act requires an explicit human-in-the-loop safety supervisor (HITL) gateway for critical operations.

**Independent Test**: Can be tested by triggering a pending HITL decision in the backend, observing the appearance of the HITL dialog on the dashboard, approving or rejecting the decision, and confirming state transition.

**Acceptance Scenarios**:

1. **Given** a swarm with a pending HITL decision requiring approval, **When** the dashboard polls `/api/v1/swarms/{swarm_id}/hitl/pending`, **Then** the high-impact approval modal is displayed showing details of the requested action.
2. **Given** the HITL modal is displayed, **When** the commander clicks "Approve", **Then** an approval POST request is sent to `/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide` with `decision: "approved"`, the modal closes, and the decision is marked approved.
3. **Given** the HITL modal is displayed, **When** the commander clicks "Reject", **Then** a rejection POST request is sent to `/api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide` with `decision: "rejected"`, the modal closes, and execution is aborted.

---

### User Story 5 - Resiliency, Error Handling, and Security Boundaries (Priority: P5)

As an operations administrator, I need the system to handle network interruptions, unauthorized API tampering, and expired tokens gracefully without corrupting state or exposing sensitive internals.

**Why this priority**: Ensures system robustness, security fail-closed semantics (FR-009), and diagnostic visibility during degraded field conditions.

**Independent Test**: Can be tested by simulating invalid tokens, expired sessions, and offline backend scenarios.

**Acceptance Scenarios**:

1. **Given** an expired or tampered token, **When** an API call is made, **Then** the backend responds with HTTP 401 Unauthorized, and the dashboard clears the session and prompts for re-authentication.
2. **Given** the backend API is unreachable, **When** a commander attempts an action, **Then** appropriate error messaging is displayed without crashing the UI.

---

### Edge Cases

- **Rapid Multiple Form Submissions**: Clicking "Authenticate" or "Submit Order" repeatedly before the first request finishes must not trigger duplicate calls or corrupted states.
- **Empty Swarm Roster**: When zero swarms are registered, the dashboard displays an informative empty state instead of crashing.
- **Map Viewport Resizing**: Dynamic browser window resizing does not break the Leaflet tile layer or misplace drone markers.
- **Malformed SMEAC Input**: Entering special characters, Unicode, or boundary-length text strings in SMEAC textarea fields does not cause parsing crashes or XSS vulnerabilities.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an automated end-to-end test suite using Playwright that tests all critical system user flows across frontend and backend.
- **FR-002**: Test suite MUST verify the Commander Login workflow, including rejection on invalid credentials and successful authentication on valid credentials.
- **FR-003**: Test suite MUST verify session persistence, ensuring stored JWT tokens maintain dashboard access across browser reloads.
- **FR-004**: Test suite MUST verify swarm discovery by checking dropdown population from the live backend API.
- **FR-005**: Test suite MUST verify telemetry mapping, ensuring Leaflet map markers are rendered for active drones with coordinate data.
- **FR-006**: Test suite MUST verify SMEAC order submission, validating payload transmission and API response handling.
- **FR-007**: Test suite MUST verify the Human-in-the-Loop (HITL) approval workflow, including modal rendering, approval submission, and rejection submission.
- **FR-008**: Test suite MUST verify security fail-closed behavior on 401 responses and unauthorized access attempts.
- **FR-009**: Test suite MUST execute against the live running container stack (`localhost:8080` dashboard and `localhost:8000` API) without mock servers.
- **FR-010**: Test suite MUST generate structured execution reports (console test results, HTML report, and failure screenshots/traces).
- **FR-011**: Test suite MUST be runnable both locally via a single command (e.g., `npm test` or `npx playwright test`) and within headless CI/CD automation.

### Key Entities

- **CommanderSession**: Represents the authenticated operator session, holding the commander callsign, JWT Bearer token, expiration timestamp, and granted scopes (`smeac:create`, `smeac:read`, `hitl:decide`, `hitl:read`).
- **SwarmRoster**: List of active drone swarms (`id`, `name`, `status`, `drone_count`) available for tactical tasking.
- **DroneTelemetry**: Real-time state of an individual drone, including latitude, longitude, altitude, velocity, battery percentage, and mode.
- **SmeacOrder**: Structured operational intent consisting of Situation, Mission, Execution, Administration, and Command fields submitted to a specific swarm.
- **HitlDecision**: High-impact operational action awaiting human authorization, containing decision ID, description, risk level, and resolution status (`pending`, `approved`, `rejected`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of end-to-end test scenarios pass against the running Intent Swarm Commander stack.
- **SC-002**: Complete test suite execution finishes in under 60 seconds.
- **SC-003**: Zero flaky tests across 3 consecutive test runs.
- **SC-004**: Comprehensive coverage across all 5 user journeys (Auth, Telemetry, SMEAC, HITL, Resiliency).
- **SC-005**: A single reproducible command (`npm test` / `npx playwright test`) executes the complete suite and produces an actionable report.

## Assumptions

- The Intent Swarm Commander container stack is running locally on `localhost:8080` (dashboard) and `localhost:8000` (backend microservice).
- Node.js (v22+) is available in the environment to run Playwright test runner.
- Default test credentials use Commander ID `commander-alpha` and passphrase `dev_passphrase`.
