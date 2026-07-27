# Implementation Plan: Replace Mocks, Stubs & Hardcodes

**Branch**: `002-replace-mocks-production` | **Date**: 2026-07-27 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/002-replace-mocks-production/spec.md)

**Input**: Feature specification from `specs/002-replace-mocks-production/spec.md`

## Summary

Replace all 20 identified mock implementations, in-memory stubs, and hardcoded values across the three system layers (frontend dashboard, microservices backend, edge services) with real production integrations. The existing codebase already has ORM models, a database engine, JWT authentication middleware, Temporal workflow infrastructure, and contract schemas in place — the mocks exist in the *usage* layer (facades, operations, frontend JS) where these components should be wired together.

## Technical Context

**Language/Version**: Python 3.14 (backend/edge), JavaScript ES2022 (frontend dashboard)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (asyncpg), Temporal SDK, pydantic-ai, python-jose (JWT), MAVSDK, ultralytics (YOLO), OpenCV, Docker SDK (docker-py), httpx, Leaflet.js

**Storage**: PostgreSQL via `asyncpg` (async SQLAlchemy engine already configured in `src/uservice/database/engine.py`)

**Testing**: pytest (existing `tests/` directory with `contract/`, `integration/`, `unit/` structure)

**Target Platform**: Linux server (backend microservices), Raspberry Pi 5 (edge), Web browser (dashboard)

**Project Type**: Multi-tier distributed system — web dashboard + microservices + edge IoT

**Performance Goals**: Dashboard telemetry updates ≤ 2s; RBAC enforcement ≤ 500ms; real-time edge processing at ~10 FPS

**Constraints**: All operations must use existing DomainFacade pattern (session + user context); Temporal workflows must remain durable; edge modules must fail loudly when hardware is missing

**Scale/Scope**: Single commander deployment; 1-N swarms with 1-N drones per swarm

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Cone of Uncertainty (LTV)** | ✅ PASS | This feature moves the system from AS-IS (MVP with mocks) toward TO-BE (production-ready). Directly satisfies the transition path. |
| **II. Cynefin Domain** | ✅ PASS | This is a **Complicated** domain problem — the path from mock to production is deterministic; we know all the interfaces and just need to wire them. Backward planning applies. |
| **III. OODA Loops** | ✅ PASS | Each mock replacement is a small, reversible, independently testable change. No massive irreversible architectural decisions. |
| **IV. False Cones** | ✅ PASS | No new technology choices — we are integrating the existing declared stack (SQLAlchemy, Temporal, Docker SDK, MAVSDK, etc.). |
| **V. Script Organization** | ✅ PASS | No new standalone scripts are created by this feature. |
| **Architecture Review** | ✅ PASS | All changes follow the existing DomainFacade + ORM + Temporal patterns. No new architectural layers introduced. |

## Project Structure

### Documentation (this feature)

```text
specs/002-replace-mocks-production/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── dashboard/                    # Frontend — vanilla HTML/JS
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── api.js                # ← MOCK: hardcoded token, simulated telemetry
│       ├── auth_indicator.js     # ← MOCK: hardcoded isAuthenticated + commanderId
│       ├── hitl.js               # ← MOCK: hardcoded token
│       ├── map.js
│       └── main.js
│
├── uservice/                     # Backend microservices — Python/FastAPI
│   ├── main.py                   # App bootstrap (middleware already wired)
│   ├── database/
│   │   ├── base.py               # ORM base + mixins (already exists)
│   │   └── engine.py             # Async session factory (already exists)
│   ├── security/
│   │   ├── jwt.py                # JWT decode/validate (already exists)
│   │   ├── jit.py                # JIT credential issuance (already exists)
│   │   ├── middleware.py         # Auth gateway middleware (already exists)
│   │   └── proxy.py              # ← MOCK: falls through to local routes
│   ├── smeac/
│   │   ├── facade/smeac.py       # ← MOCK: RBAC commented out, DB persistence commented out, hardcoded status
│   │   ├── operations/process.py # ← MOCK: safety check pass-through, HITL hardcoded True
│   │   └── models/
│   │       ├── contract/schemas.py  # Pydantic schemas (already exists)
│   │       └── storage/smeac.py     # ORM model (already exists)
│   ├── hitl/
│   │   ├── facade/hitl.py        # ← MOCK: in-memory _pending_decisions dict
│   │   └── models/
│   │       ├── contract/schemas.py  # Pydantic schemas (already exists)
│   │       └── storage/decision.py  # ORM model (already exists)
│   └── swarm/
│       ├── facade/               # (swarm facade — may not exist yet)
│       ├── operations/
│       │   ├── create.py         # ← MOCK: in-memory _swarms, simulated container_id
│       │   ├── delete.py         # ← MOCK: instant termination, references in-memory dict
│       │   └── swarm_agents.py   # ← MOCK: check_geofencing always returns None
│       └── models/
│           ├── contract/schemas.py  # Pydantic schemas (already exists)
│           └── storage/instance.py  # ORM model (already exists)
│
├── edge/                         # Edge IoT — Python on Raspberry Pi 5
│   ├── api/server.py             # ← MOCK: FastAPI conditional import stub
│   ├── vision/
│   │   ├── camera.py             # ← MOCK: simulation fallback, returns None
│   │   └── inference.py          # ← MOCK: simulation fallback, returns []
│   └── navigation/
│       └── flight_controller.py  # ← MOCK: hardcoded 320 center, simulated distance, no-op yaw

tests/
├── contract/
├── integration/
│   ├── test_e2e.py
│   └── test_security.py
└── unit/
```

**Structure Decision**: No structural changes required. The project already follows a clean domain-driven architecture with separate `models/contract` (API schemas), `models/storage` (ORM), `facade` (business logic), `operations` (workflows), and `api` (routes) layers. All mock replacements happen within existing files.

## Complexity Tracking

No constitution violations — table omitted.
