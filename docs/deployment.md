# Intent-Swarm-Commander: Deployment Architecture & Infrastructure Guide

This document describes the physical and containerized deployment topologies of **Intent-Swarm-Commander (ISC v0.2.0)**, detailing all system components, deployment environments, network configurations, hardware specifications, and orchestration methods.

---

## 1. Multi-Tier Deployment Topology

The system deploys across three physical environments: the **Command Post C2 Host** (local workstation or field server), the **Simulation Host** (GPU-accelerated development rig), and the **Tactical Edge Nodes** (physical UAV companion computers).

```mermaid
graph TD
    %% Node Declarations
    ClientNode["Commander Client Workstation (Browser)"]
    CP_Host["Command Post Host Server (Linux / Docker Host)"]
    CP_Postgres["isc_postgres (PostgreSQL 15 - :5432)"]
    CP_Temporal["isc_temporal (Temporal Server - :7233)"]
    CP_Backend["isc_backend (FastAPI uService - :8000)"]
    CP_Dashboard["isc_dashboard (HTTP Server - :8080)"]
    Edge_RPi["Tactical Edge UAV (Raspberry Pi 5)"]
    Edge_API["isc_edge Daemon (:8090)"]
    Edge_YOLO["YOLO-E Onboard Perception"]
    Edge_Pixhawk["Pixhawk 6C Autopilot (PX4 v1.14)"]
    Sim_Host["Simulation Node (ROS 2 / Gazebo)"]
    Sim_GZ["Gazebo Harmonic 3D Physics"]
    Sim_PX4["PX4 SITL Drone Simulator"]
    Sim_XRCE["Micro XRCE-DDS Agent Bridge"]

    %% Tier 1 Connections
    subgraph ClientEnv ["Commander Client Environment"]
        ClientNode
    end

    subgraph CommandPostEnv ["Command Post C2 Node (VM / Local Server)"]
        CP_Host
        CP_Dashboard
        CP_Backend
        CP_Temporal
        CP_Postgres
    end

    subgraph TacticalEdgeEnv ["Tactical Edge Hardware (Physical UAV Alpha)"]
        Edge_RPi
        Edge_API
        Edge_YOLO
        Edge_Pixhawk
    end

    subgraph SimulationEnv ["High-Fidelity Simulation Node (GPU Accelerated)"]
        Sim_Host
        Sim_GZ
        Sim_PX4
        Sim_XRCE
    end

    %% Network links
    ClientNode -->|"HTTPS / :8080"| CP_Dashboard
    ClientNode -->|"REST / :8000"| CP_Backend
    CP_Backend -->|"gRPC / :7233"| CP_Temporal
    CP_Temporal -->|"SQL / :5432"| CP_Postgres
    CP_Backend -->|"Asyncpg / :5432"| CP_Postgres

    CP_Backend -->|"Tactical Wi-Fi / WireGuard VPN (:8090)"| Edge_API
    Edge_API --> Edge_YOLO
    Edge_API -->|"MAVLink (UART / Serial)"| Edge_Pixhawk

    CP_Backend -.->|"Local Host Mode (:8090)"| Sim_Host
    Sim_Host --> Sim_XRCE
    Sim_XRCE <--> Sim_PX4
    Sim_PX4 <--> Sim_GZ
```

---

## 2. Component Catalog & Deployment Specifications

The table below outlines each component in the system, where it executes, its technology stack, container image, and networking requirements:

| Component Name | Container Name | Target Host | Tech Stack | Exposed Ports | Network Mode | Storage & Persistence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL DB** | `isc_postgres` | Command Post | PostgreSQL 15 | `5432` | `host` | Named volume `pgdata` (`/var/lib/postgresql/data`) |
| **Temporal Orchestrator** | `isc_temporal` | Command Post | Temporal Server 1.24 (Go) | `7233` (gRPC), `8233` (HTTP) | `host` | Backed by PostgreSQL (`isc_db`) |
| **Temporal UI** | `temporal-ui` *(src/docker)* | Command Post | Temporal Web (Node.js) | `8080` (or `8233`) | `bridge` / `host` | Ephemeral stateless |
| **Backend API Service** | `isc_backend` | Command Post | Python 3.10+, FastAPI, Pydantic-AI | `8000` | `host` | Ephemeral; connects to Postgres & Temporal |
| **Tactical Dashboard** | `isc_dashboard` | Command Post | Python HTTP Server, Leaflet.js | `8080` | `host` | Static web assets from `src/dashboard` |
| **Edge Drone Daemon** | `isc_edge` | Physical Pi 5 or Sim Host | FastAPI, MAVSDK, Ultralytics YOLO-E | `8090` | `host` | In-memory telemetry cache, video frame buffer |
| **Drone Simulation Stack** | `autonomous_drone_env` | Simulation Host | ROS 2 Humble, Gazebo Harmonic, PX4 SITL | `14540`, `14550` (MAVLink UDP) | `host` | Privileged, `/tmp/.X11-unix`, `/mnt/wslg` |

---

## 3. Container Configurations & Orchestration

The project provides two primary container deployment setups:

### 3.1 Primary Integrated Stack (`docker-compose.yml`)

The root [`docker-compose.yml`](file:///home/remi/Projects/Intent-Swarm-Commander/docker-compose.yml) deploys all services using `network_mode: host` for low-latency UDP/MAVLink communication and simple local loopback discovery.

```yaml
services:
  postgres:
    image: postgres:15
    container_name: isc_postgres
    network_mode: host
    restart: unless-stopped
    environment:
      - POSTGRES_USER=isc_user
      - POSTGRES_PASSWORD=isc_pass
      - POSTGRES_DB=isc_db
    volumes:
      - pgdata:/var/lib/postgresql/data

  temporal:
    image: temporalio/auto-setup:1.24
    container_name: isc_temporal
    network_mode: host
    restart: unless-stopped
    environment:
      - DB=postgres12
      - DB_PORT=5432
      - POSTGRES_USER=isc_user
      - POSTGRES_PWD=isc_pass
      - POSTGRES_SEEDS=localhost
    depends_on:
      - postgres

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: isc_backend
    network_mode: host
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql+asyncpg://isc_user:isc_pass@localhost:5432/isc_db
      - TEMPORAL_URL=localhost:7233
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
      - LLM_MODEL=${LLM_MODEL:-gemini-1.5-flash}
    command: uvicorn src.uservice.main:app --host 0.0.0.0 --port 8000
    depends_on:
      - postgres
      - temporal

  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: isc_dashboard
    network_mode: host
    restart: unless-stopped
    command: python3 -m http.server 8080 -d src/dashboard

  edge_drone:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: isc_edge
    network_mode: host
    restart: unless-stopped
    environment:
      - SIMULATION_MODE=true
    command: python3 -c "from src.edge.api.server import run_edge_server; run_edge_server(host='0.0.0.0', port=8090)"

  drone_sim:
    build:
      context: .
      dockerfile: Dockerfile.drone_sim
    container_name: autonomous_drone_env
    network_mode: host
    privileged: true
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu, graphics, compute, utility]
    command: ["/opt/entrypoint_drone.sh"]
```

### 3.2 Standalone uService Stack (`src/docker/docker-compose.yml`)

For targeted API and database testing without spinning up full simulation or ROS 2 dependencies, [`src/docker/docker-compose.yml`](file:///home/remi/Projects/Intent-Swarm-Commander/src/docker/docker-compose.yml) provides an isolated environment using Docker bridge networks and healthchecks.

---

## 4. Hardware Specifications & Edge Deployment (Tactical Edge)

When deploying to physical uncrewed aerial vehicles (UAVs), the tactical edge stack runs onboard the drone's companion computer.

```mermaid
graph LR
    %% Node Declarations
    Camera["Pi Camera Module 3 (CSI-2 / Sony IMX708)"]
    RPi5["Raspberry Pi 5 Companion Computer"]
    EdgeAPI["Edge Server (:8090)"]
    YoloModel["YOLO-E Small Model (NPU / CPU Neon)"]
    FlightCtl["FlightController Daemon (MAVSDK)"]
    TelemetryRadio["MAVLink Telemetry Radio (915MHz)"]
    Pixhawk["Pixhawk 6C Autopilot (PX4 Firmware)"]
    GPS["Dual High-Precision GNSS / Compass"]
    ESCs["Electronic Speed Controllers (ESCs) & Motors"]

    %% Wiring / Interface connections
    Camera -->|"CSI MIPI Cable"| RPi5
    RPi5 --> EdgeAPI
    EdgeAPI --> YoloModel
    EdgeAPI --> FlightCtl
    FlightCtl <-->|"UART /dev/ttyAMA0 @ 921600 baud"| Pixhawk
    Pixhawk <--> TelemetryRadio
    GPS --> Pixhawk
    Pixhawk --> ESCs
```

### Edge Hardware Specifications
* **Companion Single Board Computer**:
  * **Model**: Raspberry Pi 5 Model B (8GB RAM recommended).
  * **Processor**: Broadcom BCM2712 64-bit ARM Cortex-A76 quad-core @ 2.4GHz.
  * **Operating System**: Raspberry Pi OS 64-bit (Debian 12 Bookworm, Linux kernel 6.6+).
  * **Storage**: 64GB High-Endurance MicroSD (Class A2) or NVMe Base M.2 SSD via PCIe Gen 2/3.
* **Perception & Camera**:
  * **Sensor**: Raspberry Pi Camera Module 3 (Sony IMX708 12MP sensor, HDR, autofocus).
  * **Interface**: 15-pin/22-pin MIPI CSI-2 connector.
  * **Inference Runtime**: PyTorch CPU with ARM NEON acceleration or optional Hailo-8 M.2 AI Acceleration Module (up to 26 TOPS).
* **Flight Controller Integration**:
  * **Autopilot Board**: Holybro Pixhawk 6C / Pixhawk 4 running PX4 Autopilot v1.14+.
  * **Physical Interface**: TELEM2 port connected to Raspberry Pi 5 `UART0` (`/dev/ttyAMA0`) at `921600 baud` using standard 6-pin JST-GH cable.
  * **Protocol**: MAVLink 2.0 streaming high-rate attitude, global position, and battery status.

### Edge Daemon Execution on Hardware
On physical hardware, the edge server is configured as a systemd service:

```ini
[Unit]
Description=Intent Swarm Commander Edge Node
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Intent-Swarm-Commander
Environment=SIMULATION_MODE=false
Environment=MAVSDK_SYSTEM_ADDRESS=serial:///dev/ttyAMA0:921600
ExecStart=/home/pi/Intent-Swarm-Commander/.venv/bin/python3 -c "from src.edge.api.server import run_edge_server; run_edge_server(host='0.0.0.0', port=8090)"
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

---

## 5. High-Fidelity Simulation Environment (SITL & Gazebo)

For software-in-the-loop (SITL) testing without hardware, the `drone_sim` container ([`Dockerfile.drone_sim`](file:///home/remi/Projects/Intent-Swarm-Commander/Dockerfile.drone_sim)) provides a complete 3D virtual testing range:

1. **PX4 Autopilot SITL**: Compiles the native PX4 flight control firmware to run directly on Linux x86_64, emulating sensors, state estimation (EKF2), and motor actuators.
2. **Gazebo Harmonic (`gz-harmonic`)**: Provides advanced aerodynamic drag modeling, multi-rotor thrust dynamics, gravity, and ray-traced camera sensors.
3. **Micro XRCE-DDS Agent**: Acts as an ultra-low-latency bridge between ROS 2 Humble topics and PX4 uORB messaging channels.
4. **NVIDIA Container Toolkit Integration**: Maps GPU device capabilities (`gpu, graphics, compute, utility`) and mounts the host X11 display socket (`/tmp/.X11-unix` and `/mnt/wslg` on WSL2) so simulated 3D worlds render at 60+ FPS.

### Launching Simulation
```bash
# Start all command post services and SITL drone environment
docker compose up -d

# Check simulation and PX4 logs
docker logs -f autonomous_drone_env
```

---

## 6. Network Security & Port Allocations

| Port | Protocol | Binding | Service | Security / Access Control |
| :--- | :--- | :--- | :--- | :--- |
| `5432` | TCP | `localhost` | PostgreSQL 15 | Username/password authentication (`isc_user`) |
| `7233` | TCP / gRPC | `0.0.0.0` | Temporal Frontend | Internal cluster access |
| `8000` | TCP / HTTP | `0.0.0.0` | FastAPI Backend API | JWT Bearer token required (`auth_gateway_middleware`) |
| `8080` | TCP / HTTP | `0.0.0.0` | Tactical Dashboard Web UI | Public C2 browser access |
| `8090` | TCP / HTTP | `0.0.0.0` | Edge Drone API | Private Mesh / VPN network (WireGuard recommended) |
| `14540`| UDP | `localhost` | PX4 MAVLink Local SDK | MAVSDK client loopback connection |
| `14550`| UDP | `0.0.0.0` | PX4 Ground Control Station | QGroundControl / Mission Planner broadcast |
| `8883` | TCP / TLS | `0.0.0.0` | Mosquitto MQTT *(PMA Integration)* | Mutual TLS (mTLS) for high-rate telemetry bus |

