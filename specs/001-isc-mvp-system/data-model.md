# Data Model: Intent Swarm Commander — MVP System

**Feature**: 001-isc-mvp-system | **Date**: 2026-07-24

## Entities

### SMEAC Order

A structured military order representing commander intent.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique order identifier |
| commander_id | String | Yes | Identity of the submitting commander |
| situation | String | Yes | Situational context (enemy positions, terrain, weather) |
| mission | String | Yes | Mission objective statement |
| execution | String | Yes | Execution plan (formation, timing, assets) |
| admin_logistics | String | No | Administrative and logistics coordination |
| command_signal | String | No | Command and signal details (comms plan) |
| swarm_instance_id | UUID | Yes | Target swarm instance for this order |
| status | Enum | Yes | `draft` → `submitted` → `parsing` → `translated` → `verified` → `executing` → `completed` / `rejected` / `failed` |
| created_at | DateTime | Yes | Submission timestamp |
| updated_at | DateTime | Yes | Last status change |

**State Transitions**:
```
draft → submitted (commander hits submit)
submitted → parsing (system begins SMEAC field extraction)
parsing → translated (coarse-grained operators generated)
translated → verified (safety constraints passed)
translated → rejected (safety constraints violated)
verified → executing (command sent to swarm)
verified → pending_hitl (high-impact action detected)
pending_hitl → executing (commander approved)
pending_hitl → rejected (commander rejected or timeout+controller rejected)
pending_hitl → executing (timeout+controller approved as safe)
executing → completed (swarm execution finished)
executing → failed (execution error)
```

### Swarm Command

The atomic unit of execution derived from a SMEAC Order.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique command identifier |
| smeac_order_id | UUID | Yes | FK → SMEAC Order that generated this command |
| mission_type | Enum | Yes | `recon`, `patrol`, `strike`, `transport`, `escort`, `abort` |
| formation_type | Enum | Yes | `line`, `wedge`, `diamond`, `spread`, `stack` |
| target_area | GeoJSON | Yes | Target coordinates / area polygon |
| target_object_class | String | No | Object class to identify via YOLO-E (e.g., "vehicle") |
| drone_count | Integer | Yes | Number of drones to assign |
| altitude_m | Float | No | Operational altitude in meters |
| speed_ms | Float | No | Operational speed in m/s |
| duration_s | Integer | No | Estimated mission duration |
| priority | Enum | Yes | `critical`, `high`, `normal`, `low` |
| is_high_impact | Boolean | Yes | Whether this triggers HITL gate |

**Validation Rules**:
- `drone_count` must be > 0 and <= available drones in swarm
- `altitude_m` must be within configured min/max bounds
- `mission_type` of `abort` always sets `is_high_impact = true`
- `mission_type` of `strike` always sets `is_high_impact = true`

### Swarm Instance

A registered, running swarm container.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique swarm instance identifier |
| name | String | Yes | Human-readable swarm name |
| container_id | String | Yes | Docker container ID |
| endpoint_url | String | Yes | Reachable API URL for this swarm |
| status | Enum | Yes | `provisioning` → `ready` → `active` → `draining` → `terminated` |
| drone_count | Integer | Yes | Number of simulated drones in this swarm |
| created_at | DateTime | Yes | Provisioning timestamp |
| created_by | String | Yes | Commander who requested provisioning |

**State Transitions**:
```
provisioning → ready (container started, health check passed)
provisioning → failed (container failed to start)
ready → active (first SMEAC order received)
active → draining (termination requested, finishing pending orders)
draining → terminated (all orders completed, container stopped)
ready → terminated (no orders, direct termination)
```

### HITL Decision

A recorded approval/rejection from a human commander.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique decision identifier |
| swarm_command_id | UUID | Yes | FK → Swarm Command requiring approval |
| commander_id | String | Yes | Identity of the deciding commander |
| decision | Enum | Yes | `approved`, `rejected`, `timeout_auto_approved`, `timeout_auto_rejected` |
| rationale | String | No | Commander's stated reason (optional) |
| timeout_triggered | Boolean | Yes | Whether this was an autonomous timeout decision |
| decided_at | DateTime | Yes | Decision timestamp |

### Constraint Violation

A safety check failure record.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique violation identifier |
| swarm_command_id | UUID | Yes | FK → Swarm Command that violated constraints |
| rule_id | String | Yes | Identifier of the violated constraint rule |
| rule_description | String | Yes | Human-readable description of the rule |
| severity | Enum | Yes | `critical`, `high`, `medium`, `low` |
| actual_value | String | Yes | The value that violated the constraint |
| allowed_range | String | Yes | The expected/allowed value range |
| remediation | String | No | Suggested fix |
| detected_at | DateTime | Yes | Detection timestamp |

### Audit Event

An immutable log entry for any significant system action.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique event identifier (auto-generated) |
| event_type | Enum | Yes | `smeac_submitted`, `command_generated`, `auth_granted`, `auth_denied`, `hitl_requested`, `hitl_decided`, `constraint_passed`, `constraint_violated`, `swarm_provisioned`, `swarm_terminated`, `command_executed`, `command_failed` |
| actor_id | String | Yes | Identity of the actor (commander or agent) |
| actor_type | Enum | Yes | `commander`, `agent`, `system` |
| swarm_instance_id | UUID | No | Relevant swarm instance (if applicable) |
| resource_id | String | No | ID of the affected resource |
| details | JSON | Yes | Structured event payload |
| timestamp | DateTime | Yes | Event timestamp (server clock) |

**Immutability Enforcement**: No UPDATE or DELETE operations permitted on this table. Application-level constraint enforced via repository pattern.

### OperationInfo

Tracks the status of asynchronous Temporal workflows (from `uservice-template`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | UUID | Yes | Unique operation identifier |
| workflow_id | String | Yes | Temporal workflow ID |
| resource_id | UUID | Yes | Target entity ID (e.g., Swarm Instance ID) |
| type | String | Yes | Type of operation (`swarm.create`, `smeac.process`) |
| status | Enum | Yes | `created`, `ongoing`, `completed`, `failed` |
| requested_by | String | Yes | Identity of the user who initiated the action |
| created_at | DateTime | Yes | Timestamp of creation |
| updated_at | DateTime | Yes | Timestamp of last status change |

## Relationships

```
Commander ──1:N──▶ SMEAC Order
SMEAC Order ──1:N──▶ Swarm Command
Swarm Command ──0:1──▶ HITL Decision
Swarm Command ──0:N──▶ Constraint Violation
Swarm Instance ──1:N──▶ SMEAC Order
All entities ──────▶ Audit Event (polymorphic log)
OperationInfo ──1:1──▶ (Any entity via resource_id)
```
