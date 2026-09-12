# Tasks: Playwright End-to-End Test Suite

**Feature Directory**: `specs/004-playwright-e2e-tests`
**Specification**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Phase 1: Setup & Environment Initialization

- [X] T001: Initialize Node.js dependencies and install `@playwright/test` in [package.json](../../package.json)
- [X] T002: Install Playwright Chromium headless browser binary via `npx playwright install chromium`
- [X] T003: Configure Playwright configuration file in [playwright.config.js](../../playwright.config.js) with `baseURL: http://localhost:8080`, timeout settings, HTML reporter, and failure trace captures

## Phase 2: Foundational Page Objects & Fixtures

- [X] T004: Create test credentials and SMEAC payload fixtures in [tests/e2e/fixtures/credentials.js](../../tests/e2e/fixtures/credentials.js) and [tests/e2e/fixtures/smeac-data.js](../../tests/e2e/fixtures/smeac-data.js)
- [X] T005: Implement `LoginPage` Page Object Model in [tests/e2e/pages/LoginPage.js](../../tests/e2e/pages/LoginPage.js)
- [X] T006: Implement `DashboardPage` Page Object Model in [tests/e2e/pages/DashboardPage.js](../../tests/e2e/pages/DashboardPage.js)
- [X] T007: Implement `MapComponent` Page Object Model in [tests/e2e/pages/MapComponent.js](../../tests/e2e/pages/MapComponent.js)
- [X] T008: Implement `SmeacPage` Page Object Model in [tests/e2e/pages/SmeacPage.js](../../tests/e2e/pages/SmeacPage.js)
- [X] T009: Implement `HitlPage` Page Object Model in [tests/e2e/pages/HitlPage.js](../../tests/e2e/pages/HitlPage.js)

## Phase 3: User Story 1 — Commander Authentication & Session Lifecycle (P1)

- [X] T010: Implement invalid credentials rejection test in [tests/e2e/auth.spec.js](../../tests/e2e/auth.spec.js)
- [X] T011: Implement successful commander login test verifying modal dismissal and auth badge update in [tests/e2e/auth.spec.js](../../tests/e2e/auth.spec.js)
- [X] T012: Implement session persistence test across browser page reload in [tests/e2e/auth.spec.js](../../tests/e2e/auth.spec.js)

## Phase 4: User Story 2 — Swarm Discovery & Real-Time Telemetry Mapping (P2)

- [X] T013: Implement swarm dropdown population test verifying swarm options from backend in [tests/e2e/telemetry.spec.js](../../tests/e2e/telemetry.spec.js)
- [X] T014: Implement swarm selection and telemetry polling test in [tests/e2e/telemetry.spec.js](../../tests/e2e/telemetry.spec.js)
- [X] T015: Implement Leaflet map marker rendering verification for active drones in [tests/e2e/telemetry.spec.js](../../tests/e2e/telemetry.spec.js)

## Phase 5: User Story 3 — Tactical SMEAC Order Composition & Dispatch (P3)

- [X] T016: Implement HTML5 form validation test for empty SMEAC fields in [tests/e2e/smeac.spec.js](../../tests/e2e/smeac.spec.js)
- [X] T017: Implement full SMEAC order composition and dispatch test with order confirmation assertion in [tests/e2e/smeac.spec.js](../../tests/e2e/smeac.spec.js)

## Phase 6: User Story 4 — Human-in-the-Loop (HITL) Safety Gate (P4)

- [X] T018: Implement pending HITL decision detection and modal display test in [tests/e2e/hitl.spec.js](../../tests/e2e/hitl.spec.js)
- [X] T019: Implement HITL decision approval workflow test asserting state resolution in [tests/e2e/hitl.spec.js](../../tests/e2e/hitl.spec.js)
- [X] T020: Implement HITL decision rejection workflow test asserting state resolution in [tests/e2e/hitl.spec.js](../../tests/e2e/hitl.spec.js)

## Phase 7: User Story 5 — Resiliency & Error Handling (P5)

- [X] T021: Implement unauthorized API rejection and session expiry handling test in [tests/e2e/resilience.spec.js](../../tests/e2e/resilience.spec.js)
- [X] T022: Implement network error handling and graceful degradation test in [tests/e2e/resilience.spec.js](../../tests/e2e/resilience.spec.js)

## Phase 8: Verification & Execution

- [X] T023: Execute the complete Playwright test suite against running containers via `npx playwright test`
- [X] T024: Validate test reports, traces, and verify 100% test pass rate
