# Implementation Plan: Playwright End-to-End Test Suite

**Branch**: `main` | **Date**: 2026-09-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-playwright-e2e-tests/spec.md`

## Summary

Build a comprehensive automated End-to-End (E2E) testing framework using `@playwright/test` for Intent Swarm Commander. The suite exercises the live dashboard (`http://localhost:8080`) and backend microservice (`http://localhost:8000`) across all core operational workflows: Commander Authentication & Session Lifecycle, Swarm Discovery & Telemetry Mapping, SMEAC Order Composition & Dispatch, Human-In-The-Loop (HITL) Critical Decision Safety Gates, and Network/Security Error Resilience.

## Technical Context

**Language/Version**: JavaScript / Node.js v22.22.1

**Primary Dependencies**: `@playwright/test` (^1.48.0)

**Storage**: Local file reports (`playwright-report/`, `test-results/`), browser `sessionStorage`

**Testing**: Playwright test runner (`npx playwright test`), headless & headed Chromium

**Target Platform**: Linux (Ubuntu x86_64 host), container network (`localhost:8080`, `localhost:8000`)

**Project Type**: Web Application End-to-End Test Suite

**Performance Goals**: Full suite runs in under 45 seconds; individual test assertions < 5 seconds

**Constraints**: Must test against running live container stack without mocks; must execute in headless CI/CD

**Scale/Scope**: 5 spec test suites (`auth.spec.js`, `telemetry.spec.js`, `smeac.spec.js`, `hitl.spec.js`, `resilience.spec.js`) covering 15 functional requirements.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Cone of Uncertainty & LTV)**: PASS. Aligned with Node Points `EMA_JIT_Identity_Infrastructure` and `HITL_Elicitation_Operational`. Validates real-world integration of identity and safety gates.
- **Principle II (Cynefin Domain Assessment)**: PASS. Domain assessed and logged as "Complicated" (`python3 .agents/skills/cynefin-domain-assessor/scripts/assess_domain.py`).
- **Principle III (Execution via OODA Loops)**: PASS. Broken into modular Page Objects and test specifications.
- **Principle IV (Guard Against False Cones)**: PASS. Uses established, industry-standard `@playwright/test` without unvetted hype libraries.
- **Principle V (Script Organization)**: PASS. Test helper and setup scripts placed under `scripts/` or `tests/e2e/`.

## Project Structure

### Documentation (this feature)

```text
specs/004-playwright-e2e-tests/
├── plan.md              # This implementation plan
├── research.md          # Technical decisions and framework selection
├── data-model.md        # Page Object Models and test data fixtures
├── quickstart.md        # Execution guide and commands
├── contracts/
│   └── dashboard-api-contract.md # Endpoints exercised by E2E suite
└── tasks.md             # Ordered task breakdown (/speckit-tasks output)
```

### Source Code Layout

```text
package.json             # Root package.json defining @playwright/test and test scripts
playwright.config.js     # Playwright configuration (baseURL, reporters, timeouts, projects)
tests/
└── e2e/
    ├── fixtures/
    │   ├── credentials.js   # Commander test credentials
    │   └── smeac-data.js    # Standard and high-impact SMEAC payloads
    ├── pages/
    │   ├── LoginPage.js     # Modal auth interactions
    │   ├── DashboardPage.js # Topbar, badge, swarm dropdown
    │   ├── MapComponent.js  # Leaflet map container & drone markers
    │   ├── SmeacPage.js     # SMEAC order form
    │   └── HitlPage.js      # HITL approval dialog
    ├── auth.spec.js         # User Story 1 tests
    ├── telemetry.spec.js    # User Story 2 tests
    ├── smeac.spec.js        # User Story 3 tests
    ├── hitl.spec.js         # User Story 4 tests
    └── resilience.spec.js   # User Story 5 tests
```

## Verification Plan

### Automated Execution
1. Install dependencies: `npm install -D @playwright/test` and `npx playwright install chromium`.
2. Run full test suite: `npx playwright test`.
3. Verify all test suites pass with 0 failures.
4. Verify HTML report generation: `playwright-report/index.html`.
