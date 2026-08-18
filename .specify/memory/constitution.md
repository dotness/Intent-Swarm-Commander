<!--
Sync Impact Report:
- Version change: 1.0.0 -> 1.1.0
- Modified principles: None
- Added sections: Added rule to Verification & Architecture Standards
- Removed sections: None
- Templates requiring updates: ✅ None
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

## Verification & Architecture Standards

- **Database Consistency:** Interaction with the LTV Cone of Uncertainty (`ltv_database.db`) must go exclusively through designated manager scripts in `skills/`. No manual/arbitrary queries that corrupt the LTV schema.
- **Node Alignment:** Any new capability must explicitly document which existing Node Point it satisfies or propose a new Node Point if a critical convergence gateway is missing.
- **Architecture Review:** Always use the `.agents/agents/uservice-arch-reviewer` agent to review the implementation and ensure it strictly follows the architectural design.

## Governance

This Constitution acts as the primary compass for all AI agents operating within Intent-Swarm-Commander. Any divergence from LTV pathways or skipping of Domain Assessments is considered a violation of project governance.
All pull requests, implementations, and design specifications must be verified against these principles prior to execution.

**Version**: 1.1.0 | **Ratified**: 2026-07-24 | **Last Amended**: 2026-07-25
