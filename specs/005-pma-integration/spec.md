# Feature Specification: Poor-Man's Artemis.IA (PMA) C4ISR Integration

**Feature Branch**: `005-pma-integration`  
**Created**: 2026-11-14  
**Status**: Draft  
**Input**: User description: "based on docs/analysis/compatibility_with_pma.md i want to integrate usage of Poor mans artemis in this project, ask questions so that i can decide how to integrate it."

## Clarifications

### Session 2026-11-14

- Q: How should the system handle SMEAC orders that intersect an active dynamic Threat Zone? → A: Block auto-approval and route to the HITL gate with threat details; allow an authorized commander to explicitly override with a mandatory logged justification.
- Q: How should dynamic Threat Zone lifetimes and stale entries be managed? → A: Manual deactivation only — threat zones remain active indefinitely until an operator or external feed explicitly updates or deactivates them.
- Q: How should the Tactical Project / Theater data isolation boundary be scoped? → A: Theater / Project level (with a default project when unspecified) — multiple swarms and missions share a theater project context for cross-swarm correlation while separate theaters remain isolated.
- Q: How should edge DDIL buffer replay and storage overflow be handled? → A: Live-first + async backlog replay (immediately stream live state and alerts on reconnect while draining buffered history asynchronously; on overflow, evict oldest routine navigation updates first and preserve detections and alerts).
- Q: How should incoming Target Observation events be correlated into tracked tactical entities? → A: Automated spatial-temporal + class correlation — detections of the same target class within a configurable geographic radius and time window automatically link to the same tracked tactical entity across missions within the theater (with analyst review/override).
- Q: Should the Tactical Dashboard interact with PMA through the ISC Backend API or call PMA APIs directly? → A: ISC Backend as Unified Facade — the Tactical Dashboard communicates exclusively with the ISC Backend API, which orchestrates all requests to PMA services over the internal network.
- Q: Should ISC and PMA share a single workflow orchestrator instance or run separate orchestrator instances? → A: Shared Orchestrator with Isolated Task Queues — both ISC mission workflows and PMA data pipelines share one workflow orchestrator instance using isolated task queues.
- Q: How quickly must newly ingested telemetry be compacted and queryable in the analytical archive? → A: Near-real-time micro-batch compaction (5–15s freshness or batch-size threshold) to support both live AI fleet-readiness queries and immediate post-flight AAR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - High-Throughput Push Telemetry & Persistent Mission Archive (Priority: P1)

A tactical commander or fleet operator launches a swarm mission involving dozens of autonomous drones. Instead of the command platform polling each drone one by one over transient connections, each drone continuously streams its navigation, battery, and health telemetry onto a centralized telemetry bus. All streamed telemetry is durably archived into a long-term mission store so no operational data is lost when services restart or missions conclude.

**Why this priority**: Eliminating the polling bottleneck and ephemeral in-memory telemetry loss is the foundational prerequisite for scaling beyond small prototypes and enabling every downstream analytics, safety, and intelligence capability.

**Independent Test**: Can be fully tested by launching simulated or physical drone nodes on a mission, verifying real-time telemetry reaches the command platform via push streaming without polling, restarting the command platform, and confirming historical mission telemetry remains queryable in the archive.

**Acceptance Scenarios**:

1. **Given** an active swarm of drones in flight, **When** drones emit navigation, battery, and health updates, **Then** telemetry arrives at the command platform via push streaming with low latency and without per-drone HTTP polling.
2. **Given** a completed or interrupted mission, **When** an operator inspects mission history after a system restart, **Then** the full time-series telemetry for every participating drone is preserved and retrievable from persistent storage.
3. **Given** multiple concurrent swarms operating in separate theaters or projects, **When** telemetry is ingested and stored, **Then** each swarm's operational data remains logically isolated by mission/project boundary.

---

### User Story 2 - Dynamic Battlefield Threat Gating for Mission Orders (Priority: P2)

Before a commander's SMEAC mission order is approved for execution, the automated safety critic evaluates proposed flight routes against a live, continuously updated battlefield threat knowledge store rather than a static local configuration file. Dynamic threats—such as mobile air defense envelopes, radar detection domes, electronic warfare jammer zones, and temporary restricted airspaces—can be added, updated, or deactivated in real time, and any route intersecting an active threat envelope is flagged with the specific threat details before human approval.

**Why this priority**: Static airspace definitions cannot protect autonomous swarms in contested or rapidly changing tactical environments; dynamic threat gating directly improves flight safety and mission survivability.

**Independent Test**: Can be fully tested by inserting or moving a dynamic threat zone in the tactical threat store, submitting a SMEAC mission whose trajectory intersects that zone, and verifying that the safety critic blocks or flags the order with the intersecting threat's identity and severity.

**Acceptance Scenarios**:

1. **Given** an active dynamic threat zone (e.g., mobile radar or surface-to-air threat envelope) registered in the threat knowledge store, **When** a commander submits a SMEAC mission plan whose waypoints enter that threat zone, **Then** the safety critic identifies the spatial conflict and prevents automatic approval until resolved or overridden.
2. **Given** a previously restricted threat zone is deactivated or relocated outside the planned corridor, **When** the safety critic re-evaluates the SMEAC mission plan, **Then** the route passes threat gating without requiring code changes or service restarts.

---

### User Story 3 - Edge Vision Sensor Fusion & Target Lineage (Priority: P3)

During reconnaissance flights, edge computer-vision perception detects high-priority targets (e.g., vehicles, personnel) matching the SMEAC mission profile. Each confirmed detection—along with its estimated geographic coordinates, confidence score, and a cropped visual thumbnail snapshot—is streamed to the platform, archived alongside mission telemetry, and linked to known tactical entities and the active SMEAC mission for human-in-the-loop (HITL) verification and cross-mission tracking.

**Why this priority**: Connecting edge perception outputs to persistent visual evidence and an entity knowledge graph turns isolated drone sightings into actionable, auditable target intelligence.

**Independent Test**: Can be fully tested by triggering a target detection on an edge vision node during a mission, confirming the detection metadata and visual snapshot appear in the persistent archive, and verifying the target observation is linked to the originating drone and SMEAC mission in the tactical knowledge store.

**Acceptance Scenarios**:

1. **Given** an edge drone detects a target above the configured confidence threshold, **When** the detection event is emitted, **Then** the detection metadata and cropped target snapshot are persisted and viewable for HITL commander validation.
2. **Given** multiple drones observe the same area across one or more missions, **When** detections are correlated in the knowledge store, **Then** operators can trace which drone and mission observed a target entity over time.

---

### User Story 4 - After-Action Review (AAR) Analytics & AI-Assisted SMEAC Drafting (Priority: P4)

Following or prior to missions, commanders and analysts use the tactical dashboard to run fast after-action reviews over historical fleet telemetry (such as battery depletion curves, altitude envelopes, speed profiles, and detection density) and invoke an intelligence-driven planning assistant. The assistant queries historical telemetry and live threat context to draft deconflicted SMEAC mission orders—for example, selecting drones meeting minimum battery thresholds and routing around recently detected hostile radar—before submitting the draft to the mandatory HITL approval gate.

**Why this priority**: Unifies historical lakehouse analytics and threat context into rapid commander decision support while preserving human authority over mission execution.

**Independent Test**: Can be fully tested by completing a test flight to populate archived telemetry, executing an AAR summary query from the dashboard, and prompting the planning assistant to draft a SMEAC order constrained by historical drone readiness and active threats, verifying the draft enters HITL review rather than auto-launching.

**Acceptance Scenarios**:

1. **Given** archived telemetry from completed swarm flights, **When** an analyst opens the After-Action Review view, **Then** fleet-level performance and battery health summaries render within 2 seconds (SC-004) without manual database exports.
2. **Given** a commander submits a natural-language reconnaissance request with operational constraints (e.g., avoid recent radar zones, minimum battery threshold), **When** the planning assistant generates a SMEAC draft, **Then** the draft incorporates active threat avoidance and eligible UAVs and is routed to the HITL approval screen for explicit human confirmation.

---

### Edge Cases

- When an edge drone loses radio connectivity mid-mission (jamming or out-of-range), telemetry and detection events spool to local persistent storage; upon reconnection, live position and critical alerts resume immediately while buffered history drains asynchronously. If local storage reaches capacity, oldest routine navigation updates are evicted first while target detections and safety alerts are preserved.
- When the dynamic threat knowledge store is temporarily unreachable during SMEAC validation, the safety critic falls back to deterministic local rules and baseline restricted-zone checks with explicit degraded-service status reporting (never silent mock/pass responses).
- When running both ISC and PMA services together on a single host, services communicate over an isolated shared network with non-conflicting port allocations and dedicated database instances to prevent port and schema collisions.
- When high-frequency vision detections or large swarm bursts occur, high-priority safety alerts (low battery, geofence breach, target identification) use guaranteed delivery semantics ahead of best-effort routine positional telemetry.
- Stale dynamic threat entries remain active until explicitly updated or deactivated by an operator or external feed, with commanders able to use the audited HITL override if outdated intelligence intersects a planned corridor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Edge drone nodes MUST publish navigation, battery, and health telemetry continuously to a centralized push-based messaging bus rather than relying on per-drone HTTP polling.
- **FR-002**: High-priority state alerts (such as low battery, safety boundary breach, or confirmed target identification) MUST be transmitted with guaranteed delivery semantics, while high-frequency positional telemetry MAY use best-effort low-latency delivery to avoid queue saturation.
- **FR-003**: The system MUST persistently archive incoming swarm telemetry via near-real-time micro-batch compaction (flushing within 5–15 seconds or upon batch-size threshold) into a queryable historical store organized for fast analytical retrieval and partitioned by operational theater/project and mission timeframe.
- **FR-004**: The system MUST enforce data isolation at the Tactical Project / Theater level (automatically binding to a default tactical project when not explicitly specified), allowing multiple swarms and SMEAC missions within the same theater to share telemetry, snapshots, and target lineage while strictly isolating separate theaters.
- **FR-005**: The mission safety critic MUST validate proposed SMEAC flight plans against dynamic spatial threat zones stored in a live tactical knowledge store, replacing static configuration-only geofencing. When a proposed flight plan intersects an active threat zone, the system MUST block automatic approval and route the order to the Human-in-the-Loop (HITL) approval gate with the intersecting threat details, allowing an authorized commander to either reject/reroute or explicitly override with a mandatory logged justification.
- **FR-006**: Operators MUST be able to seed, create, update, and deactivate battlefield threat entities (e.g., threat radius/polygon, altitude bounds, threat level) without restarting command services; threat entities remain active indefinitely until explicitly updated or deactivated by an operator or external intelligence feed (no automatic time-based expiration).
- **FR-007**: Edge perception nodes MUST publish target detection events (target class, confidence, bounding box, estimated coordinates) and upload cropped visual snapshots to persistent object storage linked to the originating drone and mission. The system MUST automatically correlate target observations of the same class within a configurable spatial proximity radius and time window into tracked tactical entities across missions within the same theater, while supporting analyst review and override.
- **FR-008**: The tactical dashboard MUST interact exclusively with the ISC Backend as a unified C2 facade—which orchestrates underlying queries and commands to analytics, knowledge graph, object storage, and AI services over the internal network—so operators can manage threat entities, inspect After-Action Review fleet analytics over archived mission telemetry, review uploaded target snapshots, and invoke AI-assisted SMEAC drafting.
- **FR-009**: An AI-assisted mission planner MUST be able to query historical fleet readiness and live threat context to synthesize draft SMEAC orders, and MUST route every generated order through the mandatory Human-in-the-Loop (HITL) approval gate prior to dispatch.
- **FR-010**: Integration scope MUST encompass all four C4ISR rollout phases: push telemetry streaming and persistent mission archival (Phase 1), dynamic battlefield threat gating (Phase 2), edge vision sensor fusion with target snapshots and entity lineage (Phase 3), and dashboard After-Action Review analytics plus AI-assisted SMEAC drafting (Phase 4).
- **FR-011**: Deployment packaging and service orchestration MUST support a unified co-located single-host stack where Intent-Swarm-Commander and Poor-Man's Artemis.IA services communicate over a shared local network with non-conflicting service ports and share a single workflow orchestrator instance using isolated task queues.
- **FR-012**: During disconnected, degraded, or jammed (DDIL) or air-gapped operations, edge drones MUST buffer telemetry and detections locally to persistent storage; upon reconnection, drones MUST resume live telemetry and safety alerts immediately while replaying buffered history asynchronously, and on local buffer overflow MUST evict oldest routine navigation updates first while preserving target detections and critical alerts. When external AI or dynamic threat services are unreachable, mission planning and safety validation MUST fall back to authentic deterministic local rules and baseline restricted-zone checks with explicit service-status reporting (never silent mock or dummy responses).
- **FR-013**: All production runtime modules for telemetry streaming, lakehouse archival, threat graph validation, edge perception upload, After-Action Review analytics, and AI-assisted SMEAC planning MUST interact exclusively with authentic domain models, persistent stores, and real service/hardware interfaces, containing zero mock implementations, dummy data generators, in-memory test stubs, or silent simulation fallbacks.
- **FR-014**: Automated test suites validating this integration MUST execute hermetically with strict network isolation (zero live outbound internet or third-party cloud API calls), isolating all stubs, mocks, and recorded test fixtures strictly within the test harness.

### Key Entities

- **Swarm Telemetry Event**: Timestamped state packet emitted by an edge drone containing swarm identifier, drone identifier, metric type, flight/battery/health values, and operational metadata.
- **Threat Zone**: Dynamic geospatial and altitude-bounded hazard entity (such as air-defense envelope, radar dome, EW jammer zone, or temporary flight restriction) with active status and severity level.
- **Target Observation**: Edge perception event linking a detected object class, confidence score, estimated GPS coordinates, and visual snapshot reference to an originating drone and SMEAC mission, automatically correlated by target class, spatial proximity radius, and time window into tracked tactical entities across missions within the same theater.
- **SMEAC Mission Order**: Structured tactical command plan (Situation, Mission, Execution, Administration/Logistics, Command/Signal) evaluated by the safety critic and gated by HITL commander confirmation.
- **Tactical Project / Theater**: Logical isolation boundary scoping multiple swarms and SMEAC missions within the same operational theater (including telemetry, archived datasets, threat graphs, target lineage, and analyst access permissions), with a default project automatically bound when none is specified.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Command infrastructure ingests continuous push telemetry from concurrent simulated or physical drones without HTTP polling requests to edge nodes, maintaining sub-second live status updates on the tactical dashboard.
- **SC-002**: 100% of mission telemetry emitted during connected flight is retained across service restarts and becomes queryable in the analytical archive within 15 seconds of ingestion.
- **SC-003**: Dynamic threat updates take effect in safety critic evaluations immediately upon persistence, intercepting 100% of test flight plans intersecting active threat envelopes and preventing dispatch unless explicitly overridden by a commander with a logged rationale at the HITL gate.
- **SC-004**: Analytical After-Action Review queries over multi-flight historical telemetry return fleet summaries to the operator within 2 seconds under nominal single-node load.
- **SC-005**: Every AI-drafted SMEAC order passes through safety critic evaluation and requires explicit human approval before any drone actuation occurs.
- **SC-006**: Existing Intent-Swarm-Commander local simulation and mission dispatch workflows continue to pass end-to-end verification without regression.
- **SC-007**: Production runtime modules pass static/review verification with zero mock implementations, hardcoded dummy tokens, or silent simulation fallbacks, and 100% of automated test suites pass with outbound internet access disabled.

## Assumptions

- `docs/analysis/compatibility_with_pma.md` serves as the authoritative architectural reference for capabilities, data contracts, latency budgets, and phased rollout options.
- Human-in-the-Loop (HITL) confirmation remains mandatory before any drafted or AI-assisted SMEAC mission order dispatches commands to physical or simulated drones.
- Real-time flight control loops (autopilot stabilization and onboard visual target tracking) remain strictly onboard the UAV and are never routed through external or cloud analytics components.
- Both simulated edge nodes (local Docker simulation) and physical edge nodes will use the same telemetry publishing contract so behavior remains consistent across simulation and field deployment.
- Any new standalone utility or seed scripts introduced during implementation will reside under `scripts/` per project governance.
- **LTV Node Point & Cynefin Alignment (Constitution Principles I–III & Verification Standards)**: This feature advances LTV Node Points `Verification_1_Constraint_Graph` (encoding dynamic physical/battlefield safety limits and threat envelopes into a queryable knowledge graph) and `Verification_2_Abductive_Logic_Gate` (cross-checking AI-generated SMEAC plans against the threat/constraint graph before HITL dispatch). Under Cynefin assessment, the structural telemetry and lakehouse pipeline is treated as `Complicated` (executed via phased analytical planning), while agentic SMEAC drafting is treated as `Complex` (constrained by deterministic safety critic checks, mandatory HITL approval, and iterative OODA verification).
