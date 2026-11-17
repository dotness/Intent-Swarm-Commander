# Quickstart: Fly-and-Detect E2E (`009-fly-detect-e2e`)

1. Start the full stack including `virtual_cam`:
   ```bash
   docker compose up -d --build
   ```
2. (Optional) Watch the live virtual camera feed in your browser:
   - Open `http://localhost:8091/stream`
   - To feed a custom video file, set `VIRTUAL_VIDEO_PATH=/path/in/container/video.mp4` on `virtual_cam` in `docker-compose.yml`.
3. Run unit & integration tests:
   ```bash
   .venv/bin/pytest -v
   ```
4. Run the zero-mock Fly-and-Detect E2E test:
   ```bash
   COMMANDER_PASSPHRASE=commander-test-passphrase npx playwright test tests/e2e/prod_fly_detect.spec.js --reporter=list
   ```
