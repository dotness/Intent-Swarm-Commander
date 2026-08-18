# Intent Swarm Commander - Architecture Review

## Overview
As the `uservice-arch-reviewer` agent, I have reviewed the `src/uservice` codebase against the structural patterns and rules defined in the `uservice-template` documentation.

Overall, the current implementation (specifically the `smeac`, `swarm`, and `hitl` domains) acts primarily as an early-stage MVP or Proof-of-Concept, bypassing the strict architectural constraints of the `uservice-template`.

Below are the detailed findings categorized by architectural layer, outlining the violations and providing concrete recommendations to align the codebase with the required patterns.

---

## 1. Facades and Layered Architecture
> **Rule**: All domain business logic, data access, and orchestration must be encapsulated inside `DomainFacade` objects. API routes must be thin and only delegate to facades.

### Violations
- **Missing Facades:** The `smeac/facade/__init__.py`, `swarm/facade/__init__.py`, and `hitl/facade/__init__.py` directories are either empty or contain functions instead of `DomainFacade` classes.
- **API Business Logic:** In `smeac/api/routes.py`, the `submit_smeac_order` endpoint handles business logic directly (building the order dictionary, storing it in an in-memory `_orders` dict).
- **Direct Workflow Invocation:** In `smeac/api/routes.py`, `start_workflow()` is called directly from the HTTP route. The template dictates that Temporal workflows must be scheduled via `facade.schedule_create_entity(...)` which first persists the entity state to the DB and then launches the workflow via an Operation wrapper.

### Required Actions
- Create robust `SmeacFacade`, `SwarmFacade`, and `HitlFacade` classes extending `uservice.base.facade.base.DomainFacade`.
- Move the state manipulation logic and workflow launching out of `api/routes.py` and into the new facade classes.

---

## 2. API Layer & Response Envelopes
> **Rule**: API endpoints must return data wrapped in generic response envelopes (`Response[T]`, `PaginatedResponse[T]`). Database sessions (`AsyncSession`) and User Context must be injected.

### Violations
- **Raw Responses:** Endpoints in `smeac`, `swarm`, and `hitl` return raw Pydantic models (e.g., `SmeacOrderResponse`, `SwarmResponse`) instead of using `api_response.Response[T].create(data=...)` and `api_response.PaginatedResponse[T]`.
- **Missing Session Dependencies:** Routes do not inject the database session (`session: AsyncSession = Depends(get_db)`). They bypass DB transactions altogether or rely on global in-memory maps.
- **Hardcoded Context:** User identity is hardcoded as `"commander-default"` in multiple places (e.g., `smeac/api/routes.py:52`) instead of retrieving the authenticated user via `get_current_user_info()` from the ContextVar.
- **Error Handling:** Endpoints return manual `HTTPException(status_code=404)` instead of catching `ResourceDoesNotExist` thrown by the facade and raising predefined constants like `base_exception.HTTP_404_NOT_FOUND`.

### Required Actions
- Update all router endpoint signatures to inject the `AsyncSession`.
- Fetch `user = get_current_user_info()` in each route, pass it to the facade via `await DomainFacade.create(user=user)`, and inject the `session`.
- Refactor all `return` statements to use `uservice.base.models.api.response` envelopes.

---

## 3. Models (API, Contract, Storage)
> **Rule**: Strict separation between API (HTTP boundaries), Contract (Domain DTOs, pure Pydantic), and Storage (SQLAlchemy ORM).

### Violations
- **Flattened/Mixed Directory Structure:** The `smeac/models/` directory mixes SQLAlchemy models (`smeac.py`) and Pydantic schemas (`schemas.py`). They must be split into `smeac/models/contract/` and `smeac/models/storage/`.
- **Contract Base Classes:** Contract schemas like `SmeacOrderCreateRequest` inherit directly from `pydantic.BaseModel` rather than the required `uservice.base.models.api.base.BaseModel` which configures `from_attributes=True` and strict assignment validations.
- **Storage Model Mixins:** The ORM model `SmeacOrder` in `smeac/models/smeac.py` uses `UUIDPrimaryKeyMixin` instead of `UUIDMixin`, and it is missing the `PermissionMixin` completely, violating the RBAC rules.
- **Enums Storage Strategy:** Enums (e.g. `OrderStatus`) in `SmeacOrder` are mapped using `Enum(OrderStatus)` at the SQLAlchemy level. The template explicitly states: *"Store enums as `String` in the DB, not as enum columns."*

### Required Actions
- Reorganize `models/` into `/contract` and `/storage` packages for all domains.
- Update Pydantic base classes for contract models to use the service's customized `base.BaseModel`.
- Update SQLAlchemy definitions to use the approved `Base`, `UUIDMixin`, `TimestampMixin`, and `PermissionMixin` from `uservice.database.base`. Use `String` columns for all Enums.

---

## 4. Security
> **Rule**: Security contexts must be enforced, and domain permission models must be utilized for RBAC.

### Violations
- **No Facade Permission Checks:** Because Facades are missing, there are no checks like `await self.permissions.require_access(...)` performed prior to data access or mutation. The endpoints inherently fail open or ignore tenancy boundaries.
- **ContextVar Ignoring:** The `auth_gateway_middleware` properly extracts JWT scopes and user details, but the downstream application (routers) ignores `request.state.auth_claims` and the `ContextVar` system.

### Required Actions
- Implement `PermissionService` bindings inside the new Facades to ensure every read and write is scoped to the requesting user's authorization.

---

## Conclusion
The current `src/uservice` codebase requires a structural refactor to conform to the `uservice-template`. The highest priority action is extracting the business logic out of the `api/routes.py` scripts and into correctly formed `DomainFacade` classes, followed by properly structuring the `models` layer into `contract` and `storage`.
