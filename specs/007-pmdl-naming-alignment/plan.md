# Implementation Plan: Poor Man's Defense Lakehouse Naming Alignment

**Branch**: `007-pmdl-naming-alignment` | **Date**: 2026-11-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-pmdl-naming-alignment/spec.md`

## Summary

Align all active documentation, integration analysis guides, Docker/environment configuration, governance standards, stack verification scripts, and test suites in `Intent-Swarm-Commander` with the partner repository's new identity: **Poor Man's Defense Lakehouse (`PMDL`)** (formerly `Poor-Man's Artemis.IA` / `PMA`), while keeping upstream-owned Docker container hostnames (`artemis-mosquitto`, `artemis-memgraph`, `artemis-minio`) and `/tmp/artemis/buffer` accurate to the partner repository's current deployment manifest and preserving historical specification archives (`005-pma-integration`, `006-remove-fallback-logic`).

## Technical Context

**Language/Version**: Python 3.14.4, Markdown, JavaScript (Playwright / PDF generator), YAML (`docker-compose.yml`)  
**Primary Dependencies**: FastAPI, PyArrow, DuckDB, Shapely, `pytest`, Playwright  
**Storage**: N/A (documentation, configuration, and naming alignment — no database schema changes)  
**Testing**: `.venv/bin/pytest -v`, `.venv/bin/python scripts/verify_pmdl_stack.py --rows 500`, static grep audits  
**Target Platform**: Linux container & local development workspace  
**Project Type**: Multi-domain Python/JS C2 + C4ISR integration platform  
**Performance Goals**: Preserve `<2000ms` DuckDB AAR summary verification SLA (`verify_pmdl_stack.py`)  
**Constraints**: Zero broken internal doc/script links; zero stale `PMA` / `Poor-Man's Artemis.IA` identifiers in active files; keep `EdgeSpool` and single-path purity (Constitution v1.3.0) untouched  
**Scale/Scope**: 16 active files updated/renamed across `docs/`, `scripts/`, `tests/`, `src/`, `docker-compose.yml`, `.env.example`, and `.specify/memory/constitution.md`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I–IV. Cone of Uncertainty / Cynefin / OODA / False Cones**: PASS — Straightforward Complicated-domain refactoring aligned with verified partner repository state (`$HOME/Projects/Poor-Man-s-Artemis.IA`).
- **V. Script Organization & Modularity**: PASS — Renamed verification script remains exclusively under `scripts/verify_pmdl_stack.py`.
- **VI. Production Code Purity & Test Isolation**: PASS — Naming update to `src/uservice/security/proxy.py` comment and `tests/conftest.py` docstring introduces zero mocks or network dependencies.
- **VII. Single-Path Success Logic**: PASS — Zero conditional library imports or fallback paths introduced.

## Project Structure

### Documentation (this feature)

```text
specs/007-pmdl-naming-alignment/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code & Affected Paths (repository root)

```text
.env.example
.specify/memory/constitution.md
docker-compose.yml
docs/
├── README.md
├── deployment.md
├── system_architecture.md
└── analysis/
    └── compatibility_with_pmdl.md        # Renamed from compatibility_with_pma.md
scripts/
├── generate_architecture_pdf.js
└── verify_pmdl_stack.py                  # Renamed from verify_pma_stack.py
src/uservice/security/proxy.py
tests/
├── conftest.py
├── e2e/
│   └── pmdl_c2.spec.js                   # Renamed from pma_c2.spec.js
└── integration/
    └── test_pmdl_pipeline.py             # Renamed from test_pma_pipeline.py
```

**Structure Decision**: Retain unified root layout (`docs/`, `scripts/`, `src/`, `tests/`, `.specify/`) with file-level renames for `compatibility_with_pmdl.md`, `verify_pmdl_stack.py`, `test_pmdl_pipeline.py`, and `pmdl_c2.spec.js`. Historical specification directories (`specs/005-pma-integration/`, `specs/006-remove-fallback-logic/`) remain unchanged as immutable audit records.

## Complexity Tracking

No constitution violations; no complexity exemptions required.
