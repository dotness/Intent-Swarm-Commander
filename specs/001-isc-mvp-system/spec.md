# Feature Specification: Intent Swarm Commander — MVP System

**Feature Branch**: `001-isc-mvp-system`

**Created**: 2026-07-24

**Status**: Draft

**Input**: User description: "Implement the system described in LTV Cone knowledge, design/, and design/MVP.md as minimal scope"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Commander Submits SMEAC Intent (Priority: P1)

A military commander opens the ISC web interface, enters a high-level SMEAC (Situation, Mission, Execution, Admin/Logistics, Command/Signal) order into the intent ingestion panel, and receives a structured breakdown of the order into coarse-grained drone swarm operators. The system translates human intent into actionable swarm commands before forwarding them through the compliant pipeline.

**Why this priority**: This is the core value proposition — without intent-to-action translation, no other capability has meaning. It validates the end-to-end data flow from commander input to swarm command generation.

**Independent Test**: Can be fully tested by entering a sample SMEAC order (e.g., "Situation: Enemy AA battery at grid 123456. Mission: Conduct ISR sweep of grid square. Execution: Deploy 4-drone recon formation.") and verifying the system produces a valid structured command output, even if no physical drones execute it.

**Acceptance Scenarios**:

1. **Given** the commander is authenticated and on the ISC dashboard, **When** they enter a valid SMEAC order into the intent ingestion panel and submit, **Then** the system parses the order and displays a structured command breakdown within 10 seconds.
2. **Given** the commander submits a SMEAC order with missing fields, **When** the system detects incomplete input, **Then** it highlights the missing SMEAC fields and prompts the commander to complete them before processing.
3. **Given** the commander submits a valid SMEAC order, **When** the system generates coarse-grained operators, **Then** the output includes at minimum: mission type, formation pattern, target area, and drone count.

---

### User Story 2 — HITL Approval Gate for High-Impact Actions (Priority: P1)

When the Command Agent generates an action classified as high-impact (mass abort, Rules of Engagement change, full swarm redirect), the system pauses execution and presents a mandatory Human-in-the-Loop confirmation modal to the commander. The commander must explicitly approve or reject the action before it proceeds through the pipeline.

**Why this priority**: EU AI Act compliance mandates HITL gates for irreversible autonomous decisions. Without this, the system cannot be deployed in EU regulatory scope. Co-equal with P1 Story 1 because it is a compliance blocker.

**Independent Test**: Can be tested by triggering a simulated high-impact action (e.g., "Mass Abort") and verifying the HITL modal appears, blocks execution, and only proceeds upon explicit commander approval.

**Acceptance Scenarios**:

1. **Given** the Command Agent generates a high-impact action (mass abort, ROE change, or swarm redirect), **When** the action reaches the HITL gateway, **Then** a visually prominent confirmation overlay is displayed to the commander showing the action summary, affected units, and approve/reject controls.
2. **Given** the HITL modal is displayed, **When** the commander clicks "Reject", **Then** the action is cancelled, logged in the audit trail, and the Command Agent is notified of the rejection.
3. **Given** the HITL modal is displayed, **When** the commander clicks "Approve", **Then** the action proceeds through the MCP pipeline and the approval event is logged with the commander's identity and timestamp.

---

### User Story 3 — MCP Auth Gateway Enforces Agent Identity (Priority: P2)

Every Command Agent action passes through the MCP Auth Gateway, which validates the agent's OAuth 2.1 token and enforces scope-based access control. Agents without valid credentials or with insufficient scope are denied access to protected tools.

**Why this priority**: The MCP Gateway is the foundational security chokepoint. It enables all downstream trust decisions (RBAC, audit logging, tool access). Ranked P2 because P1 stories can be prototyped with simplified auth, but production readiness requires this.

**Independent Test**: Can be tested by sending requests with valid/invalid/expired tokens to the MCP Gateway endpoint and verifying appropriate accept/reject behavior and audit log entries.

**Acceptance Scenarios**:

1. **Given** a Command Agent with a valid OAuth 2.1 token and appropriate scope, **When** it requests a tool action through the MCP Gateway, **Then** the request is authorized and forwarded to the Tool Execution Gateway.
2. **Given** a Command Agent with an expired or invalid token, **When** it requests a tool action, **Then** the MCP Gateway rejects the request and logs the denial event.
3. **Given** a Command Agent with valid authentication but insufficient scope (e.g., "Recon Only" scope attempting a "Strike" action), **When** it requests an out-of-scope tool, **Then** the gateway rejects the request with a scope violation error.

---

### User Story 4 — Safety Verification Before Swarm Execution (Priority: P2)

Before any command reaches the Swarm Pool, it passes through the Safety Verification Layer where constraint solvers validate the command against safety rules. Commands that violate safety constraints are blocked and the commander is notified with the specific constraint violation.

**Why this priority**: Without formal verification, LLM-generated commands could issue unsafe drone operations. Ranked P2 because the verification layer can initially operate with a minimal rule set and be expanded iteratively.

**Independent Test**: Can be tested by submitting commands that intentionally violate safety constraints (e.g., altitude exceeding limits, flight into restricted airspace) and verifying they are rejected with clear violation messages.

**Acceptance Scenarios**:

1. **Given** a verified command passes all safety constraint checks, **When** it exits the Safety Verification Layer, **Then** it is forwarded to the Swarm Pool for execution.
2. **Given** a command violates one or more safety constraints, **When** it is evaluated by the constraint solvers, **Then** the command is blocked, the specific violations are listed, and the commander is notified on the dashboard.
3. **Given** the Safety Verification Layer is operational, **When** any command is processed, **Then** the verification status (pass/fail with details) is visible in the Verification & Safety Status module on the UI.

---

### User Story 5 — Commander Dashboard with Tactical Awareness (Priority: P3)

The commander views a unified dashboard that includes: the SMEAC order panel, a tactical map showing drone positions and mission status, a unit roster with live status, and an action history log. The dashboard provides real-time situational awareness.

**Why this priority**: The dashboard is the primary operational interface but can initially be functional without full real-time telemetry. Core command-and-control flow (P1, P2) works through the ingestion panel; the dashboard enhances operational awareness.

**Independent Test**: Can be tested by loading the dashboard with simulated drone and mission data and verifying all UI panels render correctly with appropriate status indicators.

**Acceptance Scenarios**:

1. **Given** the commander logs in, **When** the dashboard loads, **Then** all core panels are visible: SMEAC Order Panel, Tactical Map, Unit Roster, Action History, and Verification Status Module.
2. **Given** simulated mission data is available, **When** the dashboard is active, **Then** drone positions are displayed on the tactical map and the unit roster shows current status for each unit.
3. **Given** agent identity information is available, **When** the dashboard renders, **Then** the Agent Identity & Scope indicator shows the active agent's authentication status and current RBAC scope.

---

### User Story 6 — Commander Provisions a New Swarm Instance (Priority: P2)

The commander or an automated orchestrator calls the Central Provisioning API to request the creation of a new Swarm. The system dynamically provisions a dedicated POD/Docker instance that exposes an API exclusively for that swarm's management, isolating SMEAC ingestion and command processing for performance reasons.

**Why this priority**: Addresses explicit performance constraints by ensuring computational isolation per swarm, preventing noisy neighbor issues during high-velocity command execution.

**Independent Test**: Can be tested by invoking the provisioning API and verifying that a new, addressable container is running and responds to SMEAC requests on its dedicated endpoint.

**Acceptance Scenarios**:

1. **Given** the central provisioning API is online, **When** a request to spawn a new Swarm is received, **Then** the system dynamically spawns a dedicated container and returns its connection details within 30 seconds.
2. **Given** multiple active Swarm instances, **When** SMEAC orders are sent to their respective dedicated APIs, **Then** each container processes its commands completely independently without cross-talk or shared-bottleneck degradation.

---

### Edge Cases

- What happens when the MCP Gateway is unreachable? The system must fail closed — no commands bypass the gateway. The commander sees a clear "Gateway Unavailable" status and all pending actions queue locally.
- What happens when the HITL modal times out without a response? The system defaults to autonomous execution where the Swarm Controller makes the final decision based on pre-programmed safety heuristics. Configurable timeout period with audit log entry.
- What happens when the Safety Verification Layer encounters an unrecognized constraint type? The system must fail safe — unknown constraints default to "block" rather than "allow". The event is flagged for human review.
- How does the system handle concurrent SMEAC orders from multiple commanders? Orders are queued and processed sequentially per mission context. Conflicting orders for the same swarm are flagged for deconfliction.
- What happens when an agent's JIT credential expires mid-operation? The current operation is completed if already past verification, otherwise it is paused and the agent must re-authenticate. No credential extension without explicit renewal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept SMEAC-formatted orders through a structured intent ingestion interface and parse them into the five SMEAC fields (Situation, Mission, Execution, Admin/Logistics, Command/Signal).
- **FR-002**: System MUST translate parsed SMEAC intents into coarse-grained drone swarm operators (formation type, target area, mission type, drone count).
- **FR-003**: System MUST route all agent-to-tool interactions through a centralized MCP Auth Gateway that validates OAuth 2.1 tokens.
- **FR-004**: System MUST enforce scope-based access control (RBAC) at tool granularity, ensuring agents can only access tools aligned with their authenticated privileges.
- **FR-005**: System MUST present a mandatory HITL confirmation overlay for high-impact actions (mass abort, ROE changes, swarm redirect) before they proceed through the pipeline.
- **FR-006**: System MUST log all agent actions, HITL decisions, and gateway authorizations in an immutable audit trail.
- **FR-007**: System MUST validate all commands through a Safety Verification Layer using constraint solvers before they reach the Swarm Pool.
- **FR-008**: System MUST display a commander dashboard with SMEAC Order Panel, Tactical Map, Unit Roster, Action History, Agent Identity indicators, and Verification Status Module.
- **FR-009**: System MUST fail closed when the MCP Gateway or Safety Verification Layer is unavailable — no commands bypass security or safety checks.
- **FR-010**: System MUST support JIT ephemeral agent identities with configurable time-bound lifetimes to prevent credential sprawl.
- **FR-011**: System MUST provide visual indicators of agent authentication status and current RBAC scope on the commander dashboard.
- **FR-012**: System MUST support a Durable Approval workflow where pending actions are queued for asynchronous commander review and approval/rejection.
- **FR-013**: System MUST integrate with a software-based simulated drone environment capable of receiving swarm operators and mimicking drone execution for all Swarm Pool operations; it MUST NOT attempt physical drone deployment.
- **FR-014**: System MUST expose a Central Provisioning API allowing users to request the creation of a new Swarm.
- **FR-015**: System MUST dynamically spawn a dedicated POD/Docker instance for each created Swarm to guarantee performance isolation.
- **FR-016**: The dedicated Swarm instance MUST expose its own independent API that is dynamically registered with and routed through the central MCP Auth Gateway for all subsequent SMEAC ingestion and swarm commands.

### Key Entities

- **SMEAC Order**: A structured military order containing five fields (Situation, Mission, Execution, Admin/Logistics, Command/Signal) representing commander intent. May contain free-text or structured data per field.
- **Swarm Command**: A coarse-grained operator derived from a SMEAC Order, specifying formation type, target coordinates, mission type, and assigned drone count. The atomic unit of execution sent to the Swarm Pool.
- **Command Agent**: An AI agent with a cryptographically verified identity that translates SMEAC Orders into Swarm Commands. Operates under JIT ephemeral credentials with scoped RBAC permissions.
- **HITL Decision**: A recorded approval or rejection event from a human commander for a high-impact action, including commander identity, timestamp, action summary, and decision rationale.
- **Constraint Violation**: A safety check result indicating a proposed command violates one or more rules in the Safety Verification Layer, including the violated rule identifier, severity, and recommended remediation.
- **Audit Event**: An immutable log entry recording any significant system action — agent requests, HITL decisions, gateway authorizations, constraint check results, and swarm command executions.
- **Central Provisioning API**: The control plane interface responsible for orchestrating the lifecycle (spawning/terminating) of Dedicated Swarm Instances.
- **Dedicated Swarm Instance**: A dynamically spawned POD/Docker container providing dedicated compute resources and an isolated API specifically for managing a single swarm.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Commanders can submit a SMEAC order and receive a structured swarm command breakdown within 15 seconds of submission.
- **SC-002**: 100% of high-impact actions (mass abort, ROE change, swarm redirect) trigger the HITL confirmation overlay before execution — zero bypass rate.
- **SC-003**: 100% of agent actions are logged in the audit trail with sufficient detail for post-incident review.
- **SC-004**: Commands that violate safety constraints are blocked with a 0% false-negative rate (no unsafe commands pass through).
- **SC-005**: Commanders can view the current status of all active agents, their authentication state, and RBAC scope at a glance on the dashboard.
- **SC-006**: The system defaults to safe failure modes (fail closed) when any security or verification component is unavailable, with zero commands bypassing security gates during outages.
- **SC-007**: Pending HITL approvals are persisted and remain accessible for commander review even if the commander's session is interrupted and resumed later.

## Assumptions

- **Target Users**: Military commanders with domain expertise in SMEAC order format operating from a desktop or field workstation with a modern web browser.
- **Connectivity**: The commander workstation has reliable network connectivity to the Command Post edge server. Intermittent connectivity between edge and tactical field is expected but out of MVP scope for resilience handling.
- **Drone Simulation**: The MVP exclusively uses a software-based drone simulation setup. Physical drone integration is strictly out of scope for the current MVP, which focuses on validating the end-to-end pipeline from intent to simulated execution.
- **Authentication Infrastructure**: An external identity provider (IdP) is available or can be mocked for MVP purposes. Full enterprise IdP integration (Okta/Entra) is a fast-follow concern.
- **Constraint Rule Set**: The Safety Verification Layer operates with a minimal, manually defined rule set for MVP. Full SORA 2.5 ontology encoding and NSVIF solver deployment are post-MVP milestones.
- **Multi-Commander Operations**: MVP supports multiple concurrent commander sessions. SMEAC orders from multiple commanders targeting the same swarm are queued and processed sequentially.
- **Scope Boundary**: Remote ID/UTM integration, MCP Registry discovery, MINT neuro-symbolic planning, and full SORA 2.5 machine-readable encoding are explicitly out of MVP scope (Tier 2 or later LTV nodes).
