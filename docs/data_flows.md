# Intent-Swarm-Commander: Data Flows & Sequence Diagrams

This document details the operational data flows within **Intent-Swarm-Commander (ISC)**. It covers the end-to-end journey of tactical orders, safety verification, human approvals, edge execution, and real-time telemetry streaming.

---

## 1. End-to-End Data Flow Overview

```mermaid
graph TD
    %% Node Declarations
    Commander["Commander / Operator"]
    Dashboard["Tactical Dashboard (:8080)"]
    AuthMW["Auth Gateway Middleware"]
    SmeacRoute["SMEAC API Routes (:8000)"]
    TemporalWF["Temporal Durable Workflow (:7233)"]
    PydanticAI["Pydantic-AI Planner Agent"]
    GuardianCritic["Guardian Critic Safety Solver"]
    HitlGate["HITL Decision Service"]
    PostgresDB["PostgreSQL Database (:5432)"]
    EdgeAPI["Edge Drone API (:8090)"]
    PX4Core["PX4 Autopilot & MAVSDK"]
    Vision["YOLO-E Computer Vision"]

    %% Edges
    Commander -->|"1. Submit SMEAC"| Dashboard
    Dashboard -->|"2. POST /api/v1/smeac"| AuthMW
    AuthMW -->|"3. Authorized Request"| SmeacRoute
    SmeacRoute -->|"4. Start Workflow"| TemporalWF
    TemporalWF -->|"5. parse_smeac_activity"| PydanticAI
    PydanticAI -->|"6. SwarmCommandDTOs"| TemporalWF
    TemporalWF -->|"7. Persist Commands"| PostgresDB
    TemporalWF -->|"8. safety_check_activity"| GuardianCritic
    GuardianCritic -->|"9. Return Violations"| TemporalWF
    TemporalWF -->|"10. Trigger Gate if High-Impact"| HitlGate
    HitlGate -->|"11. Present Modal"| Dashboard
    Commander -->|"12. Approve / Reject"| Dashboard
    Dashboard -->|"13. POST /api/v1/hitl/decide"| HitlGate
    HitlGate -->|"14. hitl_decision Signal"| TemporalWF
    TemporalWF -->|"15. Dispatch Command"| EdgeAPI
    EdgeAPI -->|"16. Flight Waypoints"| PX4Core
    EdgeAPI -->|"17. Target Assignment"| Vision
```

---

## 2. Flow 1: SMEAC Order Submission & Multi-Agent Decomposition

When a commander submits a military operation order through the dashboard, it is structured according to the SMEAC military standard and decomposed into coarse-grained swarm commands by an LLM agent.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Commander as "Commander / Operator"
    participant UI as "Tactical Dashboard (:8080)"
    participant Auth as "Auth Gateway Middleware"
    participant API as "SmeacFacade & Router (:8000)"
    participant DB as "PostgreSQL (:5432)"
    participant Temporal as "Temporal Workflow Engine"
    participant Agent as "Pydantic-AI SmeacParserAgent"

    Commander->>UI: Fill SMEAC Form (Situation, Mission, Execution, Admin, Command)
    UI->>Auth: POST /api/v1/smeac (Bearer JWT)
    Auth->>Auth: Validate JWT Signature, Exp, and 'smeac:create' Scope
    Auth->>API: Forward Authorized Request
    API->>DB: INSERT INTO smeac_orders (status = 'submitted')
    API->>Temporal: Start ProcessSmeacWorkflow (order_id, swarm_instance_id, text)
    API-->>UI: 201 Created (order_id, status = 'submitted')
    
    Temporal->>DB: UPDATE smeac_orders SET status = 'parsing'
    Temporal->>Agent: Execute parse_smeac_activity(order_fields)
    Note over Agent: Evaluates LLM Prompt against SMEAC text<br/>Extracts GeoJSON geometries & mission parameters
    Agent-->>Temporal: SmeacParseResult (commands: [SwarmCommandDTO...], reasoning)
    
    loop For each generated command
        Temporal->>DB: INSERT INTO swarm_commands (mission_type, formation, target_area, is_high_impact)
    end
    Temporal->>DB: UPDATE smeac_orders SET status = 'translated'
```

### Detailed Steps:
1. **Payload Submission**: The commander inputs mission parameters into [`main.js`](file:///home/remi/Projects/Intent-Swarm-Commander/src/dashboard/js/main.js). The frontend bundles this into a [`SmeacOrderCreateRequest`](file:///home/remi/Projects/Intent-Swarm-Commander/src/uservice/smeac/models/contract/schemas.py).
2. **Authentication Gate**: [`auth_gateway_middleware`](file:///home/remi/Projects/Intent-Swarm-Commander/src/uservice/security/middleware.py) intercepts the request, decoding the JWT and verifying the `smeac:create` permission.
3. **Initial Persistence**: [`SmeacFacade`](file:///home/remi/Projects/Intent-Swarm-Commander/src/uservice/smeac/facade/smeac.py) creates an initial record in the `smeac_orders` table with status `submitted`.
4. **Workflow Execution**: The durable workflow [`ProcessSmeacWorkflow`](file:///home/remi/Projects/Intent-Swarm-Commander/src/uservice/smeac/operations/process.py) is triggered via the Temporal client.
5. **Agent Inference**: The workflow launches `parse_smeac_activity`, which invokes the [`SmeacParserAgent`](file:///home/remi/Projects/Intent-Swarm-Commander/src/uservice/smeac/operations/smeac_agents.py). The LLM decomposes the intent into formal parameters:
   - `mission_type`: recon, patrol, strike, transport, escort, or abort.
   - `formation_type`: line, wedge, diamond, spread, or stack.
   - `target_area`: Valid GeoJSON (LineString for patrols/transits, Polygon for surveillance zones).
   - `drone_count`, `altitude_m`, `speed_ms`, `duration_s`, and `priority`.
6. **Command Storage**: Each decomposed command is saved to `swarm_commands`, flagged as high-impact if `mission_type` is in `["strike", "abort"]`.

---

## 3. Flow 2: Safety Verification & Guardian Critic Solvers

Before any command can be dispatched to physical hardware or simulation, it must undergo formal safety checks to prevent airspace violations, collisions, or flight envelope exceedances.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Temporal as "Temporal Workflow Engine"
    participant Safety as "Guardian Critic (safety_check_activity)"
    participant Rules as "SORA 2.5 & Airspace Constraint Solver"
    participant DB as "PostgreSQL (:5432)"

    Temporal->>Safety: safety_check_activity(command_dict)
    Safety->>Rules: verify_command(altitude, duration, target_area, drone_count)
    
    Note over Rules: Check Rule 1: Max Altitude <= 120m AGL (SORA 2.5 Ceiling)<br/>Check Rule 2: Max Duration <= 3600s (Battery Reserve)<br/>Check Rule 3: GeoJSON Geofence / Prohibited Airspace Boundary<br/>Check Rule 4: Max Drone Density <= 10 units per sector
    
    alt Violations Found
        Rules-->>Safety: list[Violation] (e.g. ALT_CEILING_EXCEEDED, GEOFENCE_BREACH)
        Safety-->>Temporal: Return list of violation dictionaries
        Temporal->>DB: UPDATE swarm_commands SET verification_status = 'rejected'
        Temporal->>DB: UPDATE smeac_orders SET status = 'rejected'
    else All Constraints Satisfied
        Rules-->>Safety: Empty list (no violations)
        Safety-->>Temporal: []
        Temporal->>DB: UPDATE swarm_commands SET verification_status = 'verified'
        Temporal->>DB: UPDATE smeac_orders SET status = 'verified'
    end
```

### Constraint Checking Specifications:
* **Altitude Ceiling Enforcement**: Evaluated against standard civilian/military joint airspace regulations (maximum 120 meters Above Ground Level).
* **Battery Endurance Limits**: Operational durations exceeding 3,600 seconds trigger a `DURATION_EXCEEDED` violation to preserve mandatory return-to-launch (RTL) battery reserves.
* **Geofence Deconfliction**: GeoJSON coordinates are checked against restricted airspace zones loaded from [`config/restricted_zones.json`](file:///home/remi/Projects/Intent-Swarm-Commander/config/restricted_zones.json).
* **Swarm Density Bounds**: Enforces maximum simultaneous unit allocations per target grid to eliminate mid-air collision hazards.

---

## 4. Flow 3: Human-in-the-Loop (HITL) Approval Gate

High-impact actions (kinetic strikes, mission aborts, or ROE overrides) mandate explicit human commander confirmation under EU AI Act requirements.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Commander as "Commander / Operator"
    participant UI as "Tactical Dashboard (:8080)"
    participant API as "HitlFacade & Router (:8000)"
    participant DB as "PostgreSQL (:5432)"
    participant Temporal as "Temporal Workflow Engine"

    Note over Temporal: Command is flagged is_high_impact = True
    Temporal->>DB: INSERT INTO hitl_decisions (status = 'pending', timeout_seconds = 600)
    Temporal->>DB: UPDATE smeac_orders SET status = 'pending_hitl'
    
    loop Polling Active Decisions (every 3s)
        UI->>API: GET /api/v1/hitl/pending
        API->>DB: SELECT * FROM hitl_decisions WHERE status = 'pending'
        API-->>UI: Return pending decision (decision_id, action_summary, timeout)
    end
    
    UI->>UI: Display Modal Overlay with Countdown Timer
    
    alt Commander Approves
        Commander->>UI: Clicks "Approve"
        UI->>API: POST /api/v1/hitl/decide {"decision": "approved", "rationale": "Authorized by Commander"}
        API->>DB: UPDATE hitl_decisions SET status = 'approved', decision = 'approved'
        API->>Temporal: Signal Workflow 'hitl_decision' (approved = true)
        Temporal->>Temporal: Resume execution, proceed to dispatch
    else Commander Rejects
        Commander->>UI: Clicks "Reject"
        UI->>API: POST /api/v1/hitl/decide {"decision": "rejected", "rationale": "ROE mismatch"}
        API->>DB: UPDATE hitl_decisions SET status = 'rejected', decision = 'rejected'
        API->>Temporal: Signal Workflow 'hitl_decision' (approved = false)
        Temporal->>DB: UPDATE smeac_orders SET status = 'rejected'
        Temporal->>Temporal: Terminate workflow safely
    else Timeout Exceeded (600 seconds)
        Temporal->>Temporal: Workflow timer fires
        Temporal->>DB: UPDATE hitl_decisions SET decision = 'timeout_auto_rejected', timeout_triggered = true
        Temporal->>DB: UPDATE smeac_orders SET status = 'rejected'
    end
```

---

## 5. Flow 4: Tactical Edge Dispatch & Drone Flight Execution

Once commands pass safety verification and HITL approval, they are transmitted to the edge node to drive physical autopilots or simulation bridges.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant Temporal as "Temporal Workflow Engine"
    participant Backend as "FastAPI Swarm Dispatcher"
    participant Edge as "Edge Drone API (:8090)"
    participant Flight as "FlightController (MAVSDK)"
    participant Vision as "YOLO-E Inference Engine"
    participant PX4 as "PX4 Autopilot / Gazebo Sim"

    Temporal->>Backend: dispatch_command_activity(command_id)
    Backend->>Edge: POST :8090/target {"target_object_class": "vehicle", "command_id": "..."}
    Edge->>Vision: Update Target Assignment (class = "vehicle")
    Edge-->>Backend: 200 OK {"status": "target_assigned"}
    
    Backend->>Edge: POST :8090/flight/execute (waypoints, mission_type, formation)
    Edge->>Flight: execute_mission(formation, altitude, waypoints)
    Flight->>PX4: MAVSDK: drone.action.arm()
    Flight->>PX4: MAVSDK: drone.action.takeoff()
    Flight->>PX4: MAVSDK: drone.action.set_current_speed(speed_ms)
    
    loop Fly Waypoints
        Flight->>PX4: MAVSDK: drone.mission.upload_mission() & start_mission()
        Vision->>Vision: Capture frames from camera / Gazebo camera topic
        Vision->>Vision: Run YOLO-E inference (confidence >= 0.5)
        opt Target Detected
            Vision->>Edge: Emit target detection event (bbox, confidence, coords)
        end
    end
```

---

## 6. Flow 5: Real-time Telemetry Collection & Dashboard HUD

The tactical map maintains live positional awareness by polling the backend proxy, which aggregates telemetry from edge drones.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant PX4 as "PX4 Autopilot / SITL"
    participant Edge as "Edge Drone API (:8090)"
    participant Backend as "FastAPI Proxy (:8000)"
    participant UI as "Tactical Dashboard (:8080)"

    loop Background Telemetry Loop (every 500ms)
        PX4->>Edge: MAVLink Telemetry (Position, Battery, Heading, Speed, Mode)
        Edge->>Edge: Update internal _telemetry_state cache
    end

    loop Frontend Telemetry Polling (every 1000ms)
        UI->>Backend: GET /api/v1/swarm/telemetry (Bearer JWT)
        Backend->>Edge: GET :8090/telemetry
        Edge-->>Backend: {"status": "in_flight", "battery": 94, "position": {"lat": 48.858, "lon": 2.294, "alt": 45.0}, "heading": 182, "speed": 12.5}
        Backend-->>UI: Forward telemetry JSON
        UI->>UI: Update Leaflet Drone Marker, HUD Altitude/Speed Gauges, and Trail
    end
```

---

## 7. Flow 6: JIT Ephemeral Credential Lifecycle & Auth Gateway

To eliminate credential sprawl and protect the C2 perimeter, agents and operators request time-bounded Just-In-Time (JIT) JWTs.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Commander as "Commander / Agent"
    participant AuthRoute as "Auth API (/api/v1/auth/login)"
    participant JIT as "JIT Credential Generator"
    participant Gateway as "Auth Gateway Middleware"
    participant Protected as "Protected API Endpoints"

    Commander->>AuthRoute: POST /api/v1/auth/login {"commander_id": "CDR-01", "passphrase": "***"}
    AuthRoute->>AuthRoute: Verify Commander Passphrase
    AuthRoute->>JIT: issue_jit_credential(agent_name="CDR-01", scopes=[smeac:*, hitl:*], lifetime=86400)
    
    Note over JIT: Signs HS256 JWT with claims:<br/>sub: agent-CDR-01-xxxx<br/>iss: isc-auth-gateway<br/>exp: now + 86400s<br/>jit: true, scope: "smeac:create smeac:read hitl:decide"
    
    JIT-->>AuthRoute: Token metadata (token, agent_id, expires_at)
    AuthRoute-->>Commander: Return 200 OK + JWT Token

    Commander->>Gateway: Subsequent API Request (Header: Authorization: Bearer <JWT>)
    Gateway->>Gateway: decode_token(token)
    alt Token Missing or Expired
        Gateway-->>Commander: 401 Unauthorized {"error": "Token has expired / invalid"}
    else Missing Required Scope
        Gateway-->>Commander: 403 Forbidden {"error": "Insufficient privileges"}
    else Valid Token and Scope
        Gateway->>Protected: Forward request with validated claims
        Protected-->>Commander: 200 Success Response
    end
```

