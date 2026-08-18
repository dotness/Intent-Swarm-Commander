# Implementation Plan: Intent Swarm Commander — MVP System

**Branch**: `001-isc-mvp-system` | **Date**: 2026-07-24 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/001-isc-mvp-system/spec.md)

**Input**: Feature specification from `specs/001-isc-mvp-system/spec.md`

## Summary

Build an MCP-enabled Command Agent system that translates high-level military intents (SMEAC orders) into coordinated drone swarm actions using coarse-grained operators. The system is a multi-service architecture deployed via Docker Compose, using Python for the backend services, a web-based commander dashboard, and MCP JSON-RPC over SSE/HTTP as the canonical agent-to-tool protocol. Each swarm is isolated in its own container, dynamically provisioned via a Central Provisioning API and routed through a single MCP Auth Gateway for security and audit compliance. The MVP now includes edge autonomy, utilizing a Raspberry Pi 5 onboard controller running OpenCV and YOLO-E for real-time target identification and autonomous navigation.

## Technical Context

**Language/Version**: Python 3.12 (backend services), TypeScript/JavaScript (frontend dashboard)

**Primary Dependencies**:
- Backend: FastAPI (HTTP server), `temporalio` (Temporal workflow orchestration), `pydantic-ai` (multi-agent pipelines), SQLAlchemy (ORM), `mcp` SDK (MCP server/client), Docker SDK for Python
- Edge (Raspberry Pi 5): OpenCV (computer vision), YOLO-E (object detection), drone flight control SDK (e.g., MAVSDK)
- Frontend: Vanilla JS with modern CSS (no framework), Leaflet.js
- Infrastructure: Docker Compose, Nginx, Temporal Server (requires Cassandra/Postgres), Postgres (for SQLAlchemy)

**Storage**: PostgreSQL (SQLAlchemy ORM for domains) + Temporal State Store

**Testing**: pytest (backend unit/integration), Playwright (frontend E2E), httpx (contract tests)

**Target Platform**: Linux server (Docker Compose on single machine), Raspberry Pi 5 (Edge Node), web browser (commander dashboard)

**Project Type**: Multi-service web application with container orchestration

**Performance Goals**: SMEAC order to command breakdown within 15 seconds (SC-001); swarm instance provisioning within 30 seconds

**Constraints**: Fail-closed on gateway/verification unavailability (FR-009); 0% false-negative rate on safety constraint violations (SC-004); all actions audited (SC-003)

**Scale/Scope**: Multiple concurrent commanders, multiple active swarm instances, physical drone integration with edge autonomy on Raspberry Pi 5

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-Phase 0 | Post-Phase 1 |
|-----------|-------------|--------------|
| I. LTV Framework | ✅ Anchored to MCP_Integration_Standard, MCP_Gateway_Auth_Gateway nodes | ✅ Architecture directly implements these nodes |
| II. Cynefin Domain | ✅ Classified as "Complicated" — known unknowns, deterministic verification, expert-analyzable | ✅ Confirmed — Inverted Cone methodology appropriate |
| III. OODA Loops | ✅ 6 independently testable user stories as micro-hypotheses | ✅ Phased implementation supports iterative validation |
| IV. False Cones | ✅ Avoids LLM self-reflection (use formal solvers), static API keys (use JIT), standard service accounts (use NHI) | ✅ No false cone technologies adopted |
| V. Script Organization | ✅ All scripts in `scripts/` | ✅ Confirmed |
| Node Alignment | ✅ Maps to 3 LTV nodes | ✅ Each service maps to a specific node |

**Gate Result**: PASS — No violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-isc-mvp-system/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── provisioning-api.md
│   ├── swarm-instance-api.md
│   └── mcp-tools.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── uservice/
│   ├── base/                   # Abstract base classes, mixins, shared middleware
│   ├── database/               # SQLAlchemy engine, sessions
│   ├── security/               # JWT scheme, auth middleware
│   ├── operation/              # Temporal operation tracking facade/models
│   ├── swarm/                  # Domain: Swarm lifecycle & provisioning
│   │   ├── api/
│   │   ├── facade/
│   │   ├── models/             # api/, contract/, storage/
│   │   └── operations/         # Temporal workflows + pydantic-ai agents
│   │       ├── create.py       # Provisioning workflow
│   │       ├── delete.py       # Draining/termination workflow
│   │       └── swarm_agents.py # Planner, Guardian Critic, Executor
│   ├── smeac/                  # Domain: Intent ingestion & translation
│   │   ├── api/
│   │   ├── facade/
│   │   ├── models/
│   │   └── operations/
│   │       ├── process.py      # SMEAC -> Commands workflow
│   │       └── smeac_agents.py
│   └── hitl/                   # Domain: Approval gating
│       ├── api/
│       ├── facade/
│       └── models/
│
├── dashboard/                  # Commander web UI (unchanged)
│   ├── index.html
│   ├── css/
│   └── js/
│
├── edge/                       # Raspberry Pi 5 onboard software
│   ├── vision/                 # OpenCV and YOLO-E inference
│   ├── navigation/             # Autonomous flight logic
│   └── api/                    # Edge API for swarm communication
│
└── docker/
    ├── docker-compose.yml      # Includes Temporal, Postgres, and the uService API
    └── Dockerfile.api          # Unified uService API image

tests/
├── unit/
├── integration/
└── contract/
```

**Structure Decision**: The backend strictly follows the `uservice-template` Domain-Driven Design architecture. State-mutating actions (provisioning swarms, processing SMEACs) are executed as durable Temporal workflows orchestrated by pydantic-ai multi-agent pipelines (Planner → Guardian Critic → Executor). All cross-domain communication occurs strictly through domain Facades. The new edge component handles localized computer vision (YOLO-E) and autonomous targeting independently from the command post backend.

## Complexity Tracking

No constitution violations to justify.
