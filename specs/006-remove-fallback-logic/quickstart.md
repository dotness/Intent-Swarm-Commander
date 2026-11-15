# Verification Quickstart: 006-remove-fallback-logic

**Feature**: Enforce Single-Path Success Logic & Remove Fallbacks (`006-remove-fallback-logic`)  
**Prerequisites**: Synchronized `.venv` with all dependencies from `requirements.txt` / `pyproject.toml` installed as real wheels (no shims).

---

## 1. Environment & Unconditional Import Verification

Confirm all runtime, Edge, and test wheels import cleanly in `.venv` without fallbacks or `opentelemetry` conflicts:

```bash
.venv/bin/python -c "
import shapely, duckdb, pyarrow, aiomqtt, neo4j, boto3, aiosqlite, cv2, ultralytics, mavsdk, pydantic_ai
import paho.mqtt.client as mqtt
from shapely.geometry import Point, shape
from pydantic_ai import Agent
print('All single-path dependencies verified!')
"
```

---

## 2. Static Fallback-Purity Audit (Zero Violations Allowed)

Run static grep checks across `src/` (and `tests/conftest.py`) to confirm every banned pattern is absent:

```bash
# Must return exit code 1 (zero matches) for conditional library imports & flags
grep -rnE "_AVAILABLE|except ImportError" src/ tests/conftest.py

# Must return exit code 1 (zero matches) for fallback/degraded engine patterns in src/
grep -rnE "degraded_mode|degraded_reason|degraded_reasons|threat_check_mode|fallback_static_zones|sqlite_olap|PAR1ISCC|deterministic_fallback|degraded_unavailable|_point_in_ring|load_static_restricted_zones|_evaluate_static_zones|placeholder_key|dev_passphrase|dev-passphrase|127\.0\.1\.1:7233" src/
```

---

## 3. Preserved Domain Capabilities Check

Confirm `EdgeSpool` SQLite WAL DDIL buffering remains intact in `src/edge/telemetry/publisher.py`:

```bash
grep -rn "class EdgeSpool" src/edge/telemetry/publisher.py
```

---

## 4. Hermetic Test Suite Verification

Run all unit, contract, and integration suites inside `.venv` with required environment configuration:

```bash
COMMANDER_PASSPHRASE=test-commander-passphrase \
GEMINI_API_KEY=test-gemini-key \
.venv/bin/pytest -v
```

### Targeted Verification Suites
- **Unit Geospatial, Parquet & DuckDB OLAP**:
  `.venv/bin/pytest tests/unit/test_telemetry_compactor.py tests/unit/test_duckdb_aar.py -v`
- **Unit Threat Gating & SMEAC Copilot (Error Propagation)**:
  `.venv/bin/pytest tests/unit/test_threat_gating.py tests/unit/test_smeac_copilot.py -v`
- **Contract Tests (No `degraded_mode`, HTTP `500` on infrastructure outage)**:
  `.venv/bin/pytest tests/contract/test_threat_and_hitl_contract.py -v`
- **Integration Tests**:
  `.venv/bin/pytest tests/integration/ -v`
