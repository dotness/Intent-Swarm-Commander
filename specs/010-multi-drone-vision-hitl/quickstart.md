# Quickstart: Multi-Drone Vision & HITL Snapshots (`010-multi-drone-vision-hitl`)

1. Start/rebuild stack:
   ```bash
   docker compose up -d --build
   ```
2. Control individual drone feeds (e.g. `drone-1` vs `drone-3` out of 5 drones):
   ```bash
   curl -X POST http://localhost:8091/feed/drone-1 -d '{"mode":"clear"}'
   curl -X POST http://localhost:8091/feed/drone-3 -d '{"mode":"target"}'
   ```
3. Watch any drone live in browser or ISC Dashboard (`http://localhost:8080` → **Drone Vision & Snapshots** panel):
   - Direct stream: `http://localhost:8091/stream/drone-3`
4. Run tests:
   ```bash
   .venv/bin/pytest -v
   COMMANDER_PASSPHRASE=commander-test-passphrase npx playwright test tests/e2e/multi_drone_vision_hitl.spec.js --reporter=list
   ```
