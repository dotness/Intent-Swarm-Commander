# Data Model: End-to-End Production Flight (`008-e2e-prod-flight`)

## Entities & Contracts

### 1. Edge Navigation Request (`POST /navigate` on `isc_edge:8090`)
- `command_id: str` — Originating `SwarmCommand` UUID
- `swarm_id: str | None` — Active swarm UUID to bind `_telemetry_publisher`
- `project_id: str | None` — Active theater/project ID to bind `_telemetry_publisher`
- `waypoints: list[Waypoint]` — Ordered target coordinates (`lat: float`, `lon: float`, `alt_m: float = 20.0`)

### 2. Edge Telemetry Context (`POST /context` on `isc_edge:8090`)
- `swarm_id: str` — Active swarm UUID
- `project_id: str` — Active theater/project ID

### 3. Temporal `ProcessSmeacWorkflow` Dispatch Payload
- `order_id: str`
- `swarm_instance_id: str`
- `project_id: str`
- `endpoint_url: str`
- `commands: list[dict]` — Includes extracted `target_area` GeoJSON (`Point`, `LineString`, `Polygon`) and `altitude_m`
