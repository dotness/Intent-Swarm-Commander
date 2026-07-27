# Phase 0: Outline & Research

## Decision 1: Orchestration Framework
- **Decision:** Docker Compose
- **Rationale:** The MVP requires a lightweight, reproducible environment to spin up Postgres, Temporal, multiple Python FastAPI microservices, and a complex robotics simulation stack simultaneously on a developer's machine. Docker Compose perfectly fits this requirement for local E2E testing without the overhead of Kubernetes.
- **Alternatives considered:** Minikube/K3s (too much overhead for a local MVP), manual script orchestration (fragile and prone to "works on my machine" errors).

## Decision 2: Robotics Simulation Stack
- **Decision:** ROS 2 (Humble) + PX4 + Gazebo (SITL) based on `dotness/Drone-Swarm`
- **Rationale:** Standardizing on this stack aligns with industry best practices for drone development. Gazebo provides accurate physics, PX4 handles flight dynamics, and ROS 2 provides the middleware for telemetry and control. Using the `dotness/Drone-Swarm` Dockerfile jumpstarts the environment.
- **Alternatives considered:** ArduPilot SITL (PX4 chosen for better MAVSDK integration compatibility in this specific stack), Webots (Gazebo is more deeply integrated with ROS 2 and PX4).

## Decision 3: Edge Python Service Integration
- **Decision:** Run the Python edge API within the Drone-Swarm Gazebo container (or a sibling container sharing network) to interface via `localhost:14540` (MAVSDK UDP).
- **Rationale:** Keeps the networking simple. The MicroXRCEAgent bridges the PX4 uORB topics to ROS 2 topics, while MAVSDK connects to the PX4 SITL UDP port directly.
- **Alternatives considered:** Bridging the SITL UDP port out to the host (complex Docker networking configurations on Windows/WSL2).

## Decision 4: Edge Vision Service Simulation
- **Decision:** Consume the ROS 2 `/camera/image_raw` topic using a python `rclpy` subscriber in `src/edge/vision/camera.py`.
- **Rationale:** The Gazebo SITL environment publishes simulated camera streams to ROS 2 topics. Using `rclpy` allows the vision system to ingest real physical simulation frames instead of generating mock colored frames.
- **Alternatives considered:** GStreamer UDP streams (Gazebo natively supports ROS 2 topics out of the box in this stack, avoiding additional GStreamer plugin dependencies).
