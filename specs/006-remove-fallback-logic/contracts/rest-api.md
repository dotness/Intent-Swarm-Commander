# REST API Contract Changes: 006-remove-fallback-logic

**Feature**: Enforce Single-Path Success Logic & Remove Fallbacks (`006-remove-fallback-logic`)  
**Base Prefix**: `/api/v1` (`http://localhost:8000/api/v1`)  
**Date**: 2026-11-15  

---

## 1. Global Cross-Cutting Contract Rules

### 1.1 Upstream Infrastructure Error Propagation (HTTP `500`)
Per `spec.md` Clarifications (`Q3: Option C`) and Constitution Principle VII:
- Upstream infrastructure/service failures (`MemgraphUnavailableError`, `MinioUnavailableError`, missing/failing Gemini LLM configuration, unreachable Temporal host, missing `COMMANDER_PASSPHRASE`) MUST NOT trigger static/template/regex fallbacks or `503` degraded responses.
- Unhandled service/infrastructure failures surface at the FastAPI boundary as **`500 Internal Server Error`** (consistent across live ASGI serving and hermetic ASGI `httpx` tests).
- Existing client/domain status codes remain unchanged:
  - `401 Unauthorized` (invalid credentials / expired JWT / missing scopes auth challenge)
  - `403 Forbidden` (insufficient scopes / unauthorized project ownership)
  - `404 Not Found` (`ResourceDoesNotExist`, `ObjectNotFoundError`)
  - `422 Unprocessable Entity` (request validation / `ValueError`)

### 1.2 Removal of `degraded_mode` Response Metadata
- Endpoints previously wrapping responses in `meta={"degraded_mode": ...}` or `meta={"threat_check_mode": ...}` (`GET /threats`, `POST /swarms/{swarm_id}/orders`, `POST /smeac/draft`, `GET|POST /analytics/aar`) drop all `degraded_*`, `threat_check_mode`, and `fallback_static_zones` keys from both `data` and `meta`.

---

## 2. Modified Endpoints

### 2.1 Authentication (`src/uservice/security/routes.py`)
- **`POST /api/v1/login`**
  - **Pre-change**: Fell back to `"dev_passphrase"` / `{"dev_passphrase", "dev-passphrase"}` when `COMMANDER_PASSPHRASE` was unset.
  - **Post-change**: Requires `COMMANDER_PASSPHRASE` environment variable. Returns `200 OK` + bearer token on match; `401 Unauthorized` on mismatch; **`500 Internal Server Error`** if `COMMANDER_PASSPHRASE` is unset/misconfigured.

### 2.2 Threats & Targets (`src/uservice/threat/api/routes.py`)
- **`GET /api/v1/threats`**
  - **Post-change `200` Body**: Returns live Memgraph threats only (`ThreatListData` without `fallback_static_zones` and without `meta.degraded_mode`).
  - **Failure (`MemgraphUnavailableError`)**: **`500 Internal Server Error`** (replaces degraded `503` / static zone fallback).
- **`POST /api/v1/threats`** & **`PATCH /api/v1/threats/{threat_id}/deactivate`**
  - **Failure (`MemgraphUnavailableError`)**: **`500 Internal Server Error`** (replaces `503` catch).
- **`GET /api/v1/targets`**, **`GET /api/v1/targets/{target_id}/lineage`**, **`POST /api/v1/targets/{target_id}/review`**
  - **Failure (`MemgraphUnavailableError`)**: **`500 Internal Server Error`** (replaces `503` catch). `404` preserved for missing targets.

### 2.3 SMEAC Orders & Copilot (`src/uservice/smeac/api/routes.py`)
- **`POST /api/v1/swarms/{swarm_id}/orders`**
  - **Post-change `200` Body**: `Response[SmeacOrderResponse]` without `threat_check_mode`, `degraded_mode`, `degraded_reason`, or degraded `meta` flags.
  - **Failure**: Missing `GEMINI_API_KEY`, LLM call failure, Memgraph unavailability, or Temporal `start_workflow` failure surfaces directly as **`500 Internal Server Error`** (no regex coordinate fallback, no skipped threat gate).
- **`GET /api/v1/swarms/{swarm_id}/orders/{order_id}`**
  - **Post-change `200` Body**: `OrderStatusResponse` without `threat_check_mode`, `degraded_mode`, `degraded_reason`.
- **`POST /api/v1/smeac/draft`**
  - **Post-change `200` Body**: Live-synthesized copilot draft referencing live Memgraph/MinIO citations only (no `"static_baseline"`, no `graph_degraded`/`aar_degraded`/`llm_degraded`/`degraded_reasons`, no `meta.degraded_mode`).
  - **Failure**: MinIO, Memgraph, or Gemini failure surfaces as **`500 Internal Server Error`** (no template synthesis fallback).

### 2.4 Analytics & AAR (`src/uservice/analytics/api/routes.py`)
- **`GET /api/v1/analytics/aar`** & **`POST /api/v1/analytics/aar`**
  - **Post-change `200` Body**: `AarQueryResponse` with `engine == "duckdb"`, without `meta.degraded_mode`.
  - **Failure (`MinioUnavailableError`, `MemgraphUnavailableError`, `duckdb` error)**: **`500 Internal Server Error`** (replaces `503` catches).
- **`GET /api/v1/analytics/detections/{event_id}/snapshot`**
  - **Failure (`MinioUnavailableError`, `MemgraphUnavailableError`)**: **`500 Internal Server Error`** (replaces `503` catches). `404` preserved on `ObjectNotFoundError`.

### 2.5 Telemetry (`src/uservice/swarm/api/routes.py`)
- **`GET /api/v1/swarms/{swarm_id}/telemetry`**
  - **Post-change `200` Body**: `TelemetryProjectionResponse` without `degraded_mode`; `telemetry_source` restricted to `"mqtt_live"` | `"mqtt_stale"`.
  - **Failure**: Unavailability of telemetry pipeline/projection surfaces as **`500 Internal Server Error`** (no `"degraded_unavailable"` fallback payload). `404` preserved if swarm does not exist.

### 2.6 HITL Pending & Decisions (`src/uservice/hitl/api/routes.py`)
- **`GET /api/v1/swarms/{swarm_id}/hitl/pending`**
  - **Post-change `200` Body**: `HitlPendingItem` items omit `threat_check_mode` and `degraded_reason`.
- **`POST /api/v1/swarms/{swarm_id}/hitl/{decision_id}/decide`**
  - **Failure**: Memgraph override write failure or Temporal signal failure propagates directly as **`500 Internal Server Error`** instead of being silently logged and suppressed in `HitlFacade.submit_decision`. (`404` for `ResourceDoesNotExist`, `422` for `ValueError` preserved.)

---

## 3. Dashboard Frontend Alignment (`src/dashboard/`)
- `src/dashboard/index.html`: Remove `#degraded-banner` element.
- `src/dashboard/js/api.js`: Remove `updateDegradedBanner()` and `fallback_static_zones` property mapping.
- `src/dashboard/js/main.js`: Remove `threatRes.fallback_static_zones` and `result.threat_check_mode` status suffix.
- `src/dashboard/js/map.js`: Update `renderThreatZones(threats = [], onDeactivate = null)` to render live Memgraph threats only.
- `src/dashboard/js/hitl.js`: Remove `decision.threat_check_mode === 'deterministic_fallback'` warning branch in `showHitlModal`.
