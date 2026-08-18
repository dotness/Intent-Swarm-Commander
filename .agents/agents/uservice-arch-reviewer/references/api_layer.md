# API Layer — Patterns & Rules

> **Location**: `uservice/<domain>/api/<entity>.py`
> **Responsibility**: HTTP endpoint definitions. Thin glue between HTTP and the Facade.

---

## Router Setup

Each domain entity gets its own `APIRouter`. Routers are registered in `uservice/api.py` via `register_domain_apis()`.

```python
# uservice/<domain>/api/<entity>.py
from fastapi import APIRouter, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uservice.database.engine import get_db

router = APIRouter()
```

### Registering a new domain router

```python
# uservice/api.py  →  register_domain_apis()
def register_domain_apis():
    try:
        from uservice.<domain>.api import <entity>
        app.include_router(<entity>.router)
    except ImportError as e:
        print(f"Warning: Could not load some APIs: {e}")
```

Always wrap imports in `try/except ImportError` so that missing optional domains don't crash the whole service.

---

## Route Design Rules

### 1. URL pattern

Use nested resource paths scoped to their parent:

```
/api/<parent_plural>/{parent_id}/<entity_plural>           # list / create
/api/<parent_plural>/{parent_id}/<entity_plural>/{entity_id}  # get / update / delete
```

**Real example**:
```
POST   /api/federations/{federation_name}/vms        → create_vm
GET    /api/federations/{federation_name}/vms         → get_vm_list
GET    /api/federations/{federation_name}/vms/{vm_id} → get_vm
PUT    /api/federations/{federation_name}/vms/{vm_id} → update_vm
DELETE /api/federations/{federation_name}/vms/{vm_id} → delete_vm
```

### 2. Status codes

| Operation | Status | Reason |
|-----------|--------|--------|
| Create (async) | `202 Accepted` | Work is scheduled, not yet done |
| Read single | `200 OK` | — |
| Read list | `200 OK` | — |
| Update (async) | `202 Accepted` | Workflow scheduled |
| Delete (async) | `202 Accepted` | Workflow scheduled |

### 3. Return type annotations

Always annotate returns using the generic response wrappers from `uservice.base.models.api.response`:

```python
from uservice.base.models.api import response as api_response

async def get_vm(...) -> api_response.ResponseWithEtag[vm_contract.VmInfo]:
    ...

async def get_vm_list(...) -> api_response.PaginatedResponse[vm_contract.VmInfo]:
    ...

async def create_vm(...) -> api_response.Response[operation_contract.OperationInfo]:
    ...
```

---

## Input Handling

### Path parameters

- Path parameters appear in the route decorator and function signature.
- Use `str` for names, `UUID` for identifiers.
- FastAPI auto-validates them.

### Request body (create / update)

- Import the **contract model** (Pydantic) directly as the body type.
- The contract model (`VmCreateRequest`, `VmUpdateRequest`) validates input.

```python
from uservice.<domain>.models.contract import <entity> as <entity>_contract

@router.post("/api/...", status_code=202)
async def create_entity(
    parent_id: str,
    data: <entity>_contract.EntityCreateRequest,
    session: AsyncSession = Depends(get_db)
) -> api_response.Response[operation_contract.OperationInfo]:
```

### Query parameters (list endpoints)

- Declare optional query params as function arguments with defaults.
- For `offset` and `limit`, prefer reading from `request_info` middleware for consistency.

```python
from uservice.base.middleware.request_info import get_request_info

@router.get("/api/.../vms", status_code=200)
async def get_vm_list(
    federation_name: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
) -> api_response.PaginatedResponse[vm_contract.VmInfo]:
    request_info = get_request_info()
    # Use request_info.offset, request_info.limit
```

---

## Output Handling

### Response wrappers

The API always returns data wrapped in one of these generic envelopes (from `uservice.base.models.api.response`):

| Wrapper | Fields | Use case |
|---------|--------|----------|
| `Response[T]` | `meta.response_at`, `data: T` | Single-object responses |
| `ResponseWithEtag[T]` | `meta.etag`, `meta.response_at`, `data: T` | Single-object with caching |
| `PaginatedResponse[T]` | `meta`, `count`, `data: list[T]`, `links: {self, next, prev}` | List endpoints |

### Creating responses

Use the class-method factory `await Wrapper.create(data=...)`:

```python
# Single
return await api_response.Response[contract.Info].create(data=info)

# With ETag
response_data = await api_response.ResponseWithEtag[contract.Info].create(data=info)
response.headers["ETag"] = response_data.meta.etag
return response_data

# Paginated
return await api_response.PaginatedResponse[contract.Info].create(
    data=[contract.Info.model_validate(item) for item in items],
    count=total_count,
)
```

### The `data` field always contains contract models

Never return storage models or raw dicts. Always `model_validate` storage objects into contract models.

---

## Endpoint Implementation Pattern

Every endpoint follows this exact sequence:

```python
@router.post("/api/...", status_code=202)
async def create_entity(
    parent_name: str,
    data: contract.CreateRequest,
    session: AsyncSession = Depends(get_db)
) -> api_response.Response[operation_contract.OperationInfo]:
    # 1. Get authenticated user from ContextVar
    user = get_current_user_info()

    # 2. Instantiate domain facade (async factory)
    facade = await DomainFacade.create(user=user)

    # 3. Inject the DB session
    facade.session = session

    # 4. Delegate ALL logic to the facade
    try:
        operation_info = await facade.schedule_create(...)
    except ResourceDoesNotExist:
        raise base_exception.HTTP_404_NOT_FOUND

    # 5. Wrap result in response envelope and return
    return await api_response.Response[operation_contract.OperationInfo].create(
        data=operation_info
    )
```

### Rules for API functions

| ✅ DO | ❌ DON'T |
|-------|---------|
| Get `user` from `get_current_user_info()` | Hard-code user or read from headers |
| Get session via `Depends(get_db)` | Create sessions manually |
| Delegate to facade | Write SQLAlchemy queries in the route |
| Catch `ResourceDoesNotExist` → 404 | Return raw exceptions to the client |
| Use response wrappers | Return plain dicts |
| Annotate return types | Leave return types untyped |

---

## Error Handling

Use pre-built HTTP exception constants from `uservice.base.api.exception`:

```python
from uservice.base.api import exception as base_exception
from uservice.base.facade.base import ResourceDoesNotExist

try:
    result = await facade.get_entity(...)
except ResourceDoesNotExist:
    raise base_exception.HTTP_404_NOT_FOUND
```

Add new exception constants in `base/api/exception.py` as needed:

```python
HTTP_409_CONFLICT = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict")
```

---

## Database Session Lifecycle

Sessions are **injected via FastAPI dependency** and scoped to the request:

```python
from uservice.database.engine import get_db

async def my_endpoint(session: AsyncSession = Depends(get_db)):
    facade.session = session  # Pass to facade
```

The `get_db` dependency yields a session and ensures it's closed after the request, even on error. **Never commit or close the session in the route handler** — that's the facade's responsibility.
