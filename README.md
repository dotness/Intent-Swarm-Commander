# Intent-Swarm-Commander

A swarm orchestration system translating high-level military intents (SMEAC) into concrete, coordinated multi-drone actions using Temporal workflows and Pydantic-AI agentic systems.

## Local Development (Docker Compose)

The entire Intent-Swarm-Commander ecosystem, including the ROS 2 and PX4 Gazebo simulation, can be run locally using Docker Compose without needing physical hardware.

### Prerequisites

- Docker Engine
- NVIDIA Container Toolkit (for Gazebo rendering inside Docker)
- X11 or Wayland server running on host (e.g., WSLg on Windows 11)

### Quickstart

```bash
# Build the containers (this will take 10-20 minutes the first time due to PX4 compilation)
docker compose build

# Start the environment
docker compose up -d

# Verify services
docker compose ps
```

### Accessing the Ecosystem

- **Dashboard**: `http://localhost:8080`
- **Backend API**: `http://localhost:8000`
- **Edge Node API**: `http://localhost:8090`
- **Temporal Server (gRPC)**: `localhost:7233`
- **Gazebo Simulation**: The 3D physics window will appear on your host machine automatically.

### Running a Simulation End-to-End

1. Open the Dashboard.
2. Submit a SMEAC order via the web UI.
3. Observe the edge node API logs: `docker compose logs -f edge_drone`
4. Watch the Gazebo drone take off and maneuver according to the generated swarm intent.
