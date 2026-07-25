# Facades — Coarse-Grained DDD Business Facades

> **Location**: `uservice/<domain>/facade/<entity>.py`
> **Responsibility**: ALL business logic, data access, permission checks, cross-domain orchestration, and agent tool exposure.

---

## The `DomainFacade` Base Class

Every domain facade inherits from `uservice.base.facade.base.DomainFacade`.

```python
# uservice/base/facade/base.py (simplified)

class DomainFacade:
    user: UserInfo         # Authenticated user context
    _session = None        # SQLAlchemy async session

    @classmethod
    async def create(cls, user: Union[str, UserInfo]) -> Self:
        """Async factory. Accepts a UserInfo object or a username string."""
        ...

    @property
    def session(self) -> AsyncSession:
        """Raises RuntimeError if not set."""
        ...

    @session.setter
    def session(self, value): ...

    def get_permission_service(self, permission_model):
        """Returns a PermissionService bound to session + user."""
        ...
```

### Key features

| Feature | Detail |
|---------|--------|
| **Async factory** | `await Facade.create(user=user)` — resolves username to `UserInfo` if needed. |
| **Session injection** | Session is set AFTER `create()`: `facade.session = session`. |
| **Permission service** | `self.get_permission_service(PermissionModel)` — returns a bound `PermissionService`. |
| **User context** | `self.user` is always a `UserInfo` contract model. |

---

## Creating a Domain Facade

### Step 1: Inherit and init

```python
from uservice.base.facade.base import DomainFacade, ResourceDoesNotExist

class MyEntity(DomainFacade):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = None
```

### Step 2: Add session property (standard pattern)

```python
    @property
    def session(self):
        if self._session is None:
            raise RuntimeError("Database session not initialized.")
        return self._session

    @session.setter
    def session(self, value):
        self._session = value
```

### Step 3: Implement CRUD methods

```python
    async def create_entity(self, parent_name: str, data: CreateRequest) -> EntityInfo:
        """Create a new entity record in the database."""
        # 1. Cross-domain lookup (through another facade)
        parent_facade = await ParentFacade.create(user=self.user)
        parent_facade.session = self.session
        parent_info = await parent_facade.get_parent(name=parent_name)

        # 2. Build storage model
        new_record = EntityStorageInfo(
            name=data.name,
            parent_id=parent_info.id,
            status=EntityStatus.creating,
            owner=self.user.id,
            ...
        )

        # 3. Persist
        self.session.add(new_record)
        await self.session.commit()
        await self.session.refresh(new_record)

        # 4. Return as contract model
        return EntityInfo.model_validate(new_record)
```

---

## Facade Method Categories

A complete domain facade implements these method categories:

### 1. Direct CRUD (synchronous DB operations)

| Method | Purpose | Returns |
|--------|---------|---------|
| `create_entity(...)` | Insert a record | `EntityInfo` (contract) |
| `get_entity(...)` | Read one by ID | `EntityInfo` |
| `get_entity_list(...)` | Read many with filters | `list[EntityInfo]` |
| `get_count(...)` | Count with filters | `int` |
| `update_entity(...)` | Update fields | `EntityInfo` |
| `delete_entity(...)` | Soft delete / mark status | `None` |

### 2. Workflow schedulers (async operation launchers)

| Method | Purpose | Returns |
|--------|---------|---------|
| `schedule_create_entity(...)` | Creates record + schedules Temporal workflow | `OperationInfo` |
| `schedule_update_entity(...)` | Verifies existence + schedules update workflow | `OperationInfo` |
| `schedule_delete_entity(...)` | Verifies existence + schedules delete workflow | `OperationInfo` |

```python
    async def schedule_create_entity(self, ...) -> OperationInfo:
        from uservice.base.operations.base import WorkflowMetadata
        from uservice.<domain>.operations.create import CreateEntity

        # Create the DB record first
        entity_info = await self.create_entity(...)

        # Build workflow metadata
        metadata = WorkflowMetadata(
            resource_id=entity_info.id,
            username=self.user.name
        )

        # Submit to Temporal
        return await CreateEntity.create(metadata=metadata, data=entity_info.dict())
```

### 3. ADK Tool wrappers (agent-callable methods)

```python
    @property
    def exposed_tools(self) -> List[callable]:
        """Expose facade methods as ADK-compatible tools."""
        return [self.create_entity_tool, self.update_entity_tool, self.delete_entity_tool]

    async def create_entity_tool(self, name: str, ...) -> str:
        """Create a new entity.
        Args:
            name: Name of the entity
            ...
        """
        data = CreateRequest(name=name, ...)
        info = await self.create_entity(data=data)
        return f"Successfully created entity with ID: {info.id}"
```

**Tool method rules**:
- Return `str` (human-readable result for the agent).
- Use simple primitive types in the signature (agents can't construct Pydantic objects).
- Include a proper docstring with `Args:` — the ADK reads this.
- Internally delegate to the corresponding CRUD method.

---

## Permission Checking

### Using `PermissionService`

```python
    @property
    def permissions(self):
        if not hasattr(self, "_permissions") or self._permissions is None:
            self._permissions = self.get_permission_service(DomainPermission)
        return self._permissions
```

Then in methods:

```python
    # Require access (raises AccessDenied if denied)
    await self.permissions.require_access(resource_id, Action.view)

    # Check access (returns bool)
    has_access = await self.permissions.check_access(resource_id, Action.edit)

    # Scope a query to visible resources
    query = select(StorageModel).where(
        self.permissions.scoped_query(StorageModel, Action.view)
    )

    # Grant permissions on creation
    await self.permissions.bulk_grant_defaults(
        resource_id=new_record.id,
        owner_id=self.user.id,
    )
```

### Legacy permission pattern (JSON columns)

Some domains still use `view_grants` / `edit_grants` JSON columns directly:

```python
    # Check view_grants permission
    if str(self.user.id) not in storage_record.view_grants:
        raise ResourceDoesNotExist(f"Entity by id: '{entity_id}' does not exist.")
```

> **Prefer the `PermissionService` pattern** for new domains. Use `BasePermission` + per-domain permission tables.

---

## Cross-Domain Communication

Facades call other facades — **never** other domain's storage models directly.

```python
    async def create_vm(self, federation_name: str, vm_data: VmCreateRequest) -> VmInfo:
        # Cross-domain call through the Federation facade
        from uservice.federation.facade.federation import Federation

        federation_instance = await Federation.create(user=self.user)
        federation_instance.session = self.session  # Share the same session
        federation_info = await federation_instance.get_federation(name=federation_name)
        ...
```

### Rules for cross-domain calls

| ✅ DO | ❌ DON'T |
|-------|---------|
| Import and call another domain's facade | Write SQL queries against another domain's tables |
| Pass `self.user` to the other facade | Create a new user context |
| Share `self.session` with the other facade | Create a new session for cross-domain calls |
| Use `from_attributes=True` for conversions | Copy data field-by-field with manual dicts |

---

## Exception Handling

```python
from uservice.base.facade.base import ResourceDoesNotExist
from sqlalchemy.exc import NoResultFound, MultipleResultsFound

    async def get_entity(self, entity_id: UUID) -> EntityInfo:
        try:
            result = await self.session.execute(query)
            record = result.scalar_one()
        except (NoResultFound, MultipleResultsFound):
            raise ResourceDoesNotExist(f"Entity by id: '{entity_id}' does not exist.")
```

- **Always catch** `NoResultFound` and `MultipleResultsFound`.
- **Always raise** `ResourceDoesNotExist` with a descriptive message.
- The API layer translates this to HTTP 404.

---

## Query Patterns

### Single entity

```python
from sqlalchemy import select, and_

query = select(StorageModel).where(
    and_(
        StorageModel.id == entity_id,
        StorageModel.parent_id == parent_info.id,
    )
)
result = await self.session.execute(query)
record = result.scalar_one()
```

### List with pagination and filters

```python
query = (
    select(StorageModel)
    .where(StorageModel.parent_id == parent_info.id)
    .limit(limit)
    .offset(offset)
    .order_by(StorageModel.created_at)
)

# Dynamic filters
if filters.get("status"):
    query = query.where(StorageModel.status == filters["status"])

result = await self.session.execute(query)
records = result.scalars().all()
```

### Count

```python
from sqlalchemy import func

query = select(func.count(StorageModel.id)).where(...)
result = await self.session.execute(query)
total = result.scalar()
```

---

## Complete Facade Skeleton

```python
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from uservice.base.facade.base import DomainFacade, ResourceDoesNotExist
from sqlalchemy.exc import NoResultFound, MultipleResultsFound
from sqlalchemy import select, and_, func

from ..models.contract.<entity> import (
    EntityInfo, EntityStatus, EntityCreateRequest, EntityUpdateRequest,
)
from ..models.storage.<entity> import EntityInfo as EntityStorageInfo
from uservice.operation.models.contract import base as operation_contract


DEFAULT_LIMIT = 50


class Entity(DomainFacade):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = None

    @property
    def session(self):
        if self._session is None:
            raise RuntimeError("Database session not initialized.")
        return self._session

    @session.setter
    def session(self, value):
        self._session = value

    # ── Workflow schedulers ────────────────────────
    async def schedule_create_entity(self, ...) -> operation_contract.OperationInfo: ...
    async def schedule_update_entity(self, ...) -> operation_contract.OperationInfo: ...
    async def schedule_delete_entity(self, ...) -> operation_contract.OperationInfo: ...

    # ── ADK tool wrappers ──────────────────────────
    @property
    def exposed_tools(self) -> List[callable]:
        return [self.create_entity_tool, self.update_entity_tool, self.delete_entity_tool]

    async def create_entity_tool(self, ...) -> str: ...
    async def update_entity_tool(self, ...) -> str: ...
    async def delete_entity_tool(self, ...) -> str: ...

    # ── CRUD ───────────────────────────────────────
    async def create_entity(self, ...) -> EntityInfo: ...
    async def get_entity(self, ...) -> EntityInfo: ...
    async def update_entity(self, ...) -> EntityInfo: ...
    async def delete_entity(self, ...) -> None: ...
    async def get_entity_list(self, ...) -> List[EntityInfo]: ...
    async def get_count(self, ...) -> int: ...
```
