# Models — API, Contract, Storage

> **Location**: `uservice/<domain>/models/`
> **Responsibility**: Data shapes. Each sub-layer has a specific purpose and strict rules about what it imports and what it returns.

---

## Three-Layer Model Architecture

```
                  ┌───────────────────────┐
 HTTP boundary →  │   models/api/         │  request & response shapes
                  │   request/<entity>.py  │
                  │   response/<entity>.py │
                  └──────────┬────────────┘
                             │  imports ↓
                  ┌──────────┴────────────┐
 Business logic → │   models/contract/    │  canonical DTOs (Pydantic)
                  │   <entity>.py         │
                  │   <enums>.py          │
                  └──────────┬────────────┘
                             │  facade converts between ↕
                  ┌──────────┴────────────┐
 Database →       │   models/storage/     │  SQLAlchemy ORM models
                  │   <entity>.py         │
                  │   mixin.py            │
                  └───────────────────────┘
```

### Dependency direction

- **API models** may import contract models (for enums, types).
- **Contract models** must NOT import storage or API models.
- **Storage models** must NOT import contract or API models.
- **Facades** import both contract and storage, and perform the conversion.

---

## 1. Contract Models (`models/contract/`)

### Purpose

The **single source of truth** for the shape of domain data as it crosses boundaries. Every layer communicates using contract models. They are **pure Pydantic**.

### Base class

```python
from uservice.base.models.api import base

class EntityInfo(base.BaseModel):
    ...
```

`base.BaseModel` extends `pydantic.BaseModel` with this configuration:

```python
model_config = pydantic.ConfigDict(
    from_attributes=True,      # Enables model_validate() from ORM objects
    use_enum_values=True,      # Serializes enums as their values
    arbitrary_types_allowed=True,
    validate_assignment=True,
)
```

### What to define here

| Type | Purpose | Naming |
|------|---------|--------|
| **Info model** | Full read representation of the entity | `<Entity>Info` |
| **CreateRequest** | Fields required to create the entity | `<Entity>CreateRequest` |
| **UpdateRequest** | Optional fields for partial update | `<Entity>UpdateRequest` |
| **Configuration** | Nested config object | `<Entity>Configuration` |
| **Status enum** | Lifecycle states | `<Entity>Status(str, Enum)` |
| **Type enum** | Category/variant | `<Entity>Type(str, Enum)` |

### Example — VM Contract

```python
# uservice/vm/models/contract/vm.py

from uservice.base.models.api import base
from uuid import UUID
from datetime import datetime
from enum import Enum


class VmStatus(str, Enum):
    creating = "creating"
    running = "running"
    stopped = "stopped"
    error = "error"
    deleting = "deleting"
    deleted = "deleted"


class VmProvider(str, Enum):
    aws = "aws"
    azure = "azure"
    gcp = "gcp"
    local = "local"


class VmConfiguration(base.BaseModel):
    cpu: int
    memory: int       # MB
    disk_size: int    # GB
    network_config: dict


class VmInfo(base.BaseModel):
    id: UUID
    name: str
    federation_id: UUID
    status: VmStatus
    provider: VmProvider
    region: str
    size: str
    image: str
    ip_address: str | None = None
    created_at: datetime
    updated_at: datetime
    configuration: VmConfiguration
    vm_metadata: dict = {}


class VmCreateRequest(base.BaseModel):
    name: str
    provider: VmProvider
    region: str
    size: str
    image: str
    configuration: VmConfiguration


class VmUpdateRequest(base.BaseModel):
    name: str | None = None
    size: str | None = None
    configuration: VmConfiguration | None = None
```

### Rules

| ✅ DO | ❌ DON'T |
|-------|---------|
| Inherit from `base.BaseModel` | Use plain `pydantic.BaseModel` |
| Use `str \| None = None` for optional update fields | Use `Optional` from `typing` (prefer `\|` syntax) |
| Define enums as `(str, Enum)` | Use plain strings for status/type fields |
| Keep configuration as a nested Pydantic model | Use raw `dict` for structured config |
| Use `UUID` for IDs, `datetime` for timestamps | Use `str` for IDs |

---

## 2. Storage Models (`models/storage/`)

### Purpose

SQLAlchemy ORM models that map 1:1 to database tables. They define the **physical schema**.

### Base classes and mixins

All storage models inherit from the classes in `uservice/database/base.py`:

```python
from uservice.database.base import Base, UUIDMixin, TimestampMixin
```

| Mixin | Provides |
|-------|----------|
| `Base` | SQLAlchemy `DeclarativeBase` — required as a mixin for all table models |
| `UUIDMixin` | `id: UUID` primary key (auto-generated `uuid4`) |
| `TimestampMixin` | `created_at`, `updated_at` with auto-defaults |
| `OwnerMixin` (from `base/models/storage/`) | `owner_id: UUID` — tracks resource creator |
| `PermissionMixin` (domain-specific) | `owner`, `edit_grants`, `view_grants` JSON columns |

### Example — VM Storage Model

```python
# uservice/vm/models/storage/vm.py

from sqlalchemy import String, UUID, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from uuid import UUID as UUIDType

from uservice.database.base import Base, UUIDMixin, TimestampMixin
from .mixin import PermissionMixin


class VmInfo(Base, UUIDMixin, TimestampMixin, PermissionMixin):
    __tablename__ = "vm_info"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    federation_id: Mapped[UUIDType] = mapped_column(UUID, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    size: Mapped[str] = mapped_column(String(50), nullable=False)
    image: Mapped[str] = mapped_column(String(100), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    vm_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
```

### Domain-specific mixins

Create mixins in `models/storage/mixin.py` for columns shared across multiple entities within a domain:

```python
# uservice/vm/models/storage/mixin.py

class PermissionMixin:
    owner: Mapped[UUIDType] = mapped_column(UUID, nullable=False)
    edit_grants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    view_grants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
```

### Permission tables (new pattern)

For permission-based access control, create a per-domain permission table inheriting `BasePermission`:

```python
# uservice/<domain>/models/storage/permission.py

from uservice.database.base import Base
from uservice.base.models.storage.permission import BasePermission

class DomainPermission(Base, BasePermission):
    __tablename__ = "<domain>_permissions"

    resource_id: Mapped[SA_UUID] = mapped_column(
        SA_UUID, ForeignKey("<domain>_info.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
```

### Rules

| ✅ DO | ❌ DON'T |
|-------|---------|
| Use `Mapped[T]` with `mapped_column()` (SQLAlchemy 2.0 style) | Use legacy `Column()` declarations |
| Always set `__tablename__` | Rely on auto-generated table names |
| Use `UUIDMixin` for the primary key | Define `id` manually |
| Use `TimestampMixin` for audit timestamps | Skip timestamps |
| Store enums as `String` in the DB, not as enum columns | Use DB-level enum types |
| Use `JSON` columns for flexible data | Over-normalize with too many tables |
| Name classes the same as their contract counterpart | Use different naming (e.g., `VmModel` vs `VmInfo`) |

### Naming convention

The storage model class should match the contract model class name exactly (e.g., both are `VmInfo`). They live in different packages, so there's no collision. Import aliases resolve ambiguity:

```python
from ..models.contract.vm import VmInfo           # Contract
from ..models.storage.vm import VmInfo as VmStorageInfo  # Storage
```

---

## 3. API Models (`models/api/`)

### Purpose

Optional layer for shapes that exist **only at the HTTP boundary** — typically API-specific request wrappers or response decorations that don't belong in the contract.

### When to use

- You need an input shape that differs from the contract (e.g., a form-like input with different field names).
- You need a response-only shape not covered by the generic wrappers.

### When NOT to use

- In most cases, use contract models directly as request bodies (`VmCreateRequest`).
- The generic response wrappers (`Response[T]`, `PaginatedResponse[T]`, `ResponseWithEtag[T]`) handle output.

### Structure

```
models/api/
├── request/
│   └── <entity>.py     # Optional API-specific request shapes
└── response/
    └── <entity>.py     # Optional API-specific response shapes
```

### Example — API request model (when needed)

```python
# uservice/<domain>/models/api/request/<entity>.py

class EntityCreateRequest:
    name: str
    configuration: dict

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
```

> **Prefer contract models over API models.** Create API models only when the HTTP shape genuinely differs from the contract shape.

---

## Conversion Between Layers

The **facade** is the only place where storage ↔ contract conversion happens.

### Storage → Contract (reads)

```python
return VmInfo.model_validate(storage_object)
```

`model_validate()` works because `base.BaseModel` has `from_attributes=True`.

### Contract → Storage (writes)

```python
new_record = VmStorageInfo(
    name=contract_data.name,
    status=VmStatus.creating,
    configuration=contract_data.configuration.dict()
        if hasattr(contract_data.configuration, "dict")
        else contract_data.configuration,
    ...
)
session.add(new_record)
```

Map fields explicitly. Use `.dict()` or `.model_dump()` for nested Pydantic objects that need to be stored as JSON.
