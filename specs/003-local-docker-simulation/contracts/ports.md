# Port Contracts

This file defines the networking mapping utilized by the Docker Compose orchestration to ensure no collisions occur on the host machine.

- **8000**: Intent-Swarm-Commander Backend (FastAPI uvicorn)
- **8080**: Intent-Swarm-Commander Dashboard (HTTP Server)
- **5432**: PostgreSQL Database
- **7233**: Temporal Server (Frontend)
- **14540**: MAVSDK UDP Port (Simulation)
- **8888**: MicroXRCEAgent UDP Port (ROS 2 Bridge)
