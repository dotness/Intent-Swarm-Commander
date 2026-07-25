# Database Layer

> **Location**: `uservice/database/`
> **Responsibility**: Async SQLAlchemy engine, session factory, declarative base class, and shared ORM mixins.

---

## Engine & Session Factory

### File: `uservice/database/engine.py`

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Global engine (created at import time)
engine = create_async_engine_instance()

# Global session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
```

### Key config

| Setting | Value | Reason |
|---------|-------|--------|
| `expire_on_commit` | `False` | Prevents lazy-load errors after commit in async context |
| `autoflush` | `False` | Explicit control over when data is flushed |
| `pool_pre_ping` | `True` | Checks connection health before use |
| `pool_recycle` | `3600` | Prevents stale connections (1 hour) |

### Database URL construction

```python
def create_database_url(database_name=None) -> str:
    url = f"postgresql+asyncpg://{SQL_DATABASE_SECRETS.username}:{SQL_DATABASE_SECRETS.password}@{SQL_DATABASE_SECRETS.url}"
    if database_name:
        url = f"{url}/{database_name}"
    return url
```

The driver is always `asyncpg` for PostgreSQL. For testing, it automatically falls back to `sqlite+aiosqlite:///:memory:`.

---

## Session Dependency

FastAPI endpoints receive sessions via dependency injection:

```python
from uservice.database.engine import get_db

@router.get("/api/...")
async def my_endpoint(session: AsyncSession = Depends(get_db)):
    facade.session = session
```

### `get_db()` implementation

```python
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

The session is automatically closed after the request, even on error.

### Using sessions outside of FastAPI (e.g., in Temporal activities)

```python
from uservice.database.engine import AsyncSessionLocal

async with AsyncSessionLocal() as session:
    facade.session = session
    # ... do work ...
```

---

## Declarative Base and Mixins

### File: `uservice/database/base.py`

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass
```

**All storage models must inherit from this `Base`.** This ensures they're registered in the same metadata for `create_all()` / `drop_all()`.

### Mixins

| Mixin | Module | Columns Provided |
|-------|--------|------------------|
| `UUIDMixin` | `database/base.py` | `id: UUID` (PK, auto uuid4) |
| `TimestampMixin` | `database/base.py` | `created_at`, `updated_at` (auto) |
| `UserInfoMixin` | `database/base.py` | `name`, `type`, `is_staff`, `is_disabled`, `status`, `configuration` |
| `OwnerMixin` | `base/models/storage/owner_mixin.py` | `owner_id: UUID` (indexed) |
| `BasePermission` | `base/models/storage/permission.py` | `principal_id`, `principal_type`, `action`, `granted_by`, `granted_at` (abstract) |

### Using mixins

```python
from uservice.database.base import Base, UUIDMixin, TimestampMixin
from uservice.base.models.storage.owner_mixin import OwnerMixin

class EntityInfo(Base, UUIDMixin, TimestampMixin, OwnerMixin):
    __tablename__ = "entity_info"
    # ... domain-specific columns ...
```

Order: `Base` first, then mixins, so MRO is correct.

---

## Table Management

### Startup (in `api.py` lifespan)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()    # Test connection
    await create_tables()    # Create all tables from Base metadata
    yield
    await close_database()   # Dispose engine
```

### Functions

```python
async def init_database():    # Tests connection
async def create_tables():    # Base.metadata.create_all()
async def drop_tables():      # Base.metadata.drop_all()
async def close_database():   # engine.dispose()
```

---

## Permission Tables (Per-Domain)

Each domain that needs fine-grained access control creates a permission table:

```python
# uservice/<domain>/models/storage/permission.py

from uservice.database.base import Base
from uservice.base.models.storage.permission import BasePermission

class DomainPermission(Base, BasePermission):
    __tablename__ = "<domain>_permissions"

    resource_id = mapped_column(
        SA_UUID,
        ForeignKey("<domain>_info.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
```

### `BasePermission` columns

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID (PK) | Inherited from UUIDMixin |
| `principal_id` | UUID | User/group receiving the grant |
| `principal_type` | String | `user`, `group`, `service_account` |
| `action` | String | `view`, `edit`, `delete`, `admin` |
| `granted_by` | UUID | Who created this grant |
| `granted_at` | DateTime | When the grant was created |
| `resource_id` | UUID (FK) | The protected resource (defined per domain) |

---

## `PermissionService`

A shared service (`uservice/base/services/permission.py`) handles all CRUD for permission rows:

```python
from uservice.base.services.permission import PermissionService, AccessDenied, Action

# Get service from facade
svc = facade.get_permission_service(DomainPermission)

# Check access
await svc.check_access(resource_id, Action.view)          # bool
await svc.require_access(resource_id, Action.edit)         # raises AccessDenied

# Scope queries
query = select(Model).where(svc.scoped_query(Model, Action.view))

# Grant
await svc.grant(resource_id, principal_id, Action.view)

# Auto-grant owner all permissions
await svc.bulk_grant_defaults(resource_id, owner_id)

# Revoke
await svc.revoke(resource_id, principal_id, Action.edit)
```

---

## MongoDB (Legacy Support)

The `MongoORM` class in `uservice/base/models/storage/morm.py` provides a Pydantic-based ODM for MongoDB via Motor. It supports `get()`, `save()`, `delete()`, and `find()`.

This is a **legacy pattern** — new domains should use SQLAlchemy + PostgreSQL.

---

## Rules

| ✅ DO | ❌ DON'T |
|-------|---------|
| Use `Base` from `database/base.py` for all models | Create separate `declarative_base()` instances |
| Use `UUIDMixin` for primary keys | Define `id` columns manually |
| Use `TimestampMixin` for audit timestamps | Skip timestamps on entities |
| Set `expire_on_commit=False` | Use default session config |
| Use `get_db` dependency in FastAPI routes | Create sessions inside route handlers |
| Use `AsyncSessionLocal` context manager in activities | Pass FastAPI sessions to Temporal |
| Create per-domain permission tables | Share one permission table across all domains |
| Use `ForeignKey(..., ondelete="CASCADE")` for permission→resource | Skip cascading deletes |
