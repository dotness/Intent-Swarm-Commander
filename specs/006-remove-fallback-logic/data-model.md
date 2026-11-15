# Data Model & Schema Changes: 006-remove-fallback-logic

**Feature**: Enforce Single-Path Success Logic & Remove Fallbacks (`006-remove-fallback-logic`)  
**Date**: 2026-11-15  

This document specifies all ORM storage modifications, Pydantic contract DTO changes, binary storage format updates, and explicitly retained tactical entities.

---

## 1. SQLAlchemy ORM Storage Models (`src/uservice/*/models/storage/`)

### 1.1 `SmeacOrder` (`src/uservice/smeac/models/storage/smeac.py`)
| Column | Change | Rationale |
|---|---|---|
| `threat_check_mode` | **REMOVE** | Graph threat verification runs solely via live Memgraph; dual mode indicator is obsolete (FR-005). |
| `degraded_reason` | **REMOVE** | Degraded execution is prohibited; failures raise HTTP `500` (FR-005). |

All existing command, intent, swarm, status, and audit fields remain unchanged.

### 1.2 `HitlDecision` (`src/uservice/hitl/models/storage/decision.py`)
| Column | Change | Rationale |
|---|---|---|
| `threat_check_mode` | **REMOVE** | Eliminates `"deterministic_fallback"` tracking on HITL approval items (FR-005). |
| `degraded_reason` | **REMOVE** | Eliminates degraded override annotations (FR-005). |

All decision outcome, rationale, override justification, and command linkage fields remain unchanged.

### 1.3 `SwarmLiveState` / `LiveTelemetryStore` (`src/uservice/telemetry/models/storage/live_state.py`)
- **`LiveTelemetryStore.get_swarm_drones`**: Remove the `"degraded_unavailable"` fallback status when telemetry state is missing/unpopulated. Telemetry reads return only active/stale MQTT-ingested records (`"mqtt_live"` / `"mqtt_stale"`), or raise directly when the live store/MQTT pipeline is unavailable.

### 1.4 Database Schema Migration Strategy
- **Hermetic SQLite (`tests/`)**: Recreated automatically via `Base.metadata.create_all` against fresh in-memory/temp databases with `aiosqlite`.
- **PostgreSQL (`uservice`)**: When applying against existing databases, drop obsolete columns safely via:
  ```sql
  ALTER TABLE smeac_orders DROP COLUMN IF EXISTS threat_check_mode, DROP COLUMN IF EXISTS degraded_reason;
  ALTER TABLE hitl_decisions DROP COLUMN IF EXISTS threat_check_mode, DROP COLUMN IF EXISTS degraded_reason;
  ```
  (Exact table names to match SQLAlchemy `__tablename__` definitions in those modules during implementation.)

---

## 2. Pydantic Contract DTOs (`src/uservice/*/models/contract/`)

### 2.1 Threat Contracts (`src/uservice/threat/models/contract/schemas.py`)
- **`ThreatListData`**:
  - **REMOVE** field `fallback_static_zones`.
  - Retains live Memgraph threat records exclusively.
- **`RouteThreatEvaluation`**:
  - **REMOVE** fields `threat_check_mode`, `degraded_mode`, `degraded_reason`.

### 2.2 SMEAC & Copilot Contracts (`src/uservice/smeac/models/contract/schemas.py`)
- **`SmeacOrderResponse`**:
  - **REMOVE** fields `threat_check_mode`, `degraded_mode`, `degraded_reason`.
- **`OrderStatusResponse`**:
  - **REMOVE** fields `threat_check_mode`, `degraded_mode`, `degraded_reason`.
- **`SmeacCitation`**:
  - **MODIFY** `source_type`: remove `"static_baseline"` literal option; citations reflect live Memgraph and DuckDB/MinIO sources only.
- **Copilot Draft DTO & Operations (`src/uservice/smeac/operations/copilot.py`, `schemas.py`)**:
  - **REMOVE** degraded tracking fields/flags (`graph_degraded`, `aar_degraded`, `llm_degraded`, `degraded_reasons`).

### 2.3 HITL Contracts (`src/uservice/hitl/models/contract/schemas.py`)
- **`HitlPendingItem`**:
  - **REMOVE** fields `threat_check_mode`, `degraded_reason`.

### 2.4 Telemetry Contracts (`src/uservice/telemetry/models/contract/events.py`)
- **`TelemetryProjectionResponse`**:
  - **REMOVE** field `degraded_mode: bool = False`.
  - **MODIFY** `telemetry_source`: narrow from `Literal["mqtt_live", "mqtt_stale", "degraded_unavailable"]` to `Literal["mqtt_live", "mqtt_stale"]`.

### 2.5 Analytics AAR Contracts (`src/uservice/analytics/models/contract/aar.py`)
- **`AarQueryResponse`**:
  - **MODIFY** default value of `engine` from `"sqlite_olap"` to `"duckdb"`.
  - Eliminate any `"sqlite_olap"` literal/fallback mode in AAR query responses.

---

## 3. Binary & Geospatial Artifact Contracts

### 3.1 Parquet Lakehouse Artifacts (`compactor.py` → `duckdb_runner.py`)
- **Format**: Strictly standard Apache Parquet (`PAR1` magic header/footer) written via `pyarrow.parquet` and queried directly by `duckdb`.
- **Removed Format**: Custom `_ISC_COL_HEADER = b"PAR1ISCC"` / `_ISC_COL_FOOTER = b"PAR1"` fallback encoding and reader branch are completely deleted.

### 3.2 Geospatial Threat Containment
- **Engine**: Strictly `shapely.geometry` (`Point`, `shape`).
- **Removed Format/Store**: Custom pure-Python `_point_in_ring` ray-caster and `config/restricted_zones.json` static threat fallback data path.

---

## 4. Explicitly Retained Tactical Models

### 4.1 `EdgeSpool` (`src/edge/telemetry/publisher.py`)
- **Classification**: Intentional DDIL domain resilience queue (FR-004).
- **Behavior**: Buffers telemetry frames in local SQLite WAL storage during physical RF/MQTT link loss and drains in order upon reconnection via `paho.mqtt.client`. All `PAHO_AVAILABLE` import-fallback bypass code around it is removed.
