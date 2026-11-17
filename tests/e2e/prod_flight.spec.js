// @ts-check
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { MapComponent } = require('./pages/MapComponent');
const { VALID_COMMANDER } = require('./fixtures/credentials');

const SCREENSHOT_DIR =
  process.env.E2E_SCREENSHOT_DIR ||
  '/home/remi/.gemini/antigravity/brain/90c79937-29f7-4eda-8263-b3f41aab8025/screenshots';

/**
 * Compute great-circle distance in meters between two WGS84 coordinates.
 * @param {{lat: number, lng: number}} a
 * @param {{lat: number, lng: number}} b
 */
function haversineMeters(a, b) {
  const R = 6371000;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lng - a.lng);
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const h =
    sinLat * sinLat +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * sinLon * sinLon;
  return 2 * R * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

test.describe('Production E2E Flight: Live PX4 SITL Point A -> Point B', () => {
  test('creates a swarm, dispatches a SMEAC flight order, and observes real PX4 drone movement on the map (zero mocks)', async ({
    page,
  }) => {
    test.setTimeout(180000);
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const snap = (name) =>
      page.screenshot({ path: path.join(SCREENSHOT_DIR, name), fullPage: true });

    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);
    const smeacPage = new SmeacPage(page);
    const mapComponent = new MapComponent(page);

    // 1. Authenticate as real Commander
    await loginPage.goto();
    await loginPage.expectModalVisible();
    await snap('01-login-modal.png');
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();

    await dashboardPage.expectLoaded();
    await dashboardPage.expectAuthenticated(VALID_COMMANDER.commanderId);
    await mapComponent.expectMapLoaded();

    // 2. Provision a new swarm via the UI (+ New Swarm modal)
    const swarmName = `prod-flight-${Date.now().toString().slice(-6)}`;
    await dashboardPage.provisionSwarm(swarmName, 1);
    await snap('02-swarm-provisioned.png');

    // 3. Wait for live PX4 telemetry (Point A) to appear on the Leaflet map
    await mapComponent.expectDroneMarkers(1);
    /** @type {{lat: number, lng: number} | null} */
    let pointA = null;
    await expect(async () => {
      const coords = await mapComponent.getDroneCoordinates();
      expect(coords).not.toBeNull();
      expect(Math.abs(coords.lat) + Math.abs(coords.lng)).toBeGreaterThan(0.1);
      pointA = coords;
    }).toPass({ timeout: 45000, intervals: [1000, 2000] });

    expect(pointA).not.toBeNull();
    const startPos = /** @type {{lat: number, lng: number}} */ (pointA);
    // Center map on the live drone at zoom 16 so Point A -> Point B movement is clearly visible
    await page.evaluate(({ lat, lng }) => {
      // @ts-ignore
      if (window.MapController && typeof window.MapController.getMap === 'function') {
        // @ts-ignore
        window.MapController.getMap().setView([lat, lng], 16);
      }
    }, startPos);
    await page.waitForTimeout(500);
    await snap('03-point-a-live-telemetry.png');

    // Target Point B ~550m northeast of Point A so movement is clearly visible on the map
    const pointB = {
      lat: Number((startPos.lat + 0.004).toFixed(6)),
      lng: Number((startPos.lng + 0.004).toFixed(6)),
    };

    // 4. Submit a real SMEAC patrol order flying to Point B
    await smeacPage.expectFormVisible();
    await smeacPage.fillOrder({
      situation: 'Drone is airborne and ready for patrol tasking. Airspace clear.',
      mission: `Conduct aerial patrol to destination waypoint lat=${pointB.lat}, lon=${pointB.lng} at 15m altitude.`,
      execution: `Fly directly to target waypoint lat=${pointB.lat}, lon=${pointB.lng} at altitude 15m and speed 10 m/s. Mission type: patrol.`,
      administration: 'Standard PX4 SITL battery reserve.',
      command: 'Report live telemetry over MQTT.',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();
    await snap('04-smeac-order-submitted.png');
    const orderId = await smeacPage.getSubmittedOrderId();
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(orderId).toBeTruthy();
    expect(swarmId).toBeTruthy();

    // 5. Verify Temporal worker dispatches mission and marks order executed
    await expect(async () => {
      const status = await page.evaluate(
        async ({ sId, oId }) => {
          const token = sessionStorage.getItem('auth_token') || '';
          const headers = token ? { Authorization: `Bearer ${token}` } : {};
          const res = await fetch(`http://localhost:8000/api/v1/swarms/${sId}/orders/${oId}`, {
            headers,
          });
          if (!res.ok) return `http_${res.status}`;
          const body = await res.json();
          return body.data ? body.data.status : body.status;
        },
        { sId: swarmId, oId: orderId },
      );
      expect(status).toBe('executed');
    }).toPass({ timeout: 45000, intervals: [1500, 2000] });
    await snap('05-order-executed.png');

    // 6. Verify real physical PX4 SITL drone displacement (> 200m from Point A toward Point B)
    let latestPos = startPos;
    let snappedInTransit = false;
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        latestPos = current;
        const movedMeters = haversineMeters(startPos, current);
        if (!snappedInTransit && movedMeters > 60) {
          snappedInTransit = true;
          await snap('05b-drone-in-transit.png');
        }
        expect(movedMeters).toBeGreaterThan(200);
      }
    }).toPass({ timeout: 90000, intervals: [2000, 3000] });

    await snap('06-drone-moved-toward-point-b.png');
    expect(haversineMeters(startPos, latestPos)).toBeGreaterThan(200);
  });
});
