# Contract: MCP Tool Definitions

**Service**: Swarm Controller MCP Server (`src/swarm_controller/mcp_tools.py`)

Each Dedicated Swarm Instance exposes the following MCP Tools that are dynamically registered with the central MCP Auth Gateway upon provisioning. These tools allow Command Agents to interact with the swarm programmatically using the MCP JSON-RPC protocol.

## Tools

### ingest_smeac

Submit a SMEAC order to the swarm for processing.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "situation": {"type": "string", "description": "Situational context"},
    "mission": {"type": "string", "description": "Mission objective"},
    "execution": {"type": "string", "description": "Execution plan"},
    "admin_logistics": {"type": "string", "description": "Admin and logistics"},
    "command_signal": {"type": "string", "description": "Command and signal details"}
  },
  "required": ["situation", "mission", "execution"]
}
```

**Output**: Order ID and initial parsing status.

**Required Scope**: `swarm:{swarm_id}:orders:write`

### get_order_status

Check the status of a submitted SMEAC order.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "order_id": {"type": "string", "format": "uuid"}
  },
  "required": ["order_id"]
}
```

**Output**: Order status, generated commands, constraint violations.

**Required Scope**: `swarm:{swarm_id}:orders:read`

### execute_swarm_command

Execute a verified swarm command (post-verification, post-HITL if applicable).

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "command_id": {"type": "string", "format": "uuid"}
  },
  "required": ["command_id"]
}
```

**Output**: Execution confirmation or error.

**Required Scope**: `swarm:{swarm_id}:commands:execute`

### get_swarm_telemetry

Retrieve current simulated drone positions and status.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "include_battery": {"type": "boolean", "default": true},
    "include_mission": {"type": "boolean", "default": true}
  }
}
```

**Output**: Array of drone telemetry objects.

**Required Scope**: `swarm:{swarm_id}:telemetry:read`

### request_hitl_approval

Explicitly request HITL approval for an action. Called automatically for high-impact commands but can also be triggered manually by an agent.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "command_id": {"type": "string", "format": "uuid"},
    "action_summary": {"type": "string"},
    "timeout_seconds": {"type": "integer", "default": 120}
  },
  "required": ["command_id", "action_summary"]
}
```

**Output**: Decision ID and pending status.

**Required Scope**: `swarm:{swarm_id}:hitl:request`

## Tool Registration

When a Dedicated Swarm Instance starts, it registers all its tools with the MCP Auth Gateway via a registration call. The gateway maps tool names to the swarm's endpoint URL and validates scope requirements on each invocation.

**Registration payload** (sent by swarm controller on startup):
```json
{
  "swarm_id": "uuid-swarm-001",
  "tools": [
    {"name": "ingest_smeac", "scope": "swarm:uuid-swarm-001:orders:write"},
    {"name": "get_order_status", "scope": "swarm:uuid-swarm-001:orders:read"},
    {"name": "execute_swarm_command", "scope": "swarm:uuid-swarm-001:commands:execute"},
    {"name": "get_swarm_telemetry", "scope": "swarm:uuid-swarm-001:telemetry:read"},
    {"name": "request_hitl_approval", "scope": "swarm:uuid-swarm-001:hitl:request"}
  ],
  "endpoint_url": "http://swarm-uuid-swarm-001:8080"
}
```
