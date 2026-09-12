# Research: Playwright End-to-End Test Suite

**Feature Directory**: `specs/004-playwright-e2e-tests`
**Date**: 2026-09-12

## Research Findings & Technical Decisions

### 1. Test Runner & Framework Selection
- **Decision**: Use `@playwright/test` running on Node.js (v22.22.1 is already installed on the host).
- **Rationale**:
  - `@playwright/test` is the industry standard for fast, reliable browser automation with auto-waiting, built-in assertion retries, and cross-browser support.
  - Native support for headless Chromium on Linux without needing an X11 server (via `--headless`).
  - Provides rich debugging tools: HTML reporter, video recordings, screenshots on failure, and trace viewer.
  - Simple package.json configuration at project root with minimal footprint.

### 2. Live Environment Verification vs Mocking
- **Decision**: Test directly against the live container stack (`http://localhost:8080` for dashboard and `http://localhost:8000` for backend microservices).
- **Rationale**:
  - The project already runs `isc_postgres`, `isc_temporal`, `isc_backend`, `isc_dashboard`, and `isc_edge` in Docker.
  - End-to-end tests must validate real HTTP communication, JWT issuance/validation, CORS headers, Leaflet map DOM rendering, and database persistence.
  - Tests will use seeded or dynamically generated test entities that avoid colliding with production state.

### 3. Page Object Model (POM) Architecture
- **Decision**: Structure tests into modular Page Objects under `tests/e2e/pages/`:
  - `LoginPage.js` / `.ts`: Controls login modal interactions, credentials input, submission, and validation error assertions.
  - `DashboardPage.js` / `.ts`: Controls topbar, authentication badge status, and swarm selector dropdown.
  - `MapComponent.js` / `.ts`: Inspects Leaflet map canvas and `.leaflet-marker-icon` DOM elements for drone visualization.
  - `SmeacOrderPage.js` / `.ts`: Manages Situation, Mission, Execution, Administration, Command textareas and submission.
  - `HitlModalPage.js` / `.ts`: Manages detection, content assertions, and Approve/Reject clicks for High-Impact human-in-the-loop decisions.

### 4. Leaflet Map DOM Inspection Strategy
- **Decision**: Query Leaflet markers via CSS selectors:
  - Container: `#map.leaflet-container`
  - Marker pane: `.leaflet-pane.leaflet-marker-pane`
  - Markers: `.leaflet-marker-icon`
  - Popup pane: `.leaflet-popup-content`
- **Auto-wait Handling**: Telemetry polling interval is 2000ms. Playwright's `expect(locator).toBeVisible()` automatically waits up to 5000ms for markers to appear after swarm selection.

### 5. HITL Dynamic Verification Flow
- **Decision**: For HITL modal testing, create a test utility or API helper in the test suite that seeds a high-impact action or triggers a pending decision (e.g., via backend API `/api/v1/swarms/{id}/orders` with high-risk parameters or direct HITL decision insertion), then verifies the modal appears in the UI and responds to Approve/Reject.

### 6. Failure Artifacts & CI Execution
- **Artifacts**:
  - HTML report in `playwright-report/`
  - Screenshots on failure in `test-results/`
  - Video recordings retained on first retry or failure
  - Console trace files on failure
