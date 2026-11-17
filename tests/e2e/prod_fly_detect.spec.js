// @ts-check
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { HitlPage } = require('./pages/HitlPage');
const { MapComponent } = require('./pages/MapComponent');
const { VALID_COMMANDER } = require('./fixtures/credentials');

const SCREENSHOT_DIR =
  process.env.E2E_SCREENSHOT_DIR ||
  '/home/remi/.gemini/antigravity/brain/90c79937-29f7-4eda-8263-b3f41aab8025/screenshots';

const VIRTUAL_CAM_FEED_URL = process.env.VIRTUAL_CAM_FEED_URL || 'http://localhost:8091/feed';

/**
 * Great-circle distance in meters between two WGS84 coordinates.
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

/**
 * Perpendicular cross-track distance in meters from point P to segment line A -> B.
 * @param {{lat: number, lng: number}} a
 * @param {{lat: number, lng: number}} b
 * @param {{lat: number, lng: number}} p
 */
function crossTrackMeters(a, b, p) {
  const cosLat = Math.cos((a.lat * Math.PI) / 180);
  const ax = 0;
  const ay = 0;
  const bx = (b.lng - a.lng) * 111111 * cosLat;
  const by = (b.lat - a.lat) * 111111;
  const px = (p.lng - a.lng) * 111111 * cosLat;
  const py = (p.lat - a.lat) * 111111;
  const len = Math.hypot(bx - ax, by - ay);
  if (len < 1e-6) return 0;
  return Math.abs((by - ay) * px - (bx - ax) * py) / len;
}

/**
 * Switch the virtual camera server between 'clear' and 'target' video feeds.
 * @param {'clear' | 'target'} mode
 */
async function setVirtualCamMode(mode) {
  const res = await fetch(VIRTUAL_CAM_FEED_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  expect(res.ok).toBe(true);
}

/**
 * Center the Leaflet map on a coordinate so drone motion is clearly visible.
 * @param {import('@playwright/test').Page} page
 * @param {{lat: number, lng: number}} pos
 */
async function centerMapOn(page, pos) {
  await page.evaluate(({ lat, lng }) => {
    // @ts-ignore
    if (window.MapController && typeof window.MapController.getMap === 'function') {
      // @ts-ignore
      window.MapController.getMap().setView([lat, lng], 16);
    }
  }, pos);
  await page.waitForTimeout(300);
}

/**
 * Wait for a SMEAC order to reach 'executed' via the backend API.
 * @param {import('@playwright/test').Page} page
 * @param {string} swarmId
 * @param {string} orderId
 */
async function expectOrderExecuted(page, swarmId, orderId) {
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
}

/**
 * Verify a YOLO-E detection was correlated in Memgraph and has a valid MinIO JPEG snapshot.
 * @param {import('@playwright/test').Page} page
 * @param {string} targetClass
 */
async function expectCorrelatedDetectionWithSnapshot(page, targetClass) {
  await expect(async () => {
    const check = await page.evaluate(async (cls) => {
      const token = sessionStorage.getItem('auth_token') || '';
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const tRes = await fetch(
        `http://localhost:8000/api/v1/targets?project_id=default-theater&target_class=${encodeURIComponent(cls)}`,
        { headers },
      );
      if (!tRes.ok) return null;
      const tBody = await tRes.json();
      const targets = (tBody.data && (tBody.data.targets || tBody.data.items)) || [];
      if (!targets.length) return null;

      const target = targets[targets.length - 1];
      const targetId = target.target_id || target.id;
      if (!targetId) return null;

      const lRes = await fetch(
        `http://localhost:8000/api/v1/targets/${targetId}/lineage?project_id=default-theater`,
        { headers },
      );
      if (!lRes.ok) return null;
      const lBody = await lRes.json();
      const detections =
        (lBody.data && (lBody.data.observations || lBody.data.detections)) || [];
      if (!detections.length) return null;

      const det = detections[detections.length - 1];
      const snapPath =
        det.snapshot_url ||
        `/api/v1/analytics/detections/${det.event_id}/snapshot?project_id=default-theater`;
      const snapUrl = snapPath.startsWith('http')
        ? snapPath
        : `http://localhost:8000${snapPath}`;
      const sRes = await fetch(snapUrl, { headers });
      const buf = sRes.ok ? await sRes.arrayBuffer() : new ArrayBuffer(0);
      return {
        targetId,
        snapshotOk: sRes.ok,
        contentType: sRes.headers.get('content-type') || '',
        size: buf.byteLength,
      };
    }, targetClass);
    expect(check).not.toBeNull();
    expect(check?.snapshotOk).toBe(true);
    expect(check?.contentType).toContain('image/jpeg');
    expect(check?.size).toBeGreaterThan(500);
  }).toPass({ timeout: 45000, intervals: [1500, 2000] });
}

test.describe('Production Vision-Triggered E2E Flights (Zero Mocks)', () => {
  test.afterAll(async () => {
    await fetch('http://localhost:8090/target/stop', { method: 'POST' }).catch(() => {});
    await setVirtualCamMode('target').catch(() => {});
  });

  test('1. Report-Only: flies Point A -> Point B, receives video mid-flight, detects object, and continues to Point B', async ({
    page,
  }) => {
    test.setTimeout(180000);
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const snap = (name) =>
      page.screenshot({ path: path.join(SCREENSHOT_DIR, name), fullPage: true });

    await setVirtualCamMode('clear');

    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);
    const smeacPage = new SmeacPage(page);
    const mapComponent = new MapComponent(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectLoaded();
    await mapComponent.expectMapLoaded();

    await dashboardPage.provisionSwarm(`fd-report-${Date.now().toString().slice(-6)}`, 1);
    await mapComponent.expectDroneMarkers(1);

    /** @type {{lat: number, lng: number} | null} */
    let pointA = null;
    await expect(async () => {
      const coords = await mapComponent.getDroneCoordinates();
      expect(coords).not.toBeNull();
      expect(Math.abs(coords.lat) + Math.abs(coords.lng)).toBeGreaterThan(0.1);
      pointA = coords;
    }).toPass({ timeout: 45000, intervals: [1000, 2000] });

    const startPos = /** @type {{lat: number, lng: number}} */ (pointA);
    await centerMapOn(page, startPos);
    await snap('fd1-01-point-a.png');

    const pointB = {
      lat: Number((startPos.lat + 0.0035).toFixed(6)),
      lng: Number((startPos.lng + 0.0035).toFixed(6)),
    };

    await smeacPage.expectFormVisible();
    await smeacPage.fillOrder({
      situation: 'Drone is airborne and ready for recon patrol. Airspace clear.',
      mission: `Conduct aerial recon patrol to destination waypoint lat=${pointB.lat}, lon=${pointB.lng} at 15m altitude and identify any target object class 'person'.`,
      execution: `Fly directly to waypoint lat=${pointB.lat}, lon=${pointB.lng} at altitude 15m and speed 10 m/s. Mission type: recon. Target object class: person.`,
      administration: 'Standard PX4 SITL battery reserve.',
      command: 'Stream live telemetry and detection snapshots over MQTT.',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();
    const orderId = await smeacPage.getSubmittedOrderId();
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(orderId).toBeTruthy();
    await expectOrderExecuted(page, swarmId, /** @type {string} */ (orderId));

    // Wait until drone is airborne and flying toward Point B while video is still 'clear'
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        expect(haversineMeters(startPos, current)).toBeGreaterThan(25);
      }
    }).toPass({ timeout: 60000, intervals: [1500, 2000] });
    await snap('fd1-02-flying-clear-feed.png');

    // Feed target video mid-flight to trigger YOLO-E detection while continuing route
    await setVirtualCamMode('target');

    await expectCorrelatedDetectionWithSnapshot(page, 'person');

    // Verify the drone continues along A -> B past 150m despite detecting the object
    let finalPos = startPos;
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        finalPos = current;
        expect(haversineMeters(startPos, current)).toBeGreaterThan(150);
      }
    }).toPass({ timeout: 90000, intervals: [2000, 3000] });

    await snap('fd1-03-point-b-and-detected.png');
    expect(haversineMeters(startPos, finalPos)).toBeGreaterThan(150);
  });

  test('2. Intercept: flies Point A -> Point B, receives video mid-flight, detects object, and changes path toward it', async ({
    page,
  }) => {
    test.setTimeout(180000);
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const snap = (name) =>
      page.screenshot({ path: path.join(SCREENSHOT_DIR, name), fullPage: true });

    await setVirtualCamMode('clear');

    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);
    const smeacPage = new SmeacPage(page);
    const hitlPage = new HitlPage(page);
    const mapComponent = new MapComponent(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectLoaded();
    await mapComponent.expectMapLoaded();

    await dashboardPage.provisionSwarm(`fd-intercept-${Date.now().toString().slice(-6)}`, 1);
    await mapComponent.expectDroneMarkers(1);

    /** @type {{lat: number, lng: number} | null} */
    let pointA = null;
    await expect(async () => {
      const coords = await mapComponent.getDroneCoordinates();
      expect(coords).not.toBeNull();
      expect(Math.abs(coords.lat) + Math.abs(coords.lng)).toBeGreaterThan(0.1);
      pointA = coords;
    }).toPass({ timeout: 45000, intervals: [1000, 2000] });

    const startPos = /** @type {{lat: number, lng: number}} */ (pointA);
    await centerMapOn(page, startPos);
    await snap('fd2-01-point-a.png');

    const pointB = {
      lat: Number((startPos.lat + 0.004).toFixed(6)),
      lng: Number((startPos.lng + 0.004).toFixed(6)),
    };

    // Submit SMEAC STRIKE order (triggers HITL approval & detection_mode='intercept')
    await smeacPage.expectFormVisible();
    await smeacPage.fillOrder({
      situation: 'Hostile target reported along sector transit corridor.',
      mission: `Conduct strike intercept toward waypoint lat=${pointB.lat}, lon=${pointB.lng} at 15m altitude and engage detected 'person'.`,
      execution: `Fly toward waypoint lat=${pointB.lat}, lon=${pointB.lng} at altitude 15m and speed 10 m/s. Mission type: strike. Target object class: person.`,
      administration: 'Standard PX4 SITL battery reserve.',
      command: 'Require HITL approval before launch; stream detection crops over MQTT.',
    });
    await smeacPage.submit();
    await expect(smeacPage.resultDiv).toBeVisible();
    await expect(smeacPage.resultDiv).toContainText(/Status:\s*pending_hitl/i);
    const orderId = await smeacPage.getSubmittedOrderId();
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(orderId).toBeTruthy();

    // Approve the high-impact STRIKE mission in the HITL modal
    await hitlPage.expectModalOpen();
    await snap('fd2-02-hitl-modal.png');
    await hitlPage.approve();
    await hitlPage.expectModalClosed();

    await expectOrderExecuted(page, swarmId, /** @type {string} */ (orderId));

    // Wait until drone is airborne and flying toward Point B (> 30m from Point A)
    let midPos = startPos;
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        midPos = current;
        expect(haversineMeters(startPos, current)).toBeGreaterThan(30);
      }
    }).toPass({ timeout: 60000, intervals: [1500, 2000] });

    // Feed target video mid-flight to trigger intercept course change
    await setVirtualCamMode('target');

    await expectCorrelatedDetectionWithSnapshot(page, 'person');

    // Verify drone reacts by changing path off the A -> B line toward the object
    let divertedPos = midPos;
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        divertedPos = current;
        const movedAfterIntercept = haversineMeters(midPos, current);
        const crossTrack = crossTrackMeters(startPos, pointB, current);
        expect(movedAfterIntercept).toBeGreaterThan(30);
        expect(crossTrack).toBeGreaterThan(15);
      }
    }).toPass({ timeout: 90000, intervals: [2000, 3000] });

    await snap('fd2-03-intercept-diverted.png');
    await fetch('http://localhost:8090/target/stop', { method: 'POST' }).catch(() => {});
    await setVirtualCamMode('clear').catch(() => {});
    if (await hitlPage.modal.isVisible().catch(() => false)) {
      await hitlPage.approve();
      await hitlPage.expectModalClosed();
    }
    expect(crossTrackMeters(startPos, pointB, divertedPos)).toBeGreaterThan(15);
  });
});
