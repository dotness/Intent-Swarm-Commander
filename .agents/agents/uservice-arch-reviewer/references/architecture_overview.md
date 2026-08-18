# µService Architecture Overview

> **Purpose**: This document is the entry-point for agents and developers working inside `uservice_template`. It describes the layered architecture, naming conventions, and module boundaries that every domain must follow.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     FastAPI  (api.py)                     │
│  lifespan · auth middleware · request-context middleware  │
└────────────────────────┬─────────────────────────────────┘
                         │  registers domain routers
          ┌──────────────┼──────────────────────┐
          ▼              ▼                      ▼
   ┌─────────────┐ ┌─────────────┐      ┌─────────────┐
   │ domain_a/   │ │ domain_b/   │ ...  │ operation/  │
   │   api/      │ │   api/      │      │   facade/   │
   │   facade/   │ │   facade/   │      │   models/   │
   │   models/   │ │   models/   │      └──────┬──────┘
   │   operations│ │   operations│             │
   └──────┬──────┘ └──────┬──────┘             │
          │               │                    │
          ▼               ▼                    ▼
   ┌────────────────────────────────────────────────┐
   │                base/                            │
   │  facade/  models/  operations/  services/       │
   │  middleware/  api/                               │
   └────────────────────────┬───────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────────┐
   │  database/  (engine, base models, mixins)       │
   │  security/  (auth middleware, scheme, models)   │
   │  user/      (user facade & models)              │
   │  secrets.py (pydantic-settings from files)      │
   └────────────────────────────────────────────────┘
```

## Domain Module Layout

Every business domain lives in its own top-level package under `uservice/`. A complete domain contains **four sub-packages**:

```
uservice/<domain_name>/
├── __init__.py
├── api/               # FastAPI routers — thin, no business logic
│   └── <entity>.py
├── facade/            # Coarse-grained DDD facades — ALL business logic
│   └── <entity>.py
├── models/
│   ├── api/           # API-layer models (request / response wrappers)
│   │   ├── request/
│   │   └── response/
│   ├── contract/      # Pydantic DTOs — the canonical shape of domain data
│   │   └── <entity>.py
│   └── storage/       # SQLAlchemy ORM models — DB table definitions
│       └── <entity>.py
└── operations/        # Temporal workflows + ADK agents
    ├── <verb>.py       # e.g. create.py, update.py, delete.py
    ├── <domain>_agents.py
    └── steps/          # Reusable Temporal activities
        └── <verb>.py
```

## Core Principles

1. **Strict layer separation** — API layer never touches SQLAlchemy models directly; it always goes through the Facade. Facades never return storage models; they convert to contract models before returning.
2. **Contract as the truth boundary** — Contract models are the single agreed-upon shape for data exchange between layers. The API receives contract objects, the facade returns contract objects.
3. **Facade = business boundary** — Each facade class inherits `DomainFacade` and encapsulates all CRUD, permissions, and cross-domain calls for one entity.
4. **Operations for async work** — State-mutating actions (create, update, delete) are scheduled as Temporal workflows. The facade creates the DB record synchronously, then submits the workflow.
5. **Agents guard execution** — Each Temporal workflow delegates to an ADK 2.0 multi-agent pipeline: Planner → Guardian Critic → Executor.

## Cross-Domain Communication

Domains talk to each other **only through facades**, never through raw DB queries across tables. Example from `Vm` calling `Federation`:

```python
from uservice.federation.facade.federation import Federation

federation_instance = await Federation.create(user=self.user)
federation_instance.session = self.session
federation_info = await federation_instance.get_federation(name=federation_name)
```

## Infrastructure Domains

| Package | Role |
|---------|------|
| `base/` | Abstract base classes for facades, operations, models, middleware, and shared services (permission engine). |
| `database/` | SQLAlchemy engine, session factory, `Base` declarative class, and common mixins (`UUIDMixin`, `TimestampMixin`). |
| `security/` | JWT scheme, authentication middleware, user context (`ContextVar`). |
| `user/` | User CRUD facade and models. Required by auth middleware. |
| `operation/` | Operation tracking facade and models. Used by `BaseWorkflow` to log workflow lifecycle. |

## Related Documentation

| Document | Topic |
|----------|-------|
| [API Layer](api_layer.md) | Route design, input/output, response wrappers |
| [Models](models.md) | API, Contract, and Storage model rules |
| [Facades](facades.md) | DomainFacade pattern, session management, permissions |
| [Operations](operations.md) | Temporal workflows, ADK agents, activity steps |
| [Security & Auth](security.md) | Authentication flow, JWT, ContextVar user context |
| [Database](database.md) | Engine, sessions, mixins, migrations |
