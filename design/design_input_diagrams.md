# Intent Swarm Commander — Design Input Diagrams

> Architectural diagrams for the Intent Swarm Commander system.
> Each diagram below is presented as a Mermaid code block followed by key constraints and insights.

---

## 1. System Architecture Diagram (The Compliant Pipeline)

This architecture reflects the mandatory 7-step pipeline required to remediate your initial drafts. It explicitly enforces the **Model Context Protocol (MCP)** as the central control plane and integrates the required safety and identity gateways.

```mermaid
graph TD
    %% User Interfaces
    subgraph CommanderInterface ["Commander Interface"]
        GUI["Commander GUI / Tactical Map"]
        SMEAC["SMEAC Intent Ingestion"]
        HITL["HITL Confirmation Modal"]
    end

    %% Agent & Authorization
    subgraph AgentLayer ["Agent Layer"]
        API["Elicitation API"]
        Worker["Command Agent Worker"]
    end

    subgraph IdentityGovernance ["Identity & Governance"]
        IdP["Enterprise IdP - Okta/Entra"]
        EMA["Enterprise Managed Auth / JIT"]
    end

    %% MCP Control Plane
    subgraph MCPControlPlane ["MCP Control Plane"]
        AuthGate["MCP Auth Gateway - OAuth 2.1/NHI"]
        RBAC["Scope-Based Tool Loading"]
        ToolExec["MCP Tool Execution Gateway"]
        Registry["MCP Server Registry"]
    end

    %% Verification & Physical Layer
    subgraph SafetyVerification ["Safety Verification Layer"]
        SORA["SORA 2.5 Constraint Graph"]
        NSVIF["NSVIF Constraint Solvers"]
    end

    subgraph TacticalEdge ["Tactical Edge"]
        SwarmPool["Swarm Pool / Controller"]
        Drone["Physical Drone Swarm"]
        UTM["UTM System / Remote ID"]
    end

    %% Flow
    GUI --> SMEAC
    SMEAC --> API
    API -->|"High Impact Action?"| HITL
    HITL -->|"Approved"| Worker
    API -->|"Normal Action"| Worker

    IdP -->|"ID-JAG / Tokens"| EMA
    EMA -->|"JIT Ephemeral Identity"| Worker

    Worker -->|"Request Action"| AuthGate
    AuthGate --> RBAC
    RBAC --> ToolExec
    ToolExec -.->|"Discover Tools"| Registry
    ToolExec -->|"Proposed Command"| SORA
    SORA --> NSVIF
    NSVIF -->|"Verified Command"| SwarmPool

    SwarmPool -->|"Coarse Operators"| Drone
    Drone -->|"Telemetry/Deconfliction"| UTM
```

### Key Architectural Constraints

- **HITL Gateway** — Routes high-impact decisions (mass abort, ROE changes) to a human commander prior to execution, fulfilling EU AI Act requirements.
- **Identity Layer** — The Agent receives a cryptographically verified Just-In-Time (JIT) identity to prevent credential sprawl.
- **Formal Verification** — Bypassing direct drone control, commands must satisfy NSVIF solvers and the SORA 2.5 ontology before reaching the Swarm Pool.

---

## 2. Deployment Architecture (Infrastructure Topology)

This defines where these components physically execute, moving from the **strategic cloud** down to the **tactical edge** where the physical swarm operates.

```mermaid
graph LR
    subgraph StrategicCloud ["Strategic Cloud Environment"]
        CommandNode["Commander Workstation Node"]
        IdPServer["Central IdP Server"]
        PolicyServer["Policy-as-Code Engine"]
    end

    subgraph CommandPost ["Command Post Edge Server"]
        MCP_Hub["MCP Gateway Server"]
        Agent_Container["Agent Runtime Environment"]
        Verification_Engine["NSVIF & SORA Processing Node"]
        Sim_Node["MINT UAV Simulation Validations"]
    end

    subgraph TacticalField ["Tactical Field Operations"]
        Swarm_Node["Swarm Pool Controller Edge"]
        Drone_1["UAV Alpha"]
        Drone_2["UAV Bravo"]
    end

    subgraph ExternalInfra ["External Infrastructure"]
        UTM_Cloud["National Airspace UTM"]
    end

    %% Connections
    CommandNode <-->|"HTTPS/WSS"| Agent_Container
    IdPServer -->|"JWKS / EMA"| MCP_Hub
    PolicyServer --> MCP_Hub

    Agent_Container <-->|"gRPC/REST"| MCP_Hub
    MCP_Hub <-->|"Local API"| Verification_Engine
    Verification_Engine <-->|"Pre-flight Checks"| Sim_Node

    Verification_Engine -->|"Encrypted Link"| Swarm_Node
    Swarm_Node -->|"RF / LoRa"| Drone_1
    Swarm_Node -->|"RF / LoRa"| Drone_2

    Drone_1 -.->|"Remote ID Broadcast"| UTM_Cloud
    Drone_2 -.->|"Remote ID Broadcast"| UTM_Cloud
```

### Deployment Insights

- **MINT Integration** — High-fidelity simulations run at the Command Post Edge to validate tree planning before live execution.
- **Airspace Integration** — Drones broadcast their digital airspace identity directly to external UTM systems for real-time deconfliction.

---

## 3. Domain-Driven Design (DDD) Context Map

To organize the software modules and separate bounded contexts, here is the DDD breakdown. This prevents tight coupling between the user intent, the identity verification, and the physical swarm execution.

```mermaid
graph TD
    subgraph MissionCommand ["Mission Command Context"]
        Intent["SMEAC Intent"]
        Approval["Durable Approval Gates"]
        Elicit["HITL Elicitation"]
    end

    subgraph IdentityGov ["Identity & Governance Context"]
        NHI["Non-Human Identity"]
        JIT["Ephemeral Credentials"]
        RBAC_Pol["Scope-Based Tool Policy"]
    end

    subgraph MCPOrchestration ["MCP Orchestration Context"]
        Gateway["MCP Gateway"]
        Reg["Tool Registry"]
        Exec["Execution Routing"]
    end

    subgraph VerificationCtx ["Verification Context"]
        SORA_Ont["SORA 2.5 Machine-Readable Encoding"]
        NSVIF_Solv["CSP Solvers"]
    end

    subgraph SwarmExecution ["Swarm Execution Context"]
        Pool["Task Orchestration"]
        MINT["Neuro-Symbolic Planning"]
        RemoteID["UTM Identity"]
    end

    %% Context Relationships (Upstream/Downstream)
    MissionCommand -->|"Customer/Supplier"| MCPOrchestration
    IdentityGov -->|"Shared Kernel / Auth"| MCPOrchestration
    MCPOrchestration -->|"Conformist"| VerificationCtx
    VerificationCtx -->|"Anti-Corruption Layer"| SwarmExecution
```

### DDD Domain Boundaries

- **Identity & Governance** — Handles OAuth 2.1, Dynamic Client Registration (DCR), and Enterprise-Managed Authorization (EMA).
- **Verification Context** — Exclusively handles the translation of SORA 2.5 safety objectives into machine-readable ontologies and runs the deterministic safety enforcement.
- **Mission Command Context** — Manages durable workflow gates for long-running or multi-day swarm mission plans, allowing commanders to approve or reject plans asynchronously.