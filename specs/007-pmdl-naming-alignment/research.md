# Research: Poor Man's Defense Lakehouse Naming Alignment

## Upstream Repository Audit

- **Inspected Path**: `$HOME/Projects/Poor-Man-s-Artemis.IA/` (Git HEAD `c293ba23`, `Initial commit: Poor Man's Defense Lakehouse`)
- **Findings**:
  - **Product Name**: Renamed from `Poor-Man's Artemis.IA` (`PMA`) to **`Poor Man's Defense Lakehouse`** (`PMDL`).
  - **Upstream Directory & Internal Infrastructure**: The directory on disk remains `Poor-Man-s-Artemis.IA`, and its `docker-compose.yml` / `.env.example` still use `artemis-traefik`, `artemis-mosquitto`, `artemis-minio`, `artemis-memgraph`, `artemis-postgres`, `artemis-redis`, `artemis-temporal`, `artemis-net`, and `/tmp/artemis/buffer`.

## Design Decisions

1. **Product Branding Refactor (`Poor-Man's Artemis.IA` / `PMA` → `Poor Man's Defense Lakehouse` / `PMDL`)**:
   - **Decision**: Rename active prose, doc titles, links, chapter IDs, local Docker container names (`pmdl_mosquitto`, `pmdl_minio`, `pmdl_memgraph`), task queue (`PMDL_TASK_QUEUE` / `pmdl-ingestion-queue`), scripts (`verify_pmdl_stack.py`), and test filenames (`test_pmdl_pipeline.py`, `pmdl_c2.spec.js`) to `PMDL` / `pmdl`.
   - **Rationale**: Eliminates stale branding in `Intent-Swarm-Commander` while aligning container and verification tooling with the renamed partner platform.
   - **Alternatives considered**: Renaming upstream-owned `artemis-*` container examples inside `compatibility_with_pmdl.md` — rejected because upstream `Poor-Man-s-Artemis.IA/docker-compose.yml` still defines `artemis-*`.

2. **Historical Spec Archive Preservation**:
   - **Decision**: Leave `specs/005-pma-integration/` and `specs/006-remove-fallback-logic/` untouched as immutable historical records.
   - **Rationale**: Spec Kit feature directories serve as historical point-in-time specifications; `007-pmdl-naming-alignment` records the rename cleanly.
