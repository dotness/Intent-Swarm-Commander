# Quickstart: End-to-End Production Flight (`008-e2e-prod-flight`)

## 1. Bring up the full stack (including headless PX4 SITL `drone_sim`)
```bash
docker compose up -d --build
docker compose ps
```

## 2. Verify PX4 SITL → MAVSDK → MQTT live telemetry
```bash
curl -s http://localhost:8090/telemetry
```

## 3. Run zero-mock Playwright production flight E2E test
```bash
COMMANDER_PASSPHRASE=commander-test-passphrase npx playwright test tests/e2e/prod_flight.spec.js
```

## 4. Run full regression suites
```bash
COMMANDER_PASSPHRASE=test-commander-passphrase GEMINI_API_KEY=test-gemini-key .venv/bin/pytest -v
COMMANDER_PASSPHRASE=commander-test-passphrase npx playwright test
```
