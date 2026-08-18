# Quickstart: Local Docker Simulation Validation

This document outlines the validation scenarios to prove the simulation environment successfully orchestrates the E2E lifecycle of the application.

## Prerequisites
- Docker Engine installed.
- (If Windows) WSL2 with NVIDIA Container Toolkit for Gazebo GPU passthrough.

## Setup
```bash
# Start the entire local ecosystem in the background
docker compose up -d

# Verify all containers are running
docker compose ps
```

## Validation Scenarios

### Scenario 1: Backend and Dashboard Connectivity
1. Navigate to `http://localhost:8080` in your web browser.
2. Log in using standard credentials.
3. Observe that the Dashboard successfully communicates with the API at `localhost:8000`.

### Scenario 2: Gazebo Simulation Validation
1. If running on a desktop UI (or WSLg on Windows), verify the Gazebo 3D simulation window has appeared on the host, showing the X500 drone model.
2. Check the edge drone's connection to the PX4 SITL physics engine:
   ```bash
   docker compose logs edge_drone
   ```
   **Expected**: The edge API logs indicate a successful MAVSDK connection on UDP port `14540`.

### Scenario 3: Real-Time E2E Telemetry
1. Submit a SMEAC order via the dashboard.
2. Observe the Gazebo 3D simulation; the drone should arm, take off, and maneuver.
3. Observe the dashboard telemetry panel; it should display real-time metrics (altitude, battery) matching the drone in Gazebo.

## Teardown
```bash
docker compose down -v
```
