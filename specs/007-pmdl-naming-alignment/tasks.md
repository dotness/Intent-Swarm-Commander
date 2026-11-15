---
description: "Task list for feature implementation: Poor Man's Defense Lakehouse Naming Alignment"
---

# Tasks: Poor Man's Defense Lakehouse Naming Alignment

**Input**: Design documents from `/specs/007-pmdl-naming-alignment/`  
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [quickstart.md](./quickstart.md)

**Organization**: Tasks are grouped by user story (`US1`–`US3`) in priority order to enable independent implementation and verification.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Include exact repository file paths in every task description

---

## Phase 1: Setup & Audit

**Purpose**: Inspect upstream repository naming and inventory all stale references in this workspace.

- [X] T001 Audit upstream repository `$HOME/Projects/Poor-Man-s-Artemis.IA/` and inventory all active `Poor-Man's Artemis.IA` / `PMA` occurrences across `README.md`, `docs/`, `scripts/`, `src/`, `tests/`, `docker-compose.yml`, `.env.example`, and `.specify/memory/`

---

## Phase 2: User Story 1 - Partner Platform Naming Alignment Across Documentation (Priority: P1) 🎯 MVP

**Goal**: Align all active documentation, integration analysis guides, and PDF build configuration with **Poor Man's Defense Lakehouse (PMDL)**.

**Independent Test**: Review `docs/README.md`, `docs/system_architecture.md`, `docs/deployment.md`, `docs/analysis/compatibility_with_pmdl.md`, and `scripts/generate_architecture_pdf.js` to confirm consistent `Poor Man's Defense Lakehouse` / `PMDL` naming and valid cross-links.

- [X] T002 [US1] Rename `docs/analysis/compatibility_with_pma.md` to `docs/analysis/compatibility_with_pmdl.md` and update its document ID (`DOC-ANALYSIS-ISC-PMDL-001`) and partner branding to Poor Man's Defense Lakehouse (PMDL) while preserving upstream `artemis-*` container hostnames
- [X] T003 [P] [US1] Update partner name and link to `docs/analysis/compatibility_with_pmdl.md` in `docs/README.md`
- [X] T004 [P] [US1] Update partner name and link to `docs/analysis/compatibility_with_pmdl.md` in `docs/system_architecture.md` and `docs/deployment.md`
- [X] T005 [P] [US1] Update Chapter 6 title, source path, and chapter ID (`chap-pmdl-analysis`) in `scripts/generate_architecture_pdf.js`

---

## Phase 3: User Story 2 - Operational Naming Alignment Across Runtime Configuration and Verification (Priority: P2)

**Goal**: Align Docker Compose containers, environment templates, verification utilities, and test suites with `PMDL` / `pmdl` identifiers.

**Independent Test**: Run `.venv/bin/python scripts/verify_pmdl_stack.py --rows 500` and `COMMANDER_PASSPHRASE=test-commander-passphrase GEMINI_API_KEY=test-gemini-key .venv/bin/pytest -v` and confirm all checks pass.

- [X] T006 [P] [US2] Update `PMA_TASK_QUEUE`, `pma-ingestion-queue`, and `pma_mosquitto` / `pma_minio` / `pma_memgraph` to `PMDL` / `pmdl` in `docker-compose.yml` and `.env.example`
- [X] T007 [P] [US2] Update `PMA` comments/docstrings to `PMDL` in `src/uservice/security/proxy.py` and `tests/conftest.py`
- [X] T008 [P] [US2] Rename `scripts/verify_pma_stack.py` to `scripts/verify_pmdl_stack.py`, `tests/integration/test_pma_pipeline.py` to `tests/integration/test_pmdl_pipeline.py`, and `tests/e2e/pma_c2.spec.js` to `tests/e2e/pmdl_c2.spec.js` with aligned internal `PMDL` identifiers

---

## Phase 4: User Story 3 - Governance & Historical Traceability Preservation (Priority: P3)

**Goal**: Align active project governance while keeping historical `005-pma-integration` and `006-remove-fallback-logic` specs intact.

**Independent Test**: Inspect `.specify/memory/constitution.md` (`PMDL Standard`) and verify `specs/005-pma-integration/` and `specs/006-remove-fallback-logic/` remain intact.

- [X] T009 [P] [US3] Update `PMA Standard` to `PMDL Standard` in `.specify/memory/constitution.md` while keeping historical `specs/005-pma-integration/` and `specs/006-remove-fallback-logic/` archives untouched

---

## Phase 5: Polish & Validation

**Purpose**: Verify zero stale active references and full suite pass rate.

- [X] T010 Run naming grep audit across active files, execute `.venv/bin/python scripts/verify_pmdl_stack.py --rows 500`, and run full `.venv/bin/pytest -v` suite per `specs/007-pmdl-naming-alignment/quickstart.md`

---

## Dependencies & Execution Order

- **Phase 1 (`T001`)**: Audit completes first.
- **Phase 2 (`T002`–`T005`, US1)**: `T002` renames the integration doc; `T003`–`T005` update referring docs/scripts in parallel.
- **Phase 3 (`T006`–`T008`, US2)**: All runtime config, code comment, script, and test renames execute in parallel.
- **Phase 4 (`T009`, US3)**: Constitution update executes in parallel with US2.
- **Phase 5 (`T010`)**: Runs final grep audit, stack benchmark, and full test suite after all renames complete.
