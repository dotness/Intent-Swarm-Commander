# Quickstart Validation Guide: PMDL Naming Alignment

## 1. Verify Zero Stale Active References

```bash
grep -rnE "Poor-Man|Poor Man's A|PMA|\bpma\b|pma_" README.md docs/ scripts/ src/ tests/ docker-compose.yml .env.example .specify/memory/ --exclude-dir=__pycache__ --exclude="*.pdf" --exclude="*.jpg" --exclude="*.png"
```

Expected: Only the explicit partner directory note (`Poor-Man-s-Artemis.IA`) in `docs/analysis/compatibility_with_pmdl.md`.

## 2. Verify Renamed Stack Benchmark Script

```bash
.venv/bin/python scripts/verify_pmdl_stack.py --rows 500
```

Expected: Exits `0` with `[PMDL Verify]` output and `AAR (duckdb) summary on 500 rows completed in < 2000 ms`.

## 3. Verify Full Automated Test Suite

```bash
COMMANDER_PASSPHRASE=test-commander-passphrase GEMINI_API_KEY=test-gemini-key .venv/bin/pytest -v
```

Expected: All tests pass (`27 passed`), including `tests/integration/test_pmdl_pipeline.py::test_full_pmdl_c4isr_pipeline_hermetic`.
