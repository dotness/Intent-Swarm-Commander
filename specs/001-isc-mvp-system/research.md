# Research: Intent Swarm Commander — MVP System

**Feature**: 001-isc-mvp-system | **Date**: 2026-07-24

## R1: MCP Transport Protocol for Remote Servers

**Decision**: MCP JSON-RPC 2.0 over Streamable HTTP (SSE for server-to-client, HTTP POST for client-to-server)

**Rationale**: The official MCP specification (2025-03-26 revision onward) standardizes on JSON-RPC 2.0 as the wire protocol. For remote (non-stdio) servers — which is our use case with dynamically provisioned swarm containers — the spec mandates Streamable HTTP transport. This is the only protocol that supports dynamic tool registration and discovery, which we need for newly provisioned swarm instances to register their tools with the gateway.

**Alternatives Considered**:
- gRPC: Higher performance but not MCP-compliant; would require custom bridging.
- Plain REST: Simpler but lacks the bidirectional streaming needed for real-time telemetry and HITL elicitation.
- WebSockets: Good for persistent connections but not the MCP standard transport.

## R2: Dynamic Container Provisioning Strategy

**Decision**: Docker SDK for Python executed via pydantic-ai Executor Agent within a Temporal workflow.

**Rationale**: The `uservice-template` mandates that state-mutating actions (like provisioning a swarm) be handled as durable Temporal workflows. The provisioning process is orchestrated by a 3-agent pydantic-ai pipeline (Planner → Guardian Critic → Executor). The Executor agent uses the Docker SDK as an exposed tool to programmatically create the dedicated swarm container, ensuring full visibility, reasoning, and retryability.

**Alternatives Considered**:
- Kubernetes: Production-grade but excessive for MVP. Would require a K8s cluster, service mesh, and operator patterns. Deferred to post-MVP.
- Docker Compose scale: The `--scale` flag doesn't support per-instance configuration (unique ports, swarm IDs). Custom orchestration needed.
- Direct API calls: Synchronous provisioning without Temporal risks blocking the API and lacks durable retries.

## R3: Authentication for MVP — Mocked vs. Real IdP

**Decision**: Self-signed JWT tokens issued by the gateway itself for MVP. No external IdP dependency.

**Rationale**: The spec allows mocked IdP (Assumption: "An external identity provider is available or can be mocked for MVP purposes"). For MVP, the gateway generates and validates its own JWTs with configurable scopes and expiry. This validates the full auth flow (token validation, scope checking, JIT expiry) without requiring an Okta/Entra deployment. The token format follows OAuth 2.1 JWT structure so the upgrade path is a configuration change.

**Alternatives Considered**:
- Keycloak: Full-featured IdP but heavy operational overhead for MVP.
- Auth0 free tier: External dependency, network requirement, and potential latency.
- No auth: Would skip FR-003/FR-004 entirely, leaving a critical gap.

## R4: Safety Verification — Minimal Constraint Solver

**Decision**: Rule-based constraint engine using a declarative JSON/YAML rule set with Python evaluation. No external solver dependency for MVP.

**Rationale**: The spec explicitly states the Safety Verification Layer operates with a "minimal, manually defined rule set" (Assumption). A full Z3/SMT solver is the LTV target (NSVIF_CSP_Solver_Deployment node) but is out of MVP scope. A simple Python-based rule engine that evaluates constraints like `altitude < max_altitude`, `target_area not in restricted_zones`, and `drone_count <= available_drones` satisfies FR-007 and SC-004 for the MVP rule set. The constraint format is designed to be forward-compatible with Z3 constraint expressions.

**Alternatives Considered**:
- Z3 SMT Solver: The LTV target, but requires significant integration effort. Deferred to Neuro_Symbolic_Verification node.
- OPA (Open Policy Agent): Good for policy-as-code but overkill for simple numeric/geographic constraints in MVP.
- Hardcoded rules: Would work but not extensible. JSON/YAML rule files provide the right balance.

## R5: Frontend Architecture

**Decision**: Vanilla HTML/CSS/JavaScript with ES modules. No framework.

**Rationale**: Per project web development guidelines, the system uses vanilla JS with rich modern aesthetics (glassmorphism, micro-animations, dark mode). The dashboard is a single-page application with modular JS files for each panel (SMEAC, Tactical Map, HITL Modal, etc.). Leaflet.js is used for the tactical map (open-source, military-grade mapping). WebSocket connection to the gateway for real-time updates.

**Alternatives Considered**:
- React/Vue/Next.js: Would add build tooling complexity. The dashboard has a fixed panel layout, not a dynamic SPA requiring virtual DOM.
- Tailwind CSS: Not used unless explicitly requested (per project guidelines).

## R6: HITL Timeout Fallback — Swarm Controller Autonomous Decision

**Decision**: On HITL timeout, the Swarm Controller evaluates the pending action against its pre-programmed safety heuristics and either executes (if safe) or rejects (if unsafe). All timeout-triggered autonomous decisions are flagged in the audit trail.

**Rationale**: The user explicitly specified that on timeout, "the Swarm Controller makes the decision." This means the controller needs a decision matrix that classifies actions by risk level. For MVP, the heuristic is conservative: only actions that pass all safety constraints AND are below a configurable risk threshold proceed autonomously. Mass abort always auto-approves (safe by nature). ROE changes always auto-reject (too consequential for autonomous decision).

**Alternatives Considered**:
- Always reject on timeout: Simpler but the user explicitly rejected this approach.
- Always approve on timeout: Unsafe, violates fail-safe principles.
- Escalate to secondary commander: Multi-tier approval is post-MVP.

## R7: Audit Trail Storage

**Decision**: SQLite with append-only table, JSON-structured event payloads. Immutability enforced at application level (no UPDATE/DELETE on audit table).

**Rationale**: SQLite is sufficient for MVP audit volumes. The audit table uses an append-only pattern with JSON payloads for flexible event schemas. Application-level enforcement prevents deletion. Upgrade path to PostgreSQL with write-ahead logging is straightforward.

**Alternatives Considered**:
- File-based JSON logs: Simple but lack query capability for post-incident review.
- PostgreSQL: Production-grade but adds container/dependency complexity for MVP.
- Event sourcing with Kafka: Overkill for MVP; deferred to production architecture.

## R8: Cynefin Domain Classification

**Decision**: This problem is classified as **Complicated** (Cynefin Domain).

**Rationale**: The system architecture follows known patterns (MCP protocol, OAuth 2.1, container orchestration). The unknowns are analyzable by experts (constraint solver design, dynamic routing). The cause-effect relationships are discoverable through analysis. This is not Complex (no emergent behavior to probe) or Chaotic (no immediate crisis). The Inverted Cone methodology from the LTV Framework is therefore appropriate.

**Alternatives Considered**:
- Complex: Would require Probe-Sense-Respond. But the architecture is deterministic and well-specified.
- Clear: Would imply trivial implementation. The multi-service orchestration with dynamic provisioning is non-trivial.

## R9: State-Mutating Operations Orchestration

**Decision**: All state-mutating operations (Provisioning swarms, processing SMEAC orders) run as Temporal Workflows.

**Rationale**: Following the `uservice-template` architecture, long-running or failure-prone operations require durable execution. Temporal guarantees that if the uService crashes during swarm provisioning or SMEAC parsing, the workflow resumes exactly where it left off. It also provides built-in dependency management (e.g., ensuring a swarm isn't updated while being created).

**Alternatives Considered**:
- Celery / Redis Queue: Lacks advanced workflow orchestration and state durability.
- Synchronous API: Fragile for operations like container spinning or LLM-based intent translation.

## R10: Intelligent Execution via pydantic-ai

**Decision**: Use the pydantic-ai 3-Agent Pipeline (Planner → Guardian Critic → Executor) for complex domain operations.

**Rationale**: `uservice-template` relies on this pattern for intelligent, safe execution. For example, when parsing a SMEAC order, the Planner agent proposes the command breakdown, the Guardian Critic reviews it for missing/unsafe parameters (Reasoning by Inversion), and the Executor agent executes the tool calls to persist the commands. This enforces a strict separation of concerns within the LLM reasoning process. pydantic-ai provides type-safe, Pydantic-native agent definitions that integrate naturally with the existing FastAPI/Pydantic stack.

**Alternatives Considered**:
- Single-agent execution: Faster but lacks the adversarial safety check of the Guardian Critic.
- Traditional code logic: Parsing unstructured SMEAC text requires LLM reasoning; hardcoded logic is insufficient.
