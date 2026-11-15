# Feature Specification: Poor Man's Defense Lakehouse Naming Alignment

**Feature Branch**: `007-pmdl-naming-alignment`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "I have renamed and refactored the naming of poor mans artemis $HOME/Projects/Poor-Man-s-Artemis.IA/ Use /speckit-specify to check and adapt if needed. Also refactor naming in this project to reflect the new name. Update docs and integration docs we did before."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Partner Platform Naming Alignment Across Documentation (Priority: P1)

Engineers, architects, and stakeholders reading the project documentation hub, system architecture overview, deployment guide, and integration analysis see consistent references to **Poor Man's Defense Lakehouse (PMDL)** instead of the retired **Poor-Man's Artemis.IA (PMA)** name.

**Why this priority**: Accurate partner naming in architectural and integration documentation is critical for onboarding, cross-repository coordination, and preventing confusion between the legacy name and the current platform identity.

**Independent Test**: Can be fully tested by reviewing the documentation hub, system architecture summary, deployment manual, and integration analysis document to confirm every partner brand reference uses "Poor Man's Defense Lakehouse" and "PMDL" and all cross-document links resolve cleanly.

**Acceptance Scenarios**:

1. **Given** a reader opens the documentation hub or system architecture document, **When** they follow the link to the lakehouse integration analysis, **Then** the target document exists at the updated path, loads cleanly, and consistently uses "Poor Man's Defense Lakehouse" and "PMDL".
2. **Given** a stakeholder reviews the printable architecture manual configuration and deployment documentation, **When** they inspect chapter titles, integration notes, and comparison tables, **Then** retired partner product names do not appear as the active platform name.

---

### User Story 2 - Operational Naming Alignment Across Runtime Configuration and Verification (Priority: P2)

Operators and developers configuring containers, environment templates, verification utilities, and automated test suites encounter consistent `PMDL` / `pmdl` identifiers matching the renamed partner platform.

**Why this priority**: Consistent naming across configuration templates, service definitions, and verification scripts prevents configuration mismatches and aligns runtime terminology with documentation.

**Independent Test**: Can be fully tested by inspecting environment templates, container definitions, verification scripts, and running the automated test and stack-verification suites to confirm all checks pass under the updated naming.

**Acceptance Scenarios**:

1. **Given** an operator sets up a deployment from the environment template and container compose configuration, **When** they review task queue names, service container names, and section headings, **Then** they see `PMDL` / `pmdl` identifiers instead of legacy `PMA` / `pma` labels.
2. **Given** a developer runs the renamed stack verification utility and integration test suite, **When** execution completes, **Then** all checks pass without broken imports, missing files, or stale references.

---

### User Story 3 - Governance & Historical Traceability Preservation (Priority: P3)

Maintainers reviewing project governance rules and historical feature records see updated governance terminology where active standards apply, while earlier completed specifications remain intact as historical audit records.

**Why this priority**: Keeping active governance standards aligned while preserving historical feature records maintains auditability without breaking historical references.

**Independent Test**: Can be fully tested by inspecting project governance documents for current partner terminology and confirming earlier specification records remain accessible.

**Acceptance Scenarios**:

1. **Given** a contributor reads the active project constitution, **When** they review the test isolation standard, **Then** it references the PMDL standard rather than the retired PMA acronym.
2. **Given** an auditor inspects historical specifications, **When** they browse earlier specification folders, **Then** historical specifications remain preserved while active specifications reflect the current name.

---

### Edge Cases

- What happens when external partner infrastructure still exposes internal container hostnames or temporary paths (`artemis-*` or `/tmp/artemis/buffer`) in its own deployment manifest? Documentation mapping directly to external partner container hostnames must accurately reflect what the partner repository currently defines rather than inventing non-existent endpoints.
- How are binary documentation assets handled? Regenerating or noting any pre-rendered manual assets (such as the architecture PDF) avoids broken build references when source markdown files are renamed.
- What happens to automated references pointing to renamed test or script files? Every internal reference, command example, and CI/script path in active files must be updated alongside the rename so no dangling file paths remain.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Active documentation files MUST replace retired partner platform references ("Poor-Man's Artemis.IA", "PMA") with **Poor Man's Defense Lakehouse** and **PMDL**.
- **FR-002**: The integration analysis document MUST be renamed to reflect `pmdl` naming, and all active links referencing it across the documentation hub, system architecture guide, and PDF generation manifest MUST be updated to point to the renamed file.
- **FR-003**: Runtime configuration templates, container definitions, and task queue identifiers owned by this project MUST use `PMDL` / `pmdl` naming consistently.
- **FR-004**: Stack verification utilities and integration/E2E test files named after `pma` MUST be renamed and updated internally to `pmdl`, and all automated verification checks MUST pass after refactoring.
- **FR-005**: Active project governance documents MUST reflect the `PMDL` standard while preserving historical specification directories as immutable audit records.
- **FR-006**: References to the partner repository's own internal container hostnames or buffer directories (`artemis-mosquitto`, `artemis-memgraph`, `artemis-minio`, `/tmp/artemis/buffer`) MUST remain accurate to the partner repository's actual deployment manifest until changed upstream.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of active documentation pages, configuration templates, governance standards, and verification utilities use "Poor Man's Defense Lakehouse" and "PMDL" with zero stale "Poor-Man's Artemis.IA" or `PMA` references outside historical specification archives and upstream-owned container names.
- **SC-002**: 100% of internal documentation links and script references resolve to valid existing files.
- **SC-003**: 100% of automated test cases and stack verification checks pass after all renames and refactoring edits are applied.

## Assumptions

- The partner repository located on disk at `$HOME/Projects/Poor-Man-s-Artemis.IA/` has been renamed conceptually to **Poor Man's Defense Lakehouse**, while its repository folder and internal Docker service names (`artemis-*`) remain unchanged upstream at this time.
- Historical feature folders (`005-pma-integration`, `006-remove-fallback-logic`) are retained as completed historical records rather than retroactively renamed.
- Any generated binary PDF manual (`docs/Intent-Swarm-Commander-Architecture.pdf`) can be rebuilt if PDF tooling is available, or its source configuration (`scripts/generate_architecture_pdf.js`) is kept synchronized.
