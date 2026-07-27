# Design Document: Extend OperationInfo with Traceback

## Overview

The purpose of this design document is to outline the changes required to extend the `OperationInfo` model with a `traceback` attribute. This attribute will store the error traceback as a list of strings when an operation fails. The error traceback will be saved within the `set_operation_failed` base workflow activity.

## Requirements

1. **Extend `OperationInfo` Model:** Add a `traceback` attribute to the `OperationInfo` model. In the database, this should be stored as a JSON column (specifically, a JSON array of strings). In the contract model, it should be a list of strings.
2. **Update Workflow Activity:** Modify the `set_operation_failed` base workflow activity to accept the traceback and save it when marking an operation as failed.
3. **Update Tests:** Modify and extend end-to-end (e2e) and micro-tests (mt) to verify the new functionality.

## Detailed Design

### 1. Model Modifications

#### Storage Model (`uservice/operation/models/storage/base.py`)

*   Add a `traceback` column to the `OperationInfo` SQLAlchemy model.
*   The column type should be `JSON` and it should be nullable (`nullable=True`), as successful operations will not have a traceback.
*   Default value should be `None`.

```python
# In uservice/operation/models/storage/base.py
from sqlalchemy import JSON
# ...
class OperationInfo(Base, ...):
    # ... existing fields ...
    traceback: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
```

#### Contract Model (`uservice/operation/models/contract/base.py`)

*   Add an optional `traceback` attribute to the `OperationInfo` Pydantic model.

```python
# In uservice/operation/models/contract/base.py
from typing import Optional

class OperationInfo(base.BaseModel):
    # ... existing fields ...
    traceback: Optional[list[str]] = None
```

### 2. Facade Updates

#### Operation Facade (`uservice/operation/facade/operation.py`)

*   Update the `update_operation` method to accept an optional `traceback` parameter.
*   If `traceback` is provided, update the `operation_info.traceback` attribute before committing the changes.

```python
# In uservice/operation/facade/operation.py
from typing import Optional

class Operation(base_facade.DomainFacade):
    # ...
    async def update_operation(
        self,
        operation_id: UUID,
        queue_id: Optional[UUID] = None,
        status: Optional[operation_contract.OperationStatus] = None,
        traceback: Optional[list[str]] = None, # Added parameter
    ) -> operation_contract.OperationInfo:
        # ... fetch operation_info ...

        if queue_id is not None:
            operation_info.queue_id = queue_id
        if status is not None:
            # Handle enum correctly
            operation_info.status = status.value if hasattr(status, "value") else status
        if traceback is not None:
            operation_info.traceback = traceback # Update traceback

        # ... commit and return ...
```

### 3. Activity and Workflow Updates

#### Workflow Metadata (`uservice/base/operations/base.py`)

*   Extend the `WorkflowMetadata` Pydantic model to include an optional `traceback` attribute.

```python
class WorkflowMetadata(BaseModel):
    resource_id: UUID
    username: str
    operation_id: Optional[UUID] = None
    traceback: Optional[list[str]] = None # Added parameter
```

#### Activity (`uservice/base/operations/base.py`)

*   Update the `set_operation_failed` activity to extract the `traceback` from `metadata` (if present) and pass it to `facade.update_operation`.

```python
@activity.defn
async def set_operation_failed(metadata: WorkflowMetadata) -> None:
    from uservice.database.engine import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        facade = await operation_facade.Operation.create(user=metadata.username)
        facade.session = session
        operation_info = await facade.get_operation_info(operation_id=metadata.operation_id)
        await facade.update_operation(
            operation_id=operation_info.id,
            status=operation_contract.OperationStatus.failed,
            traceback=metadata.traceback # Pass traceback to update
        )
```

#### Workflow (`uservice/base/operations/base.py`)

*   Modify the `mark_failed` method in `BaseWorkflow` to optionally accept an exception object or directly populate the metadata's traceback.
*   A common pattern is to catch exceptions in the `run` method of derived workflows, extract the traceback, and update the metadata before calling `mark_failed`. Alternatively, `mark_failed` itself could be updated to capture the current traceback if not provided in metadata, though passing it explicitly via metadata is cleaner. Let's assume the `metadata.traceback` is populated before calling `mark_failed` for explicit control.
*   In specific workflows (like `CreateExample`), when an exception is caught, format the traceback using Python's `traceback.format_exception()` and set `metadata.traceback` before calling `self.mark_failed(metadata=metadata)`.

```python
# Example update in a workflow's run method (e.g., CreateExample)
import traceback as tb_module

@workflow.defn(sandboxed=False)
class CreateExample(operations_base.BaseWorkflow):
    # ...
    @workflow.run
    async def run(self, metadata: operations_base.WorkflowMetadata, data: dict):
        await self.can_we_run(metadata=metadata)
        try:
            # ... activity execution ...
            pass
        except Exception as e:
            # Extract and format traceback
            tb_list = tb_module.format_exception(type(e), e, e.__traceback__)
            metadata.traceback = tb_list
            await self.mark_failed(metadata=metadata)
            raise
        await self.mark_completed(metadata=metadata)
```

### 4. Testing Strategy

#### Micro-tests (mt)

*   **Models:** Verify that the `OperationInfo` contract model can serialize/deserialize lists of strings in the `traceback` field.
*   **Storage:** Verify that creating and retrieving an `OperationInfo` record from the database correctly stores and retrieves the JSON array for `traceback`.
*   **Facade:** Write tests for `update_operation` to ensure that providing a `traceback` successfully updates the database record. Verify that if `traceback` is not provided, it does not clear an existing traceback (or acts as intended).

#### End-to-End Tests (e2e)

*   **Workflow Failure Scenario:** Create an e2e test that intentionally triggers a failure in a workflow (e.g., by providing invalid input or mocking an activity to raise an exception).
*   **Verification:** After the workflow fails, retrieve the operation status using the API or database directly.
*   **Assertions:**
    1.  Assert the operation status is `failed`.
    2.  Assert that the `traceback` attribute on the retrieved operation is not `None` or empty.
    3.  Assert that the `traceback` is a list of strings containing the expected error signature from the triggered failure.
