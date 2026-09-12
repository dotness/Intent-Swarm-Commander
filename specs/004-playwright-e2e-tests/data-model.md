# Data Model: Playwright End-to-End Test Suite

**Feature Directory**: `specs/004-playwright-e2e-tests`
**Date**: 2026-09-12

## Page Object Models (POM) & Component Abstractions

### 1. `LoginPage`
- **Target**: `#login-modal`
- **Fields**:
  - `commanderInput`: `input#login-commander-id`
  - `passphraseInput`: `input#login-passphrase`
  - `submitButton`: `button[type="submit"]`
  - `errorMessage`: `#login-error`
- **Methods**:
  - `goto()`: Navigates to dashboard root URL.
  - `login(commanderId, passphrase)`: Fills in credentials and clicks Authenticate.
  - `expectModalVisible()`: Asserts modal is displayed and not hidden.
  - `expectModalHidden()`: Asserts modal is closed (`display: none` or `.hidden`).
  - `expectErrorMessage(expectedText)`: Asserts error message text.

### 2. `DashboardPage`
- **Target**: `.topbar`, `.dashboard`
- **Fields**:
  - `authIndicator`: `#auth-indicator`
  - `authBadge`: `.auth-badge`
  - `swarmSelect`: `select#swarm-select`
- **Methods**:
  - `expectAuthenticated(agentId)`: Checks auth badge contains `Auth: agent-...`.
  - `expectUnauthenticated()`: Checks auth badge shows `Not Authenticated`.
  - `getSwarmOptions()`: Returns array of available swarm options.
  - `selectSwarm(swarmId)`: Selects a swarm from the dropdown.

### 3. `MapComponent`
- **Target**: `#map`
- **Fields**:
  - `mapContainer`: `#map.leaflet-container`
  - `markerPane`: `.leaflet-marker-pane`
  - `markers`: `.leaflet-marker-icon`
  - `popups`: `.leaflet-popup-content`
- **Methods**:
  - `expectMapInitialized()`: Checks Leaflet container has loaded tile layers.
  - `expectDroneMarkers(minCount)`: Asserts at least `minCount` markers are present on map.
  - `clickMarker(index)`: Clicks a drone marker to open telemetry popup.

### 4. `SmeacOrderPage`
- **Target**: `#smeac-panel`
- **Fields**:
  - `situationInput`: `#smeac-situation`
  - `missionInput`: `#smeac-mission`
  - `executionInput`: `#smeac-execution`
  - `adminInput`: `#smeac-admin`
  - `commandInput`: `#smeac-command`
  - `submitButton`: `#smeac-form button[type="submit"]`
  - `statusMessage`: `#smeac-status`
- **Methods**:
  - `fillOrder({ situation, mission, execution, administration, command })`: Fills order fields.
  - `submitOrder()`: Submits the form.
  - `expectSuccessMessage()`: Validates order submission acknowledgement.

### 5. `HitlModalPage`
- **Target**: `#hitl-modal`
- **Fields**:
  - `modalDialog`: `dialog#hitl-modal`
  - `modalTitle`: `.hitl-modal__title`
  - `modalBody`: `#hitl-modal-body`
  - `approveButton`: `#hitl-approve`
  - `rejectButton`: `#hitl-reject`
- **Methods**:
  - `expectDecisionPrompt(textSnippet)`: Waits for dialog to open with action details.
  - `approve()`: Clicks Approve.
  - `reject()`: Clicks Reject.
  - `expectClosed()`: Asserts dialog is no longer open.

---

## Test Data Fixtures

### 1. Authentication Credentials
- `VALID_USER`: `{ commanderId: "commander-alpha", passphrase: "dev_passphrase" }`
- `INVALID_USER`: `{ commanderId: "commander-alpha", passphrase: "wrong_password_123" }`

### 2. SMEAC Order Payloads
- `STANDARD_SMEAC`:
  ```json
  {
    "situation": "Enemy surveillance drones detected in sector 4.",
    "mission": "Deploy defensive patrol perimeter at 100m AGL.",
    "execution": "Alpha squad sweep North to South, Bravo squad hold perimeter.",
    "administration": "Standard battery swap at FOB Bravo every 45 mins.",
    "command": "Commander Alpha on primary comms channel 4."
  }
  ```
- `HIGH_RISK_SMEAC`:
  ```json
  {
    "situation": "Hostile drone swarm approaching civilian exclusion zone.",
    "mission": "AUTHORIZE KINETIC INTERCEPTION AND ROE ESCALATION.",
    "execution": "Immediate kinetic neutralization sequence.",
    "administration": "Emergency munitions authorization Code Red.",
    "command": "Tactical Commander Alpha."
  }
  ```
