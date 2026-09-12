# Intent-Swarm-Commander: System Architecture

![Intent-Swarm-Commander Architecture](./images/swarm_architecture.jpg)

## System Overview

**Intent-Swarm-Commander (ISC)** translates high-level military intent orders (**SMEAC**: Situation, Mission, Execution, Administration, Command/Signal) into resilient, coordinated multi-drone operations.

The architecture is partitioned into three decoupled tiers:

### 1. Top Tier: Commander Dashboard & HITL Interface
* **Tactical Web UI**: Leaflet.js map display, real-time telemetry, and operational status (`:8080`).
* **SMEAC Intent Parser**: Ingestion of mission intent parameters and operational constraints.
* **Human-in-the-Loop (HITL) Validation**: Safety gating requiring explicit human approval before irreversible swarm execution.

### 2. Middle Tier: Mission Orchestration Engine
* **Temporal Workflow Engine**: Durable distributed state machine managing order lifecycles, retries, and fail-closed safety (`:7233`).
* **Pydantic-AI Multi-Agent Collective**:
  * **Planner Agent**: Decomposes high-level intent into coarse-grained swarm operators.
  * **Guardian Critic Agent**: Enforces safety, airspace boundaries, and military ROEs (Rules of Engagement).
  * **Executor Agent**: Translates validated plans into dispatchable drone tasks.
* **State Store**: PostgreSQL database backing Temporal state and domain entities (`:5432`).
* **MCP (Model Context Protocol) Gateway**: Standardized tool interface exposing swarm management and sensors over JSON-RPC (SSE/HTTP).

### 3. Bottom Tier: Edge Nodes & Autonomous Drone Swarm
* **Edge Compute (Raspberry Pi 5 / Edge API)**: Edge server (`:8090`) coordinating local drone execution.
* **Onboard Perception**: Real-time object and target identification powered by YOLO-E and OpenCV.
* **Flight Controllers & Autopilot**: MAVSDK communicating with PX4 Autopilot over MAVLink.
* **Simulation & Physics**: ROS 2 bridging with Gazebo 3D simulation for zero-hardware local testing.

---

## Architecture Flow Diagram

```mermaid
graph TD
    %% Node Declarations
    Commander["Commander / Operator"]
    Dashboard["Tactical Web Dashboard (Port 8080)"]
    HITL["HITL Approval Gate"]
    Backend["FastAPI Backend API (Port 8000)"]
    Temporal["Temporal Orchestrator (Port 7233)"]
    AgentPlanner["Planner Agent"]
    AgentCritic["Guardian Critic Agent"]
    AgentExec["Executor Agent"]
    MCPGate["MCP Auth Gateway"]
    Postgres["PostgreSQL Store"]
    EdgeAPI["Edge Drone API (Port 8090)"]
    YoloCV["YOLO-E Perception & OpenCV"]
    PX4["PX4 Autopilot / MAVSDK"]
    Gazebo["Gazebo 3D Simulation / ROS 2"]

    %% Subgraphs and Connections
    subgraph Tier1 ["Top Tier: Command & Control"]
        Commander --> Dashboard
        Dashboard --> HITL
        HITL --> Backend
    end

    subgraph Tier2 ["Middle Tier: Orchestration & Multi-Agent Core"]
        Backend --> Temporal
        Temporal --> Postgres
        Temporal --> AgentPlanner
        AgentPlanner --> AgentCritic
        AgentCritic --> AgentExec
        AgentExec --> MCPGate
    end

    subgraph Tier3 ["Bottom Tier: Tactical Swarm & Edge"]
        MCPGate --> EdgeAPI
        EdgeAPI --> YoloCV
        EdgeAPI --> PX4
        PX4 --> Gazebo
    end
```
