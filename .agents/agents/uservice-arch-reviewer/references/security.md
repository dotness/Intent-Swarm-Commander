# Security & Authentication

> **Location**: `uservice/security/`
> **Responsibility**: JWT-based authentication, user context propagation via `ContextVar`, and the security middleware pipeline.

---

## Authentication Flow

```
  Client Request
       │
       ▼
  ┌──────────────────────┐
  │ OAuth2PasswordBearer  │  Extracts Bearer token from header
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │   authenticate_user   │  Decodes JWT, looks up user in DB
  │   (FastAPI Depend)    │
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │  ContextVar set       │  _user_info_ctx_var.set(user)
  │  (user available      │
  │   throughout request) │
  └──────────┬───────────┘
             ▼
         Route Handler
```

### Global auth dependency

Auth is applied globally at the `FastAPI` app level:

```python
app = FastAPI(
    dependencies=[Depends(authenticate.authenticate_user)],
)
```

Every request goes through `authenticate_user` before reaching any route.

---

## JWT Scheme

Defined in `uservice/security/scheme.py`:

```python
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ALGORITHM = "HS256"
```

| Config | Value |
|--------|-------|
| Token type | Bearer (OAuth2) |
| Algorithm | HS256 |
| Expiry | 30 minutes |
| Token URL | `/token` |

### Creating tokens

```python
from uservice.security.scheme import create_token_for_user

token = create_token_for_user(username="admin")
# Returns: Token(access_token="...", token_type="bearer")
```

---

## User Context (`ContextVar`)

The authenticated user is stored in a `ContextVar` and can be retrieved anywhere in the request lifecycle:

```python
from uservice.security import get_current_user_info

# In any route or facade
user = get_current_user_info()  # Returns UserInfo or None
```

### How it works

```python
# uservice/security/middleware/authenticate.py

_user_info_ctx_var: ContextVar[Union[UserInfo, None]] = ContextVar("user_info", default=None)

async def authenticate_user(token, session):
    # 1. Decode JWT
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    username = payload.get("sub")

    # 2. Look up user via User facade
    user_fac = user_facade.User()
    user_fac.session = session
    user = await user_fac.get_user_info(username=username)

    # 3. Set ContextVar (scoped to this request)
    user_set_id = _user_info_ctx_var.set(user)
    yield user
    _user_info_ctx_var.reset(user_set_id)
```

### Rules

| ✅ DO | ❌ DON'T |
|-------|---------|
| Use `get_current_user_info()` in routes | Pass user through function params from the route |
| Pass `UserInfo` to facades via `create(user=user)` | Re-authenticate inside facades |
| Handle `None` return from `get_current_user_info()` in non-auth contexts | Assume it's always set |

---

## Request Context Middleware

Defined in `uservice/base/middleware/request_info.py`:

```python
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Captures: self-link, path, offset, limit, query_params
        request_id = _request_info_ctx_var.set(RequestInfo(...))
        response = await call_next(request)
        _request_info_ctx_var.reset(request_id)
        return response
```

Access anywhere via:

```python
from uservice.base.middleware.request_info import get_request_info

request_info = get_request_info()
# request_info.self    → full URL with query
# request_info.path    → path only
# request_info.offset  → int or None
# request_info.limit   → int or None
# request_info.query_params → dict
```

---

## Secrets Management

All sensitive configuration is loaded from files using `pydantic-settings`:

```python
# uservice/secrets.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class SqlDatabase(BaseSettings):
    model_config = SettingsConfigDict(secrets_dir='<path>/database/sql')
    username: str
    password: str
    url: str

SQL_DATABASE_SECRETS = SqlDatabase()
```

### Secret directory layout

```
secrets/
├── database/
│   ├── sql/
│   │   ├── username
│   │   ├── password
│   │   └── url
│   └── mongo/
│       ├── username
│       ├── password
│       ├── host
│       ├── port
│       ├── parameters
│       └── database
└── queue/
    └── temporal/
        ├── username
        ├── password
        ├── host
        └── port
```

Each file contains the raw secret value (no quotes, no newline). This pattern is compatible with Docker/Kubernetes secret mounts.

### Rules

| ✅ DO | ❌ DON'T |
|-------|---------|
| Define secrets as `pydantic_settings.BaseSettings` | Hard-code connection strings |
| Use `SettingsConfigDict(secrets_dir=...)` | Read from env vars directly for DB credentials |
| Load secrets once at module level | Re-read secrets on every request |
| Keep actual secrets out of version control | Commit the `secrets/` directory with real values |
