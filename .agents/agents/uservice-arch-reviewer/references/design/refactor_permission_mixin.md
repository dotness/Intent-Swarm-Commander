# Design Document: PermissionMixin Analysis & Refactor

## 1. Current Implementation Analysis

### What Exists Today

[PermissionMixin](file:///home/remi/Projects/uservice_template/uservice/operation/models/storage/mixin.py#L6-L9) is a 4-line SQLAlchemy mixin:

```python
class PermissionMixin:
    owner: Mapped[UUIDType] = mapped_column(UUID, nullable=False)
    edit_grants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    view_grants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
```

It is used by [OperationInfo](file:///home/remi/Projects/uservice_template/uservice/operation/models/storage/base.py#L10) and consumed in [Operation.create_operation](file:///home/remi/Projects/uservice_template/uservice/operation/facade/operation.py#L81-L100):

```python
new_operation = operation_storage.OperationInfo(
    ...
    owner=self.user.id,
    view_grants=[str(self.user.id)],
)
```

### Rating: 3/10

The mixin captures a reasonable *intent* — co-locating ownership and access grants with the resource — but the execution has significant issues that will cause pain as the service grows.

---

### What's Good

| Aspect | Assessment |
|---|---|
| **Simplicity** | Easy to understand at a glance |
| **Mixin pattern** | Reusable across models via composition — aligns with the existing `UUIDMixin` / `TimestampMixin` conventions |
| **Owner field** | Having a first-class `owner` FK is correct |

---

### What's Wrong

#### 🔴 Critical Issues

| # | Issue | Details |
|---|---|---|
| **C1** | **No enforcement layer** | The mixin stores permission *data* but nothing reads or enforces it. There is no `check_permission()`, no query filter, no middleware. Any facade can `.get()` any resource regardless of grants. The data is write-only decoration. |
| **C2** | **JSON columns are unqueryable** | `edit_grants` and `view_grants` are `JSON` columns containing flat lists of UUID strings. Filtering ("give me all operations I can view") requires database-specific JSON operators (`jsonb @>` in Postgres, nothing portable in SQLite). This kills performance at scale and makes indexing impossible. |
| **C3** | **No type safety** | `Mapped[list]` is untyped — it accepts any JSON-serializable value. There's no validation that the list contains valid UUIDs, nor that they reference existing users. |
| **C4** | **Grants not exposed in contract** | [OperationInfo contract](file:///home/remi/Projects/uservice_template/uservice/operation/models/contract/base.py#L16-L26) only exposes `owner: UUID` — `edit_grants` and `view_grants` are never surfaced to API consumers, making them invisible and unmanageable. |

#### 🟡 Design Issues

| # | Issue | Details |
|---|---|---|
| **D1** | **Fixed permission model** | Only two hard-coded permission levels (`edit`, `view`). Adding `delete`, `admin`, `execute`, or any domain-specific permission requires a schema migration and mixin change. |
| **D2** | **User-only grants** | Grants are lists of user UUIDs. There is no concept of groups, roles, teams, or service accounts. Granting access to a team of 50 users requires 50 entries in the JSON array. |
| **D3** | **No grant management** | There are no facade methods to `grant()`, `revoke()`, or `list_grants()`. The only write path is the initial `create_operation` which hardcodes `view_grants=[str(self.user.id)]` and never sets `edit_grants`. |
| **D4** | **UUID serialization inconsistency** | `owner` stores a native `UUID`, but `view_grants` stores `str(self.user.id)` — string UUIDs inside JSON. This mismatch complicates comparisons. |
| **D5** | **No cascading / inheritance** | Resource hierarchies (e.g., a resource and its child operations) don't share permissions. Each record is an island. |

---

## 2. Proposed Refactor Design

### Goals

1. **Enforce permissions** — queries should automatically scope to what the user can access
2. **Queryable & indexable** — use relational tables, not JSON blobs
3. **Extensible** — new permission types without schema migrations
4. **Group/role support** — grant to principals (users, groups, service-accounts)
5. **Consistent with existing patterns** — still a mixin, still uses `DomainFacade`

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     API / FastAPI Layer                       │
│  Depends(authenticate_user) → Depends(get_current_user)      │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                  DomainFacade (base)                          │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  PermissionEnforcer                                    │   │
│  │  - scoped_query(model, action) → filtered query        │   │
│  │  - check_access(resource, action) → bool / raise       │   │
│  │  - grant(resource, principal, action)                   │   │
│  │  - revoke(resource, principal, action)                  │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│              Database — Relational Permission Tables          │
│                                                               │
│  ┌──────────────────┐    ┌─────────────────────────────┐     │
│  │ resource_table    │    │ resource_permissions         │     │
│  │ (has owner_id)    │◄───│  resource_id  (FK)           │     │
│  └──────────────────┘    │  resource_type (str)          │     │
│                           │  principal_id (UUID)          │     │
│                           │  principal_type (enum)        │     │
│                           │  action (enum/str)            │     │
│                           │  granted_by (UUID)            │     │
│                           │  granted_at (datetime)        │     │
│                           └─────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.1 New Storage Models

#### `uservice/base/models/storage/permission.py` [NEW]

```python
from enum import Enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import String, UUID as SA_UUID, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from uservice.database.base import Base, UUIDMixin


class PrincipalType(str, Enum):
    """Who is receiving the grant."""
    user = "user"
    group = "group"
    service_account = "service_account"


class Action(str, Enum):
    """
    Baseline actions. Domain-specific actions can be added
    without a migration by using the `custom` value + a
    `custom_action` string column, or by extending this enum
    and running a lightweight ALTER.
    """
    view = "view"
    edit = "edit"
    delete = "delete"
    admin = "admin"


class ResourcePermission(Base, UUIDMixin):
    """
    A single grant: "principal X can perform action Y on resource Z".
    Replaces the JSON columns in PermissionMixin.
    """
    __tablename__ = "resource_permissions"

    # What resource
    resource_id: Mapped[UUID] = mapped_column(SA_UUID, nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(255), nullable=False)

    # Who
    principal_id: Mapped[UUID] = mapped_column(SA_UUID, nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=PrincipalType.user.value
    )

    # What action
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    # Audit
    granted_by: Mapped[UUID] = mapped_column(SA_UUID, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "resource_id", "principal_id", "action",
            name="uq_resource_principal_action",
        ),
        Index("ix_perm_lookup", "resource_id", "action"),
        Index("ix_perm_principal", "principal_id", "action"),
    )
```

> [!NOTE]
> `resource_type` is a discriminator string (e.g. `"operation_info"`, `"vm"`) so a single
> permissions table serves all domain models. Alternatively, each domain can have its own
> permissions table — but a shared table is simpler for cross-cutting queries like
> "show me everything user X can access".

#### `uservice/base/models/storage/owner_mixin.py` [NEW]

The mixin is slimmed down to just ownership. Grants move to the relational table.

```python
from sqlalchemy import UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID as UUIDType


class OwnerMixin:
    """Tracks who created/owns a resource. Access grants are in ResourcePermission."""
    owner_id: Mapped[UUIDType] = mapped_column(UUID, nullable=False, index=True)
```

---

### 2.2 Permission Enforcer Service

#### `uservice/base/services/permission.py` [NEW]

A service class that facades consume for all permission operations.

```python
from uuid import UUID
from sqlalchemy import select, and_, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from uservice.base.models.storage.permission import (
    ResourcePermission, Action, PrincipalType,
)


class AccessDenied(Exception):
    """Raised when a principal lacks the required permission."""
    ...


class PermissionService:
    """
    Centralised permission enforcement.
    Injected into DomainFacade so every domain gets consistent authz.
    """

    def __init__(self, session: AsyncSession, user_id: UUID):
        self._session = session
        self._user_id = user_id

    # ── Enforcement ────────────────────────────────────────────

    async def check_access(
        self,
        resource_id: UUID,
        resource_type: str,
        action: Action | str,
        *,
        owner_id: UUID | None = None,
    ) -> bool:
        """
        Returns True if the current user can perform `action` on `resource_id`.
        Owners implicitly have all permissions.
        """
        if owner_id is not None and owner_id == self._user_id:
            return True

        action_value = action.value if isinstance(action, Action) else action

        query = select(ResourcePermission.id).where(
            and_(
                ResourcePermission.resource_id == resource_id,
                ResourcePermission.resource_type == resource_type,
                ResourcePermission.principal_id == self._user_id,
                ResourcePermission.action == action_value,
            )
        ).limit(1)

        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None

    async def require_access(
        self,
        resource_id: UUID,
        resource_type: str,
        action: Action | str,
        *,
        owner_id: UUID | None = None,
    ) -> None:
        """Like check_access but raises AccessDenied on failure."""
        if not await self.check_access(
            resource_id, resource_type, action, owner_id=owner_id
        ):
            raise AccessDenied(
                f"User {self._user_id} lacks '{action}' on {resource_type}/{resource_id}"
            )

    def scoped_query(self, model, action: Action | str):
        """
        Returns a subquery filter that can be composed into any SELECT
        to restrict results to resources the current user can access.

        Usage:
            query = select(OperationInfo).where(
                permissions.scoped_query(OperationInfo, Action.view)
            )
        """
        action_value = action.value if isinstance(action, Action) else action

        return model.id.in_(
            select(ResourcePermission.resource_id).where(
                and_(
                    ResourcePermission.principal_id == self._user_id,
                    ResourcePermission.action == action_value,
                    ResourcePermission.resource_type == model.__tablename__,
                )
            )
        ) | (model.owner_id == self._user_id)

    # ── Grant management ───────────────────────────────────────

    async def grant(
        self,
        resource_id: UUID,
        resource_type: str,
        principal_id: UUID,
        action: Action | str,
        *,
        principal_type: PrincipalType = PrincipalType.user,
    ) -> ResourcePermission:
        action_value = action.value if isinstance(action, Action) else action

        perm = ResourcePermission(
            resource_id=resource_id,
            resource_type=resource_type,
            principal_id=principal_id,
            principal_type=principal_type.value,
            action=action_value,
            granted_by=self._user_id,
        )
        self._session.add(perm)
        await self._session.flush()
        return perm

    async def revoke(
        self,
        resource_id: UUID,
        principal_id: UUID,
        action: Action | str,
    ) -> None:
        action_value = action.value if isinstance(action, Action) else action

        stmt = sa_delete(ResourcePermission).where(
            and_(
                ResourcePermission.resource_id == resource_id,
                ResourcePermission.principal_id == principal_id,
                ResourcePermission.action == action_value,
            )
        )
        await self._session.execute(stmt)

    async def bulk_grant_defaults(
        self,
        resource_id: UUID,
        resource_type: str,
        owner_id: UUID,
    ) -> None:
        """
        Auto-grants the owner view + edit + delete + admin on resource creation.
        Called from create_* facade methods.
        """
        for action in (Action.view, Action.edit, Action.delete, Action.admin):
            await self.grant(
                resource_id=resource_id,
                resource_type=resource_type,
                principal_id=owner_id,
                action=action,
            )
```

---

### 2.3 DomainFacade Integration

#### [MODIFY] [base.py](file:///home/remi/Projects/uservice_template/uservice/base/facade/base.py)

Add a `permissions` property so every domain facade gets access enforcement for free.

```diff
 class DomainFacade:
     user: user_contract.UserInfo
     _session = None
+    _permissions = None

     @property
     def session(self):
         if self._session is None:
             raise RuntimeError("Database session not initialized.")
         return self._session

     @session.setter
     def session(self, value):
         self._session = value
+        # Auto-initialise permission service when session is set
+        from uservice.base.services.permission import PermissionService
+        self._permissions = PermissionService(session=value, user_id=self.user.id)
+
+    @property
+    def permissions(self) -> "PermissionService":
+        if self._permissions is None:
+            raise RuntimeError("Permissions not initialized. Set session first.")
+        return self._permissions
```

---

### 2.4 Facade Usage (Before → After)

#### [MODIFY] [operation.py](file:///home/remi/Projects/uservice_template/uservice/operation/facade/operation.py)

```diff
 async def create_operation(self, ...):
     new_operation = operation_storage.OperationInfo(
         type=operation_type,
         status=operation_contract.OperationStatus.created,
         configuration=configuration,
         resource_id=resource_id,
-        owner=self.user.id,
-        view_grants=[str(self.user.id)],
+        owner_id=self.user.id,
     )
     self.session.add(new_operation)
     await self.session.commit()
     await self.session.refresh(new_operation)
+
+    # Grant default permissions (view, edit, delete, admin)
+    await self.permissions.bulk_grant_defaults(
+        resource_id=new_operation.id,
+        resource_type="operation_info",
+        owner_id=self.user.id,
+    )
+    await self.session.commit()
+
     return operation_contract.OperationInfo.model_validate(new_operation)

 async def get_operation_info(self, operation_id: UUID):
-    query = select(operation_storage.OperationInfo).where(
-        operation_storage.OperationInfo.id == operation_id
-    )
+    query = select(operation_storage.OperationInfo).where(
+        operation_storage.OperationInfo.id == operation_id,
+        self.permissions.scoped_query(operation_storage.OperationInfo, Action.view),
+    )
     ...
```

---

### 2.5 Migration Strategy

This refactor touches the DB schema. Proposed migration approach:

| Step | Action | Risk |
|---|---|---|
| **1** | Create `resource_permissions` table (Alembic migration) | Low — additive |
| **2** | Add `owner_id` column to `operation_info` (nullable initially) | Low — additive |
| **3** | Data migration: copy `owner` → `owner_id`, explode `view_grants`/`edit_grants` JSON into `resource_permissions` rows | Medium — needs careful testing |
| **4** | Drop `owner`, `edit_grants`, `view_grants` columns | Medium — breaking if anything still reads them |
| **5** | Rename `owner_id` to be non-nullable | Low |
| **6** | Delete [mixin.py](file:///home/remi/Projects/uservice_template/uservice/operation/models/storage/mixin.py) | Low |

> [!IMPORTANT]
> Steps 3-4 should be a single release behind a feature flag or at minimum a coordinated deploy.
> If any consumer reads `edit_grants`/`view_grants` directly, step 4 is a breaking change.

---

### 2.6 Contract Model Updates

#### [MODIFY] [base.py](file:///home/remi/Projects/uservice_template/uservice/operation/models/contract/base.py)

```diff
 class OperationInfo(base.BaseModel):
     id: UUID
     resource_id: UUID
-    owner: UUID
+    owner_id: UUID
     type: str
     status: OperationStatus
     created_at: datetime
     updated_at: Optional[datetime] = None
     finished_at: Optional[datetime] = None
+    permissions: Optional[list["PermissionGrant"]] = None
+
+
+class PermissionGrant(base.BaseModel):
+    principal_id: UUID
+    principal_type: str
+    action: str
```

---

## 3. File Change Summary

| File | Action | Purpose |
|---|---|---|
| `uservice/base/models/storage/permission.py` | **NEW** | `ResourcePermission` table + enums |
| `uservice/base/models/storage/owner_mixin.py` | **NEW** | Slim `OwnerMixin` (just `owner_id`) |
| `uservice/base/services/permission.py` | **NEW** | `PermissionService` (check, grant, revoke, scoped_query) |
| `uservice/base/facade/base.py` | **MODIFY** | Wire `PermissionService` into `DomainFacade` |
| `uservice/operation/models/storage/base.py` | **MODIFY** | Replace `PermissionMixin` with `OwnerMixin` |
| `uservice/operation/models/storage/mixin.py` | **DELETE** | Superseded by `OwnerMixin` + `ResourcePermission` |
| `uservice/operation/models/contract/base.py` | **MODIFY** | `owner` → `owner_id`, add `permissions` field |
| `uservice/operation/facade/operation.py` | **MODIFY** | Use `PermissionService` for grants + scoped queries |
| Alembic migration | **NEW** | Schema migration for `resource_permissions` table |

---

## 4. Testing Strategy

### Unit Tests
- `PermissionService.check_access` — owner bypass, explicit grant, missing grant
- `PermissionService.scoped_query` — returns only accessible resources
- `PermissionService.grant` / `revoke` — idempotent, unique constraint handling
- `PermissionService.bulk_grant_defaults` — creates 4 grants for owner

### Integration Tests
- `Operation.create_operation` → verify `resource_permissions` rows are created
- `Operation.get_operation_info` → verify non-owner without grants gets `AccessDenied`
- `Operation.get_operation_info` → verify grantee can access

### Data Migration Tests
- Seed DB with old-schema rows (JSON grants) → run migration → verify `resource_permissions` are correct

---

## 5. Open Questions

> [!IMPORTANT]
> **Q1: Shared vs. per-domain permission tables?**
> The design above uses a single `resource_permissions` table with a `resource_type` discriminator. An alternative is one permission table per domain (e.g. `operation_permissions`, `vm_permissions`). Single table is simpler for cross-cutting queries; per-domain allows FK constraints. Which do you prefer?

> [!IMPORTANT]
> **Q2: Group/team support scope.**
> The `PrincipalType` enum includes `group` and `service_account`. Should groups be modeled now (requires a `groups` + `group_members` table) or deferred to a follow-up?

> [!WARNING]
> **Q3: Backward compatibility.**
> Are there any external consumers (other services, scripts, CI jobs) that read `edit_grants` / `view_grants` JSON columns directly from the database? If so, we need a compatibility shim during migration.
