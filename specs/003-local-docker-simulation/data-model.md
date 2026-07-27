# Data Model: Local Docker Simulation

## Entities

There are no new database entities introduced in this feature. This feature strictly focuses on orchestration and infrastructure simulation.

### Simulated Edge Node
A virtualized instance of the drone edge hardware.
- **Attributes:**
  - `container_id`: Docker container UUID.
  - `simulation_mode`: Set to `true` to ensure fallbacks are appropriately bypassed and the system connects to the SITL physics engine.
- **Relationships:**
  - One-to-one with the Gazebo Physics Engine.

### Gazebo Physics Engine
The environment providing realistic physics for the SITL drone.
- **Attributes:**
  - `world`: The simulated physics environment.
  - `vehicle`: Holybro X500 drone simulation model.
- **State Transitions:**
  - Boot -> Physics Active -> Receives PX4 SITL UDP packets -> Drone Moves in 3D Space.
