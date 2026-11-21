# Quickstart Validation Guide: Gradual Corridor Path Discovery and Adaptive Survey

**Feature**: `012-corridor-path-discovery` | **Date**: `2026-11-19` | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/spec.md)

## Prerequisites

1. **Python & Node Tooling**: Python 3.12+ virtual environment (`.venv`) synchronized via `uv sync` and Playwright installed (`npx playwright --version`).
2. **Environment Configuration**: `.env` configured with `GEMINI_API_KEY`, `COMMANDER_PASSPHRASE`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, and database/broker settings matching `docker-compose.yml`.
3. **Reference Documentation**:
   - Entity schemas & state transitions: [data-model.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/data-model.md)
   - API, Edge, MQTT & Virtual-Cam contracts: [corridor-survey-contract.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/012-corridor-path-discovery/contracts/corridor-survey-contract.md)

---

## Validation Scenario 1: Hermetic Unit & Contract Tests

Run all hermetic tests covering 3D corridor visual perception, `CorridorSurveyController` state transitions, SMEAC coordinate-free parsing, C2 facade/API validation, and MQTT contract provenance without requiring live external network calls:

```bash
pytest \
  tests/unit/test_corridor_analyzer.py \
  tests/unit/test_corridor_survey_controller.py \
  tests/unit/test_corridor_smeac_and_api.py \
  tests/contract/test_corridor_mqtt_contract.py \
  tests/contract/test_mqtt_contract.py \
  -v
```

**Expected Outcome**:
- `CorridorVisualAnalyzer` processes frames well within the `500 ms` SLA (`SC-007`), detects dead ends, turns, low overhangs, slopes, forks, and degraded (dark/blur/frozen) feeds (`FR-004`, `FR-006`, `FR-011`, `FR-015`).
- `CorridorSurveyController` completes the 8-heading `360°` initial look-around sweep while holding at origin before any forward movement (`SC-002`), navigates straight/L-turn/S-bend/overhang paths within configurable `[min_altitude_m, max_altitude_m]` bounds (`FR-021`), triggers failsafe reverse return after `5 s` edge guidance timeout (`SC-004`, `SC-007`), retraces 3D breadcrumbs on return (`SC-005`), and differentiates `recall` vs. `emergency_abort` (`FR-018`).
- SMEAC intake accepts `"go check the corridor next 20 meters and go back"` with `RelativeCorridor`, rejects `<= 0` distances with `422`, defaults omitted distance to `20.0 m`, assigns `drone-1` as lead scout while holding remaining swarm drones (`FR-019`), and preserves all Feature 011 MQTT contracts.

---

## Validation Scenario 2: Security & Production Purity Verification

Run static security and Constitution VI/VII purity verification checks:

```bash
# 1. Verify zero conditional imports or fallback flags in src/
grep -rnE '_AVAILABLE|except ImportError' src/ || echo "CONSTITUTION_VII_CLEAN"

# 2. Verify zero innerHTML / confirm / alert / eval usage in dashboard corridor JS
grep -rnE 'innerHTML|outerHTML|insertAdjacentHTML|document\.write|confirm\(|alert\(|eval\(' src/dashboard/js/corridor.js || echo "FRONTEND_XSS_CLEAN"

# 3. Verify existing unit & security suites remain green
pytest tests/unit/ -v
```

**Expected Outcome**:
- Zero `ImportError` fallback guards or `*_AVAILABLE` flags in `src/`.
- Zero unsafe DOM injection or blocking native dialog patterns in `src/dashboard/js/corridor.js`.
- Hermetic API/authorization tests verify `401/403` on missing/insufficient JWT scopes, `404` on cross-swarm/cross-project snapshot IDOR attempts, strict UUID/regex key validation, and JPEG magic-byte/size enforcement.

---

## Validation Scenario 3: Live Zero-Mock Multi-Shape Corridor E2E Verification

Start the full Docker Compose ecosystem (PostgreSQL, Temporal, Mosquitto, MinIO, Memgraph, `backend`, `dashboard`, `virtual_cam`, `edge_drone`, `drone_sim` PX4 SITL):

```bash
docker compose up -d --build
npx playwright test tests/e2e/prod_corridor_survey.spec.js
```

**Expected Outcome**:
1. **Multi-Shape Corridor Traversal (`straight_20m`, `l_turn_20m`, `s_bend_overhang_20m`)**:
   - Submitting coordinate-free SMEAC order *"go check the corridor next 20 meters and go back"* assigns `drone-1` as lead scout and holds `drone-2`/`drone-3` at staging (`FR-019`).
   - Drone hovers at origin through the 360° look-around sweep before moving (`SC-002`), adapts headings and 3D altitude along the L-turn and overhang (`SC-003`), reaches `~20 m` cumulative 3D path distance, and retraces the discovered 3D breadcrumbs back to origin (`SC-005`).
2. **Early Dead-End Termination (`dead_end_12m`) & Two-Tier Operator Override**:
   - Dead-end corridor terminates cleanly around `12 m` and autonomously returns to origin; recall and emergency-abort overrides behave distinctly (`FR-018`) and record operator provenance.
3. **Full Snapshot Persistence & Dashboard Visualization (`FR-012`, `FR-013`, `FR-020`, `SC-006`)**:
   - Every captured snapshot is persisted in MinIO and viewable via authenticated BFF proxy in the **Corridor Survey & Intelligence** panel alongside live 3D Top-Down Plan & Elevation Profile SVG views and the complete `CorridorIntelligenceReport` within `5 s` of mission completion.
