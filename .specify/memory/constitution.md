<!--
Sync Impact Report:
- Version change: 1.2.0 -> 1.3.0
- Modified principles: VI. Production Code Purity & Test Isolation (aligned with single-path rule)
- Added sections: VII. Single-Path Success Logic (No Conditional Library Imports or Fallbacks); Single-Path Verification standard
- Removed sections: None
- Templates requiring updates: ✅ None (.specify/templates/plan-template.md, spec-template.md, tasks-template.md already align dynamically)
- Follow-up TODOs: None
-->
# Intent-Swarm-Commander Constitution

## Core Principles

### I. Cone of Uncertainty Framework (LTV)
Every design and specification must be anchored in the Long Term Vision (LTV) and the Cone of Uncertainty Framework. Before initiating new architectures or significant changes, the "TO-BE" state must be clearly defined. The Inverted Cone (working backward from the End State) must be used to eliminate non-viable paths, ensuring all work converges toward predefined Node Points.

### II. Cynefin Domain Assessment
Before planning architecture or implementation, the environment must be classified into its Cynefin Domain (Clear, Complicated, Complex, Chaotic). Backward planning and the Inverted Cone apply strictly to the "Complicated" domain. "Complex" challenges require a Probe-Sense-Respond approach, while "Chaotic" situations necessitate Act-Sense-Respond micro-hypotheses.

### III. Execution via OODA Loops
Short-term execution between major Node Points must utilize high-velocity OODA (Observe, Orient, Decide, Act) loops. Avoid massive, irreversible architectural decisions; instead, break tasks down into testable micro-hypotheses aligned with the next immediate Node Point on the LTV Cone.

### IV. Guard Against False Cones
All technological choices and trends must be scrutinized for "hype" or false possibilities. Trends that do not align with the target TO-BE goal must be rigorously rejected and logged as false cones to preserve the integrity of the Inverted Cone pathway.

### V. Script Organization and Modularity
All standalone or utility scripts developed to support operations must be placed in the `scripts/` directory at the project root. The root directory itself must remain clean of one-off executables.

### VI. Production Code Purity & Test Isolation
- **No Mocks in Production:** Production source code (`src/`) MUST NOT contain mock implementations, stubs, test doubles, simulation fallbacks, or dummy data paths. Every production component, facade, operation, and API endpoint MUST interact with authentic domain models, databases, and real system/hardware interfaces. Testing stubs, mock classes, and simulated fixtures MUST reside strictly within test suites (e.g., `tests/`, `pytest` fixtures, or dedicated test harnesses) and MUST NEVER leak into runtime production packages.
- **Strict Network Isolation in Tests (PMA Standard):** Automated tests MUST NOT execute live outbound network calls or depend on unmanaged external network endpoints. External HTTP, cloud, or third-party network interactions in automated tests MUST be stubbed, mocked, or replayed from deterministic test fixtures (e.g., `pytest` fixtures, `respx`, `responses`, or localized container mocks).

**Rationale:** In a tactical drone swarm C2 / C4ISR system, simulated fallbacks, in-memory stubs, or mock shortcuts left in production code introduce catastrophic reliability risks, bypass critical safety gates, and conceal structural defects. Restricting mocks exclusively to pytest fixtures keeps production code pure, while hermetic test-time network mocking ensures repeatable, fast, and deterministic test runs without external network flakiness.

### VII. Single-Path Success Logic (No Conditional Library Imports or Fallbacks)
- **Unconditional Dependency Imports:** Production modules (`src/`) MUST import all required third-party and internal libraries unconditionally at the module top level. Guarding imports with `try: ... except ImportError:` or toggling behavior via `*_AVAILABLE` flags (such as `SHAPELY_AVAILABLE`, `DUCKDB_AVAILABLE`, `PYARROW_AVAILABLE`, `AIOMQTT_AVAILABLE`, `NEO4J_AVAILABLE`, `PAHO_AVAILABLE`, `MAVSDK_AVAILABLE`, `OPENCV_AVAILABLE`, `YOLO_AVAILABLE`) is strictly forbidden.
- **Success Case Only — Zero Fallback Branches:** Production code MUST implement only the primary, canonical execution path. Writing secondary fallback implementations for when a library, configuration, or service is absent or fails (such as manual ray-casting when a geometry library is missing, secondary database/serialization engines, regex/template synthesis when an AI model fails, static file fallbacks when a graph store is unreachable, or hardcoded fallback credentials/hosts) is prohibited. When a dependency or service is unavailable, the component MUST raise an explicit error immediately rather than branching to fallback logic.

**Rationale:** Dual-path conditional logic (`if LIB_AVAILABLE ... else ...`) and fallback branches double maintenance surface area, hide missing dependencies in deployment environments, create divergent behavior between environments, and mask operational failures. Enforcing a single canonical code path guarantees deterministic behavior and fail-fast visibility.

## Verification & Architecture Standards

- **Database Consistency:** Interaction with the LTV Cone of Uncertainty (`ltv_database.db`) must go exclusively through designated manager scripts in `skills/`. No manual/arbitrary queries that corrupt the LTV schema.
- **Node Alignment:** Any new capability must explicitly document which existing Node Point it satisfies or propose a new Node Point if a critical convergence gateway is missing.
- **Architecture Review:** Always use the `.agents/agents/uservice-arch-reviewer` agent to review the implementation and ensure it strictly follows the architectural design.
- **Production Purity Verification:** Code reviews and CI quality gates MUST inspect production modules under `src/` to ensure zero mock fallbacks, hardcoded dummy tokens, or simulated test pathways are merged.
- **Single-Path Verification:** Code reviews and CI checks MUST verify that `src/` contains zero `try/except ImportError` guards, zero `*_AVAILABLE` feature-detection flags, and zero secondary fallback algorithms.
- **Hermetic Test Verification:** Automated test execution MUST pass without requiring outbound internet access or external third-party network services.

## Governance

This Constitution acts as the primary compass for all AI agents operating within Intent-Swarm-Commander. Any divergence from LTV pathways, skipping of Domain Assessments, or introducing mock pathways into production code is considered a violation of project governance.
All pull requests, implementations, and design specifications must be verified against these principles prior to execution.
Amendments require clear documentation, rationalized SemVer version bumps (MAJOR for breaking governance redefinitions, MINOR for new principles/sections, PATCH for wording clarifications), and propagation to dependent templates.

**Version**: 1.3.0 | **Ratified**: 2026-07-24 | **Last Amended**: 2026-11-15
