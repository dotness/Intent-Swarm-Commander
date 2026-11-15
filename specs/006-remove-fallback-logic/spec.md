# Feature Specification: Enforce Single-Path Success Logic & Remove Fallbacks

**Feature Branch**: `006-remove-fallback-logic`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "include in constitution a rule that we are not to implement logic as in attached screenshot. What is presented, means in the logic that we have one logic where a library is available and another when its not. I dont want that. I only want the success case, no fallback logic. Update constitution and then do /speckit-specify to refactor codebase to be compliant with new rule."

## Clarifications

### Session 2026-11-15

- Q: Which categories of fallback logic must be removed from production code? → A: Remove both library-availability fallbacks (`try/except ImportError`, `*_AVAILABLE` flags, and alternate engines such as `_point_in_ring`, `sqlite_olap`, `PAR1ISCC`, and `PIL`) and runtime service/config fallbacks (static `restricted_zones.json` fallback, LLM regex/template fallbacks, multi-host Temporal retry loop, and `dev_passphrase`), while retaining `EdgeSpool` DDIL SQLite buffering as an explicit tactical domain capability.
- Q: How should unconditional third-party imports be satisfied in the local development and test environment (`.venv`)? → A: Install every required package (including full `mavsdk`, `opencv-python-headless`, `ultralytics`, `shapely`, `duckdb`, `pyarrow`, `aiomqtt`, `neo4j`, `paho-mqtt`, and `aiosqlite` wheels) into `.venv` and declare them in project dependency manifests with zero module-import shims in `tests/conftest.py`.
- Q: How should upstream service failures and legacy degraded/fallback schema fields be handled once runtime fallbacks are removed? → A: Let upstream exceptions surface directly (HTTP 500 Internal Server Error at the API boundary) without degraded-mode catch wrappers, and remove all fallback/degraded fields and UI banners (`degraded_mode`, `degraded_reason`, `fallback_static_zones`, and `threat_check_mode` fallback states) from API schemas, ORM models, and the dashboard.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fail-Fast Dependency Enforcement Across Core & Edge Modules (Priority: P1)

Platform engineers and operators running the command backend and edge companion runtimes require every production module to load its mandatory dependencies directly and execute a single canonical code path, failing immediately at startup or invocation when a required dependency is absent rather than silently switching to an alternate code path.

**Why this priority**: Conditional import branches and dual-path availability flags conceal broken deployments and cause inconsistent behavior between environments. Eliminating conditional dependency guards establishes fail-fast correctness as the baseline invariant.

**Independent Test**: Can be fully tested by auditing all production modules for conditional import guards and availability flags and verifying that removing or blocking a required dependency results in an immediate failure rather than secondary-branch execution.

**Acceptance Scenarios**:

1. **Given** a production environment with all required dependencies installed, **When** any backend or edge service starts up, **Then** every module initializes its mandatory libraries directly without checking feature-availability flags.
2. **Given** an environment where a required dependency is missing, **When** the dependent production module is imported or invoked, **Then** the process fails fast with a direct dependency error instead of activating an alternate implementation.

---

### User Story 2 - Canonical Single-Engine Execution for Analytics, Archival, and Spatial Safety (Priority: P2)

Tactical analysts and mission safety critics require mission archival, after-action analytics, and spatial geofence/threat evaluation to run exclusively through the primary columnar storage format, primary analytical engine, and primary spatial knowledge/geometry engines without secondary storage containers, alternate query engines, or static-file threat fallbacks.

**Why this priority**: Dual implementations in data storage, querying, and threat evaluation introduce schema drift and split behavior between test and production runs, undermining confidence in analytical accuracy and safety checks.

**Independent Test**: Can be fully tested by running spatial safety checks, telemetry archival, and after-action analytical queries across unit, contract, and integration suites and confirming zero fallback engines or static-file threat branches execute.

**Acceptance Scenarios**:

1. **Given** incoming mission telemetry and active mission orders, **When** telemetry is archived and queried for after-action review, **Then** only the primary columnar archival format and primary analytical engine process the data.
2. **Given** proposed swarm flight paths evaluated by the safety critic or threat gateway, **When** spatial intersection or dynamic threat checks execute, **Then** only the primary geometry and knowledge-graph evaluation path executes, and any service outage lets the upstream exception surface directly (resulting in HTTP 500 at the API boundary) rather than catching to substitute static zone files or degraded-mode flags.

---

### User Story 3 - Explicit Failure Propagation for Mission Planning, Orchestration, and Security (Priority: P3)

Commanders and security administrators require mission order translation, AI-assisted drafting, workflow scheduling, and security credential endpoints to execute exclusively along the primary configured pathway and return explicit errors when an upstream service or configuration setting is missing, removing regex/template fallbacks, multi-host retry loops, and default credentials.

**Why this priority**: Silent regex mission synthesis, template drafts, or default passphrases mask upstream misconfigurations or security omissions and allow unverified defaults to stand in for authentic service outputs.

**Independent Test**: Can be fully tested by exercising order submission, AI draft generation, workflow dispatch, and token issuance with missing upstream connectivity or configuration and verifying immediate explicit errors are raised instead of fallback payloads.

**Acceptance Scenarios**:

1. **Given** an order translation or AI drafting request when the AI service is unconfigured or unavailable, **When** the request is processed, **Then** the system lets the error propagate cleanly without catch-and-fallback wrappers (resulting in HTTP 500 at the API boundary) instead of generating regex-parsed commands, template drafts, or degraded-mode responses.
2. **Given** a workflow dispatch or token credential request when the target endpoint or required passphrase configuration is absent, **When** the operation executes, **Then** the system lets the configuration or connection failure propagate directly (resulting in HTTP 500 on route handlers or immediate exception propagation) without iterating backup host addresses or falling back to default development credentials.

---

### Edge Cases

- What happens when an optional runtime dependency is absent from an environment during startup? The service fails fast on startup import instead of entering a partial or secondary execution mode.
- How does the system handle an unreachable threat knowledge store, analytical store, AI provider, or workflow orchestrator during a live request? Upstream exceptions surface directly without degraded-mode catch wrappers (producing HTTP 500 Internal Server Error responses at API boundaries) without substituting static files, synthetic templates, secondary storage engines, or degraded status payloads.
- What happens when required security secrets or endpoint settings are unset? Credential validation and service client initialization reject execution immediately rather than falling back to hardcoded default values.
- How do hermetic automated tests run without external network access once production fallback paths are removed? Automated tests install every required runtime wheel directly into the test environment (with zero module-import shims) and inject controlled boundary test doubles solely within the test suite.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Production source modules MUST load all required runtime dependencies unconditionally at module initialization without conditional availability flags or import-error branching.
- **FR-002**: Spatial containment and geofence evaluations MUST execute solely through the primary geometric evaluation library; secondary manual polygon-intersection algorithms MUST be removed.
- **FR-003**: Telemetry archival and after-action analytical queries MUST execute solely through the primary columnar storage format and primary analytical query engine; custom binary fallback containers and secondary relational query fallbacks MUST be removed.
- **FR-004**: Edge camera capture, target detection, image cropping, flight control, and telemetry publishing MUST execute solely against their primary library interfaces without conditional availability guards or secondary image-encoding fallbacks, while retaining local `EdgeSpool` persistent buffering as an explicit DDIL tactical capability for radio link loss.
- **FR-005**: Dynamic threat listing and route threat evaluation MUST query solely the primary tactical knowledge store and allow upstream errors to propagate directly (HTTP 500 at the API boundary); static baseline threat file fallbacks and fallback/degraded fields (`degraded_mode`, `degraded_reason`, `fallback_static_zones`, and `threat_check_mode` fallback states) MUST be removed from schemas, persistence models, and the dashboard UI.
- **FR-006**: Mission order parsing, AI-assisted order drafting, and command/draft persistence MUST execute solely through the primary AI synthesis service without regex coordinate extraction fallbacks, deterministic draft template fallbacks, or degraded-mode catch wrappers, propagating missing configuration or AI service exceptions directly (HTTP 500 at the API boundary).
- **FR-007**: Workflow dispatch and security credential issuance MUST connect solely to the explicitly configured service endpoint and require configured security credentials; multi-host fallback connection loops, hardcoded fallback passphrases, and silent workflow-start exception suppression MUST be removed so errors propagate directly.
- **FR-008**: All required runtime packages (including spatial, analytical, messaging, database, computer vision, and autopilot packages) MUST be declared in project dependency manifests and installed in the project test environment with zero module-import shims, and automated unit, contract, and integration suites MUST verify single-path production execution and explicit failure behavior.

### Key Entities

- **Canonical Execution Path**: The single mandatory runtime workflow for a given system capability, directly backed by its primary library or external service without secondary alternatives.
- **Explicit Failure Boundary**: The strict boundary where missing dependencies, unconfigured credentials, or unreachable upstream services immediately raise errors to callers rather than activating fallback code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of production source files contain zero conditional dependency-availability flags and zero import-error fallback branches.
- **SC-002**: 100% of spatial safety, telemetry archival, analytical query, edge perception, and mission-planning capabilities execute along a single code path with zero secondary algorithm or static-file fallback logic.
- **SC-003**: 100% of unavailable-dependency, unconfigured-secret, and unreachable-service test cases surface explicit error failures rather than returning synthesized or fallback data.
- **SC-004**: 100% of automated test suites pass against the single-path production codebase without regressions in core mission dispatch, telemetry ingestion, analytical reporting, and safety gating workflows.

## Assumptions

- Target production and test environments have all mandatory packages installed directly as real wheels (including edge vision and autopilot packages) rather than relying on reduced dependency subsets or test-time module-import shims.
- Dashboard UI views remove legacy fallback zone layers and degraded-mode banners (`degraded_mode`, `fallback_static_zones`, `threat_check_mode` warnings) since all operations execute strictly along the single canonical path or surface an explicit failure.
- Runtime service/protocol test doubles inside the test suite (such as in-memory MQTT/S3/Memgraph/DB/AI client fixtures at boundary interfaces, with zero missing-module shims) remain compliant with Constitution Principles VI and VII while exercising authentic single-path production modules.
