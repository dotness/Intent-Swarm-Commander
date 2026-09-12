// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { MapComponent } = require('./pages/MapComponent');
const { VALID_COMMANDER } = require('./fixtures/credentials');

test.describe('User Story 2: Swarm Discovery & Real-Time Telemetry Mapping', () => {
  /** @type {LoginPage} */
  let loginPage;
  /** @type {DashboardPage} */
  let dashboardPage;
  /** @type {MapComponent} */
  let mapComponent;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    mapComponent = new MapComponent(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated();
  });

  test('T013: should populate swarm dropdown with swarms retrieved from API', async () => {
    const options = await dashboardPage.getSwarmOptions();
    expect(options.length).toBeGreaterThan(1);
    // At least one swarm option exists beyond the placeholder
    const swarmNames = options.join(' ');
    expect(swarmNames).toMatch(/swarm|drone|alpha|bravo/i);
  });

  test('T013b: should provision a new swarm via the "+ New Swarm" dialog and auto-select it', async ({ page }) => {
    const newSwarmName = `Echo Patrol Swarm ${Date.now()}`;
    const droneCount = 3;

    // Verify Create Swarm button is visible
    await expect(dashboardPage.createSwarmBtn).toBeVisible();

    // Click "+ New Swarm" to open the provision modal
    await dashboardPage.createSwarmBtn.click();
    await expect(dashboardPage.createSwarmModal).toBeVisible();

    // Fill in the swarm creation form
    await dashboardPage.createSwarmNameInput.fill(newSwarmName);
    await dashboardPage.createSwarmDronesInput.fill(String(droneCount));

    // Submit the form and wait for the POST request
    const createPromise = page.waitForResponse(
      (res) => res.url().includes('/api/v1/swarms') && res.request().method() === 'POST' && res.status() === 201
    );
    await dashboardPage.createSwarmSubmitBtn.click();
    await createPromise;

    // Modal should close upon successful creation
    await expect(dashboardPage.createSwarmModal).toBeHidden();

    // Swarm selector should now contain and select the new swarm
    await expect(dashboardPage.swarmSelect).toContainText(newSwarmName);
    const selectedOption = await dashboardPage.swarmSelect.locator('option:checked').textContent();
    expect(selectedOption).toContain(newSwarmName);

    // Verify activity history logged the creation
    await dashboardPage.expectHistoryContains(newSwarmName);
  });

  test('T014: should trigger telemetry polling upon selecting an active swarm', async ({ page }) => {
    // Listen for telemetry API requests
    const telemetryPromise = page.waitForRequest(
      req => req.url().includes('/telemetry') && req.method() === 'GET',
      { timeout: 10000 }
    );

    await dashboardPage.selectFirstAvailableSwarm();
    const telemetryRequest = await telemetryPromise;
    expect(telemetryRequest.url()).toContain('/api/v1/swarms/');
  });

  test('T015: should initialize Leaflet map and render drone markers', async () => {
    await mapComponent.expectMapLoaded();
    await dashboardPage.selectFirstAvailableSwarm();

    // Check that drone markers appear on the tactical map
    await mapComponent.expectDroneMarkers(1);
  });
});
