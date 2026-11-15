# Data & Identifier Mapping: PMDL Naming Alignment

No relational database tables, ORM columns, or REST/MQTT wire payload schemas are modified by this feature. The identifier mapping below governs documentation, configuration, scripts, and tests:

| Scope | Legacy Identifier | Aligned Identifier | Notes |
|---|---|---|---|
| Partner Product Name | `Poor-Man's Artemis.IA` | `Poor Man's Defense Lakehouse` | Updated across `docs/`, `scripts/generate_architecture_pdf.js` |
| Partner Acronym | `PMA` | `PMDL` | Updated across `docs/`, `.env.example`, `.specify/memory/constitution.md`, `proxy.py`, `conftest.py` |
| Integration Doc Path | `docs/analysis/compatibility_with_pma.md` | `docs/analysis/compatibility_with_pmdl.md` | Document ID updated to `DOC-ANALYSIS-ISC-PMDL-001` |
| Compose Containers | `pma_mosquitto`, `pma_minio`, `pma_memgraph` | `pmdl_mosquitto`, `pmdl_minio`, `pmdl_memgraph` | In `docker-compose.yml` |
| Temporal Queue Env/Default | `PMA_TASK_QUEUE` / `pma-ingestion-queue` | `PMDL_TASK_QUEUE` / `pmdl-ingestion-queue` | In `docker-compose.yml` and `.env.example` |
| Verification Script | `scripts/verify_pma_stack.py` | `scripts/verify_pmdl_stack.py` | Log prefix `[PMDL Verify]`, temp prefix `isc_pmdl_verify_` |
| Integration Test | `tests/integration/test_pma_pipeline.py` | `tests/integration/test_pmdl_pipeline.py` | Function `test_full_pmdl_c4isr_pipeline_hermetic` |
| Playwright E2E Spec | `tests/e2e/pma_c2.spec.js` | `tests/e2e/pmdl_c2.spec.js` | Suite title `PMDL C4ISR Unified C2 Console (US1-US4)` |
| Upstream Hostnames (Retained) | `artemis-mosquitto`, `artemis-memgraph`, `artemis-minio` | Retained as-is | Matches `$HOME/Projects/Poor-Man-s-Artemis.IA/docker-compose.yml` |
