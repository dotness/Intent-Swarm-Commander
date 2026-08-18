# Feature Specification: Local Docker Compose Simulation

**Feature Branch**: `003-local-docker-simulation`

**Created**: 2026-07-27

**Status**: Draft

**Input**: User description: "For MVP / PoC purposes i dont want to use real RasperryPi5 , but a docker compose service instead, same with drone simulation. I want to be able to test e2e here locally. For drone tech stack and simulation check github.com/dotness/Drone-Swarm and use what i have used there"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Local E2E Simulation Environment (Priority: P1)

A developer or commander wants to run the entire Intent-Swarm-Commander stack locally on a single machine for testing and MVP validation. They run a single `docker compose up` command, which orchestrates the backend services (PostgreSQL, Temporal, microservices) alongside simulated drone edge nodes using ROS 2, PX4, and Gazebo. 

**Why this priority**: Running a physical Raspberry Pi 5 swarm is too complex and costly for rapid prototyping and MVP testing. A fully contained local simulation environment is critical for end-to-end functional testing.

**Independent Test**: Can be tested by running `docker compose up` on a host machine and verifying that all services start successfully, and the simulated drone connects to the backend as an edge node.

**Acceptance Scenarios**:

1. **Given** a developer with Docker and WSL2/Linux, **When** they execute the docker compose startup, **Then** all backend services and the drone simulation environment initialize without errors.
2. **Given** the local simulation is running, **When** a user submits a SMEAC order via the dashboard, **Then** the simulated Gazebo drone receives the command through the edge service and moves accordingly in the simulation.
3. **Given** the simulation is active, **When** the dashboard polls for telemetry, **Then** it receives real-time simulated ROS 2/PX4 telemetry data (odometry, battery) from the local edge container.

### Edge Cases

- What happens when the Gazebo simulation crashes or becomes unresponsive?
- How does the system handle networking delays or bridging issues between the Docker containers (e.g., MicroXRCEAgent failures)?
- What happens if the host machine's resources max out while running the simulation?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `docker-compose.yml` file that orchestrates the entire stack: frontend dashboard, backend microservices, database, Temporal, and drone simulation edge nodes.
- **FR-002**: The drone simulation MUST utilize the ROS 2 (Humble), PX4, and Gazebo stack as defined in the `dotness/Drone-Swarm` repository.
- **FR-003**: The simulation containers MUST include the MicroXRCEAgent to bridge ROS 2 and PX4 telemetry.
- **FR-004**: The edge flight controller service MUST interface with the local simulated ROS 2/PX4 environment (e.g., via MAVSDK to the SITL UDP port) instead of expecting physical hardware.
- **FR-005**: The edge vision service MUST connect to the Gazebo simulated camera topic/feed instead of a physical Pi Camera.
- **FR-006**: The local simulation MUST NOT require manual setup of the Raspberry Pi OS or physical network configurations.

### Key Entities

- **Simulated Edge Node**: A Docker container running the edge API, flight controller, and vision system, connected to the local Gazebo simulation rather than real hardware.
- **Gazebo Environment**: The 3D physics simulation world rendering the Holybro X500 drone.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can launch the entire ecosystem (dashboard, backend, 1 simulated drone) using a single `docker compose up -d` command in under 5 minutes (post-build).
- **SC-002**: The dashboard successfully displays real-time telemetry (at least 5 Hz) sourced from the simulation physics.
- **SC-003**: A SMEAC order submitted from the dashboard successfully commands the SITL drone to take off and navigate to a designated waypoint in the simulation.
- **SC-004**: System behavior is identical regardless of whether running against the simulation or physical hardware, without relying on mock data generation.

## Assumptions

- The host machine running the simulation has sufficient resources (CPU/RAM/GPU) to run Gazebo and multiple Docker containers simultaneously.
- If using Windows, WSL2 with mirrored networking and GPU passthrough (NVIDIA Container Toolkit) is correctly configured per the `Drone-Swarm` README.
- The `Drone-Swarm` Dockerfile and dependencies can be integrated or pulled into the Intent-Swarm-Commander infrastructure.
