// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { MapComponent } = require('./pages/MapComponent');
const { VALID_COMMANDER } = require('./fixtures/credentials');

test.describe('Tactical Navigation & Map Visualization: Point A to Point B Swarm Movement', () => {
  /** @type {LoginPage} */
  let loginPage;
  /** @type {DashboardPage} */
  let dashboardPage;
  /** @type {SmeacPage} */
  let smeacPage;
  /** @type {MapComponent} */
  let mapComponent;

  test('should create a swarm, order movement from Point A to Point B, and observe drone move on the tactical map', async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    smeacPage = new SmeacPage(page);
    mapComponent = new MapComponent(page);

    // Geographic coordinates for Point A (e.g. Berlin Alexanderplatz) and Point B (e.g. Prenzlauer Berg)
    const pointA = { lat: 52.5200, lng: 13.4050, alt_m: 50 };
    const pointB = { lat: 52.5350, lng: 13.4200, alt_m: 80 };

    // Mutable state for the telemetry stream
    let currentDronePosition = { ...pointA };
    let currentMission = 'holding_at_point_a';

    // Intercept telemetry polling so we can stream realistic positional updates to the map with CORS headers
    await page.route('**/api/v1/swarms/*/telemetry', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({
          status: 204,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          },
        });
        return;
      }

      const url = route.request().url();
      const swarmIdMatch = url.match(/\/swarms\/([^/]+)\/telemetry/);
      const swarmId = swarmIdMatch ? swarmIdMatch[1] : 'nav-swarm-01';

      await route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Headers': '*',
        },
        contentType: 'application/json',
        body: JSON.stringify({
          drones: [
            {
              id: `${swarmId}-lead-drone`,
              status: currentMission.includes('arrived') ? 'holding' : (currentMission.includes('transit') ? 'in_transit' : 'active'),
              battery_pct: currentMission.includes('arrived') ? 91 : 98,
              position: {
                lat: currentDronePosition.lat,
                lng: currentDronePosition.lng,
                alt_m: currentDronePosition.alt_m,
              },
              heading: 45,
              speed: currentMission.includes('transit') ? 15.0 : 0.0,
              current_mission: currentMission,
            },
          ],
        }),
      });
    });

    const SCREENSHOT_DIR = '/home/remi/.gemini/antigravity-ide/brain/3ed699e0-203d-43df-9568-348fd78eefab/screenshots';

    // ── Step 1: Login to Dashboard ──────────────────────────────────────────
    console.log('>>> [TEST] Starting Step 1: Login');
    await loginPage.goto();
    await loginPage.expectModalVisible();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated();
    await mapComponent.expectMapLoaded();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step1_dashboard_authenticated.png` });
    console.log('>>> [TEST] Step 1 complete: Authenticated');

    // ── Step 2: Create a New Swarm ──────────────────────────────────────────
    console.log('>>> [TEST] Starting Step 2: Provision Swarm');
    const swarmName = `Vector Navigation Swarm ${Date.now()}`;
    await dashboardPage.provisionSwarm(swarmName, 3);
    await expect(dashboardPage.swarmSelect).toContainText(swarmName);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step2_swarm_provisioned.png` });
    console.log('>>> [TEST] Step 2 complete: Swarm provisioned');

    // ── Step 3: Observe Swarm at Initial Position (Point A) on Tactical Map ──
    console.log('>>> [TEST] Starting Step 3: Check Point A on Map');
    await mapComponent.expectDroneMarkers(1);
    await mapComponent.expectDroneAt(pointA.lat, pointA.lng);

    // Click marker to verify telemetry popup displays Point A data
    await mapComponent.clickDroneMarker(0);
    await expect(mapComponent.popupContent).toContainText('holding_at_point_a');
    await expect(mapComponent.popupContent).toContainText(`Alt: ${pointA.alt_m}m`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step3_point_a_marker.png` });
    console.log('>>> [TEST] Step 3 complete: Point A verified on Map');

    // ── Step 4: Issue Order to Move Swarm from Point A to Point B ───────────
    console.log('>>> [TEST] Starting Step 4: Issue Order');
    const moveOrder = {
      situation: `Swarm positioned at Point A (${pointA.lat}, ${pointA.lng}). High-value objective detected at Point B (${pointB.lat}, ${pointB.lng}).`,
      mission: `Relocate swarm from Point A to Point B (${pointB.lat}, ${pointB.lng}).`,
      execution: `Transit from Point A [${pointA.lat}, ${pointA.lng}] to Point B [${pointB.lat}, ${pointB.lng}] at cruising altitude ${pointB.alt_m}m AGL.`,
      administration: 'Automated return-to-base if battery falls below 20%.',
      command: 'Commander Alpha directing vector navigation on channel Delta-4.'
    };

    await smeacPage.fillOrder(moveOrder);
    await smeacPage.submit();
    console.log('>>> [TEST] Step 4 complete: Order submitted');

    // ── Step 5: Verify Order Submitted & Flight Corridor Displayed on Map ───
    console.log('>>> [TEST] Starting Step 5: Verify Order Execution');
    await smeacPage.expectSuccess();
    await smeacPage.expectExecuted();
    const orderId = await smeacPage.getSubmittedOrderId();
    expect(orderId).toBeTruthy();
    if (orderId) {
      await dashboardPage.expectHistoryContains(orderId);
    }

    // Tactical map renders the target flight trajectory between Point A and Point B
    await mapComponent.expectTargetAreaLayerVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step4_order_flight_path.png` });
    console.log('>>> [TEST] Step 5 complete: Flight path visible on map');

    // ── Step 6: Swarm En-Route (Simulate In-Transit Telemetry) ───────────────
    console.log('>>> [TEST] Starting Step 6: In-transit');
    currentDronePosition = { lat: 52.5275, lng: 13.4125, alt_m: 65 };
    currentMission = 'in_transit_to_point_b';

    // Drone marker moves to waypoint on the map
    await mapComponent.expectDroneAt(52.5275, 13.4125);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step5_in_transit_marker.png` });
    console.log('>>> [TEST] Step 6 complete: In-transit position verified');

    // ── Step 7: Swarm Arrives at Point B (Observe on Tactical Map) ──────────
    console.log('>>> [TEST] Starting Step 7: Arrived at Point B');
    currentDronePosition = { ...pointB };
    currentMission = 'arrived_at_point_b';

    // Verify drone marker on map has updated to Point B coordinates
    await mapComponent.expectDroneAt(pointB.lat, pointB.lng);

    // Click marker to verify updated popup details at Point B
    await mapComponent.clickDroneMarker(0);
    await expect(mapComponent.popupContent).toContainText('arrived_at_point_b');
    await expect(mapComponent.popupContent).toContainText(`Alt: ${pointB.alt_m}m`);

    // Verify unit roster table also reflects arrival at Point B
    const rosterRow = page.locator('#roster-body tr').first();
    await expect(rosterRow).toContainText('arrived_at_point_b');
    await page.screenshot({ path: `${SCREENSHOT_DIR}/step6_point_b_arrived.png` });
    console.log('>>> [TEST] Step 7 complete: All assertions passed!');
  });
});
