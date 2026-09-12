# Quickstart: Running Playwright End-to-End Tests

**Feature Directory**: `specs/004-playwright-e2e-tests`
**Date**: 2026-09-12

## Prerequisites

1. Node.js v20+ or v22+ installed on the host.
2. The Intent Swarm Commander Docker stack running:
   ```bash
   docker compose ps
   ```
   Ensure `isc_backend` (port 8000) and `isc_dashboard` (port 8080) are healthy and reachable.

## Running Tests

### 1. Run all E2E tests headless:
```bash
npm test
```
or
```bash
npx playwright test
```

### 2. Run specific test file:
```bash
npx playwright test tests/e2e/auth.spec.js
npx playwright test tests/e2e/telemetry.spec.js
npx playwright test tests/e2e/smeac.spec.js
npx playwright test tests/e2e/hitl.spec.js
```

### 3. Run in headed mode (view browser during tests):
```bash
npx playwright test --headed
```

### 4. Run with UI Mode (interactive test runner):
```bash
npx playwright test --ui
```

### 5. View Test Report:
```bash
npx playwright show-report
```
