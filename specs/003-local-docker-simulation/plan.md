# Implementation Plan: Local Docker Compose Simulation

**Branch**: `003-local-docker-simulation` | **Date**: 2026-07-27 | **Spec**: [spec.md](file:///home/remi/Projects/Intent-Swarm-Commander/specs/003-local-docker-simulation/spec.md)

**Input**: Feature specification from `/specs/003-local-docker-simulation/spec.md`

## Summary

Integrate the ROS 2, PX4, and Gazebo simulation stack from `dotness/Drone-Swarm` into a `docker-compose.yml` environment. This orchestrates the entire Intent-Swarm-Commander system locally (backend, dashboard, Temporal) alongside simulated edge drones, allowing rapid E2E testing without physical Raspberry Pi 5 hardware.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Docker, Docker Compose, ROS 2 (Humble), PX4, Gazebo, FastAPI, MAVSDK

**Storage**: PostgreSQL

**Testing**: pytest

**Target Platform**: Linux / WSL2 (with NVIDIA GPU passthrough for Gazebo)

**Project Type**: Microservices + Robotics Simulation

**Performance Goals**: Minimum 5 Hz telemetry throughput from Gazebo; all containers launch in under 5 minutes.

**Constraints**: Must run entirely via `docker compose` with no manual host configurations (aside from standard WSL2/Docker setup).

**Scale/Scope**: 1 Backend Stack + 1 Simulated Edge Drone.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. LTV Framework (Node Alignment)**: Anchored directly to target Node Point `MINT_UAV_Simulation_Validation` (Q1-Q2 2027 milestone). Simulating the drone tech stack (ROS 2, PX4, Gazebo) is a mandatory convergence gateway to iterate toward the TO-BE physical edge swarm without hardware friction.
- **II. Cynefin Domain**: Complicated domain. The physical constraints are abstracted into a simulation model, enabling backward planning.
- **III. OODA Loops**: A local simulation drastically reduces the cycle time for the "Act" and "Observe" phases of local development loops.
- **IV. False Cones**: Standardizing on open ROS 2 / PX4 interfaces protects the architecture from vendor lock-in and corporate hardware hype.
- **V. Script Organization and Modularity**: All simulation startup and entrypoint helpers (`scripts/entrypoint_drone.sh`) reside strictly in `scripts/`, preserving root modularity.
- **Architecture Standards**: Implementation design and code must be reviewed and verified by `.agents/agents/uservice-arch-reviewer`.

## Project Structure

### Documentation (this feature)

```text
specs/003-local-docker-simulation/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
# Single Repository with Docker orchestration
src/
├── dashboard/
├── edge/
└── uservice/

scripts/
└── entrypoint_drone.sh

docker-compose.yml
Dockerfile.backend
Dockerfile.drone_sim
```

**Structure Decision**: Utilizing the existing monorepo structure, we will introduce `docker-compose.yml` at the project root. We will adapt the `Drone-Swarm` Dockerfile as `Dockerfile.drone_sim` to build the simulation node.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No constitutional violations identified. Design conforms strictly to all principles.*
