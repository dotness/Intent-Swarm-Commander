# Operations — Temporal Workflows & ADK Agents

> **Location**: `uservice/<domain>/operations/`
> **Responsibility**: Durable, asynchronous execution of state-mutating actions via Temporal workflows orchestrated by ADK 2.0 multi-agent pipelines.

---

## Architecture

```
     Facade                   Temporal                      ADK 2.0
  ┌──────────┐            ┌──────────────┐           ┌─────────────────┐
  │ schedule_ │──create──→│ BaseWorkflow │──activity─→│ Planner Agent   │
  │ create()  │  operation│   .run()     │           │       ↓         │
  │           │  + start  │              │           │ Guardian Critic  │
  └──────────┘  workflow  │              │           │       ↓         │
                          │              │           │ Executor Agent   │
                          │              │           │  (uses tools)   │
                          └──────────────┘           └─────────────────┘
```

### Flow

1. **Facade** creates a DB record and operation tracking entry, then starts a Temporal workflow.
2. **Temporal workflow** checks dependencies, sets operation status, and executes an activity.
3. **Activity** runs an ADK 2.0 multi-agent pipeline.
4. **Agent pipeline**: Planner → Guardian Critic → Executor.
5. Workflow marks operation as completed or failed.

---

## File Structure

```
uservice/<domain>/operations/
├── __init__.py
├── create.py              # CreateEntity workflow + PlannerAgent
├── update.py              # UpdateEntity workflow + PlannerAgent
├── delete.py              # DeleteEntity workflow + PlannerAgent
├── <domain>_agents.py     # Shared agents (GuardianCritic, Executor) + run_agentic_workflow()
└── steps/                 # Reusable Temporal activities (granular steps)
    ├── create.py
    ├── update.py
    └── delete.py
```

---

## BaseWorkflow

All workflows inherit from `uservice.base.operations.base.BaseWorkflow`.

```python
class BaseWorkflow:
    # Must declare workflow dependencies
    @property
    @abstractmethod
    def DEPENDS_ON(self) -> Sequence[BaseWorkflow]: ...

    # Lifecycle helpers
    async def can_we_run(self, metadata): ...      # Check deps + set "ongoing"
    async def mark_completed(self, metadata): ...  # Set "completed"
    async def mark_failed(self, metadata): ...     # Set "failed"

    # Static helpers
    @classmethod
    def get_task_queue_name(cls) -> str: ...  # Uses class name
    @classmethod
    def get_name(cls) -> str: ...
    @classmethod
    def get_workflow_id(cls) -> str: ...      # uuid4

    # Factory — creates Operation record + starts Temporal workflow
    @classmethod
    async def create(cls, metadata: WorkflowMetadata, data: Any) -> OperationInfo: ...
```

### `WorkflowMetadata`

```python
class WorkflowMetadata(BaseModel):
    resource_id: UUID           # The entity being acted upon
    username: str               # Authenticated user
    operation_id: Optional[UUID] = None  # Set after operation record creation
```

### `BaseWorkflow.create()` lifecycle

1. Creates an `OperationInfo` record via the Operation facade (status: `created`).
2. Sets `metadata.operation_id`.
3. Connects to Temporal and starts the workflow.
4. Updates the operation with the Temporal `queue_id`.
5. Returns the `OperationInfo`.

---

## Writing a Workflow

### Step 1: Define the Planner Agent

```python
# uservice/<domain>/operations/create.py

from google.adk import Agent

class CreatePlannerAgent(Agent):
    def __init__(self, **kwargs):
        instruction = (
            "You are the <Entity> Create Planner. Based on the task description and data, "
            "propose a clear, high-level plan to create a new <entity>. "
            "Ensure you specify the tool for creation with appropriate parameters. "
            "Do NOT execute the tool yourself. Output the proposed action clearly."
        )
        super().__init__(
            name="<entity>_create_planner",
            model="gemini-2.5-flash-lite",
            instruction=instruction,
            **kwargs
        )
```

### Step 2: Define the activity

```python
from temporalio import activity
from uservice.base.operations import base as operations_base
from .<domain>_agents import run_agentic_workflow

@activity.defn
async def execute_create_agentic_operation(
    metadata: operations_base.WorkflowMetadata,
    task_description: str,
    task_data: dict
):
    """Activity that runs the ADK workflow for creating an entity."""
    planner = CreatePlannerAgent()
    return await run_agentic_workflow(
        metadata, task_description, task_data,
        planner, "<entity>_agentic_workflow_create"
    )
```

### Step 3: Define the workflow class

```python
from temporalio import workflow
from datetime import timedelta

@workflow.defn(sandboxed=False)
class CreateEntity(operations_base.BaseWorkflow):
    @property
    def DEPENDS_ON(self) -> tuple:
        return ()  # No dependencies, or list workflow classes

    @workflow.run
    async def run(self, metadata: operations_base.WorkflowMetadata, data: dict):
        # 1. Check dependencies + mark "ongoing"
        await self.can_we_run(metadata=metadata)
        try:
            # 2. Execute the agentic activity
            await workflow.execute_activity(
                activity=execute_create_agentic_operation,
                args=(metadata, "Create a new entity", data),
                start_to_close_timeout=timedelta(seconds=300),
            )
        except Exception:
            # 3a. Mark failed on error
            await self.mark_failed(metadata=metadata)
            raise
        # 3b. Mark completed on success
        await self.mark_completed(metadata=metadata)
```

### Rules for workflows

| ✅ DO | ❌ DON'T |
|-------|---------|
| Use `@workflow.defn(sandboxed=False)` | Omit `sandboxed=False` (Temporal sandbox breaks async) |
| Set `DEPENDS_ON` as a tuple of workflow classes | Skip DEPENDS_ON |
| Always call `can_we_run()` first | Start work without checking dependencies |
| Catch exceptions and call `mark_failed()` | Let exceptions propagate without marking |
| Call `mark_completed()` on success | Forget to update status |
| Use `timedelta(seconds=300)` for timeout | Use very short or no timeouts |

---

## ADK Agent Pipeline

### Shared agents file: `<domain>_agents.py`

Each domain defines its shared agents and the `run_agentic_workflow()` helper:

```python
# uservice/<domain>/operations/<domain>_agents.py

import asyncio, json
from google.adk import Agent, Workflow, Runner
from google.adk.sessions import InMemorySessionService
from uservice.base.operations.base import WorkflowMetadata
from uservice.database.engine import AsyncSessionLocal
from uservice.<domain>.facade.<entity> import Entity

class GuardianCriticAgent(Agent):
    def __init__(self, **kwargs):
        instruction = (
            "You are the Guardian Critic implementing Reasoning by Inversion (InvThink). "
            "Review the proposed action. Check for missing or invalid parameters. "
            "If the plan is safe, end with 'APPROVED'. "
            "If unsafe, end with 'REJECTED: [Reason]'."
        )
        super().__init__(
            name="guardian_critic",
            model="gemini-2.5-flash-lite",
            instruction=instruction,
            **kwargs
        )

class ExecutorAgent(Agent):
    def __init__(self, tools=None, **kwargs):
        instruction = (
            "You are the Executor. If the Guardian Critic approved, "
            "execute the planned action using the provided tools. "
            "If rejected, reply with 'Operation Aborted' and the reason."
        )
        super().__init__(
            name="executor",
            model="gemini-2.5-flash-lite",
            instruction=instruction,
            tools=tools or [],
            **kwargs
        )
```

### `run_agentic_workflow()` — the orchestrator

```python
async def run_agentic_workflow(
    metadata: WorkflowMetadata,
    task_description: str,
    task_data: dict,
    planner_agent: Agent,
    workflow_name: str
) -> str:
    async with AsyncSessionLocal() as session:
        # 1. Set up domain facade with tools
        facade = await Entity.create(user=user_info)
        facade.session = session

        # 2. Instantiate agents
        guardian = GuardianCriticAgent()
        executor = ExecutorAgent(tools=facade.exposed_tools)

        # 3. Define workflow graph
        workflow = Workflow(
            name=workflow_name,
            edges=[
                ("START", planner_agent),
                (planner_agent, guardian),
                (guardian, executor),
            ]
        )

        # 4. Run via Runner
        runner = Runner(
            node=workflow,
            app_name="<domain>_operations_app",
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )

        input_message = {"task": task_description, "data": task_data}

        events = await asyncio.to_thread(
            lambda: list(runner.run(
                user_id=metadata.username,
                session_id=str(metadata.operation_id),
                new_message=json.dumps(input_message),
            ))
        )

        # 5. Extract text results
        result_text = ""
        for event in events:
            if event.content:
                for part in event.content.parts:
                    if part.text:
                        result_text += part.text
        return result_text
```

### Three-agent pattern

| Agent | Role | Model |
|-------|------|-------|
| **Planner** | Proposes a high-level action plan based on input data. Domain-specific. | `gemini-2.5-flash-lite` |
| **Guardian Critic** | Reviews the plan using "Reasoning by Inversion" — asks what would guarantee failure. Approves or rejects. | `gemini-2.5-flash-lite` |
| **Executor** | Executes approved plans using facade `exposed_tools`. Aborts if rejected. | `gemini-2.5-flash-lite` |

### Rules for agents

| ✅ DO | ❌ DON'T |
|-------|---------|
| Create domain-specific Planners per operation | Reuse the same Planner for all operations |
| Reuse GuardianCritic and Executor across operations | Create new Guardian/Executor classes per operation |
| Use `InMemorySessionService` | Use persistent session services |
| Run `runner.run()` via `asyncio.to_thread()` | Call runner synchronously in an async context |
| Feed `facade.exposed_tools` to the Executor | Hard-code tool functions |

---

## Activity Steps (`steps/`)

For granular, reusable activities that can be composed into workflows independently of the agent pipeline:

```python
# uservice/<domain>/operations/steps/create.py

from temporalio import activity, exceptions
from uservice.base.operations import base as operations_base

@activity.defn
async def ensure_network(metadata: operations_base.WorkflowMetadata, data: dict):
    """Validates and provisions network for the entity."""
    if not data or not data.get("name"):
        raise exceptions.ApplicationError(
            "Invalid data: missing name", non_retryable=True
        )
```

### When to use steps vs. agents

| Use **steps** when | Use **agents** when |
|-------------------|---------------------|
| Logic is deterministic and well-defined | Logic requires reasoning or decision-making |
| You need fine-grained retry control | The operation benefits from critique/review |
| Side effects need to be isolated | You want human-readable execution traces |

---

## Operation Lifecycle

```
    created   →   ongoing   →   completed
                     ↓
                   failed
```

| Status | Set by |
|--------|--------|
| `created` | `BaseWorkflow.create()` |
| `ongoing` | `can_we_run()` (after dependency check) |
| `completed` | `mark_completed()` |
| `failed` | `mark_failed()` |

---

## Dependency Management

Workflows declare their dependencies via `DEPENDS_ON`:

```python
@property
def DEPENDS_ON(self) -> tuple:
    return (CreateEntity,)  # This workflow waits for CreateEntity to finish
```

The `can_we_run()` method checks if any operations of the listed types (plus the current type) are still running for the same `resource_id`. If so, it retries with exponential backoff.

---

## Temporal Data Converter

Pydantic models are serialized for Temporal using a custom converter:

```python
from uservice.base.operations.converter import pydantic_data_converter

client = await Client.connect(
    f"{TEMPORAL_QUEUE_SECRETS.host}:{TEMPORAL_QUEUE_SECRETS.port}",
    data_converter=pydantic_data_converter
)
```

Always use `pydantic_data_converter` when connecting to Temporal. It ensures proper serialization/deserialization of Pydantic models in workflow and activity arguments.
