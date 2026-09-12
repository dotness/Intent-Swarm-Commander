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
