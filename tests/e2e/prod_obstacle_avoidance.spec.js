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
  '/home/remi/.gemini/antigravity/brain/84a88afb-dd60-4675-a0c1-af8057e9022d/screenshots';

const VIRTUAL_CAM_FEED_URL = process.env.VIRTUAL_CAM_FEED_URL || 'http://localhost:8091/feed';
const OBSTACLE_VIDEO_PATH =
  process.env.OBSTACLE_VIDEO_PATH || 'tests/videos/drone_fpv_fly_straight_meet_lamp_obstacle.mp4';
const TARGET_IMAGE_PATH =
  process.env.TARGET_IMAGE_PATH || '/usr/local/lib/python3.10/dist-packages/ultralytics/assets/bus.jpg';

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
  const bx = (b.lng - a.lng) * 111111 * cosLat;
  const by = (b.lat - a.lat) * 111111;
  const px = (p.lng - a.lng) * 111111 * cosLat;
  const py = (p.lat - a.lat) * 111111;
  const len = Math.hypot(bx, by);
  if (len < 1e-6) return 0;
  return Math.abs(by * px - bx * py) / len;
}

/**
 * Switch the virtual camera server feed mode and optional video asset path.
 * @param {'clear' | 'target'} mode
 * @param {string} [videoPath]
 */
async function setVirtualCamFeed(mode, videoPath) {
  const payload = videoPath ? { mode, path: videoPath } : { mode };
  const res = await fetch(VIRTUAL_CAM_FEED_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  expect(res.ok).toBe(true);
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

test.describe('Production Edge-Autonomous Obstacle Avoidance E2E (Zero Mocks)', () => {
  test.afterAll(async () => {
    await fetch('http://localhost:8090/target/stop', { method: 'POST' }).catch(() => {});
    await setVirtualCamFeed('clear').catch(() => {});
  });

  test('1. Lamp post obstacle bypass: edge autonomously orders lateral bypass and proves provenance in telemetry and C2 audit', async ({
    page,
  }) => {
    test.setTimeout(180000);
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const snap = (name) =>
      page.screenshot({ path: path.join(SCREENSHOT_DIR, name), fullPage: true });
    await setVirtualCamFeed('clear');

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

    await dashboardPage.provisionSwarm(`obs-bypass-${Date.now().toString().slice(-6)}`, 1);
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
    const pointB = {
      lat: Number((startPos.lat + 0.0035).toFixed(6)),
      lng: Number(startPos.lng.toFixed(6)),
    };

    await smeacPage.expectFormVisible();
    await smeacPage.fillOrder({
      situation: 'Drone is flying straight along urban corridor.',
      mission: `Fly straight to waypoint lat=${pointB.lat}, lon=${pointB.lng} at 15m altitude and search for target class 'truck'.`,
      execution: `Navigate directly to waypoint lat=${pointB.lat}, lon=${pointB.lng} at 15m altitude. Mission type: recon. Target object class: truck.`,
      administration: 'Standard PX4 SITL battery reserve.',
      command: 'Autonomous edge obstacle avoidance enabled with MQTT telemetry provenance.',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();
    const orderId = await smeacPage.getSubmittedOrderId();
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(orderId).toBeTruthy();
    await expectOrderExecuted(page, swarmId, /** @type {string} */ (orderId));

    // Confirm drone is airborne and flying straight before feeding the lamp-post FPV video
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        expect(haversineMeters(startPos, current)).toBeGreaterThan(25);
      }
    }).toPass({ timeout: 60000, intervals: [1500, 2000] });
    await snap('01-straight-flight.png');

    // Stream real FPV video containing lamp post obstacle directly ahead
    await setVirtualCamFeed('target', OBSTACLE_VIDEO_PATH);

    // 1. Verify telemetry stream projection proves edge_autonomous obstacle_bypass
    /** @type {any} */
    let capturedTelemetry = null;
    await expect(async () => {
      const telemetry = await page.evaluate(async (sId) => {
        const token = sessionStorage.getItem('auth_token') || '';
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(`http://localhost:8000/api/v1/swarms/${sId}/telemetry`, {
          headers,
        });
        if (!res.ok) return null;
        return res.json();
      }, swarmId);
      expect(telemetry).not.toBeNull();
      const drones = telemetry.drones || [];
      expect(drones.length).toBeGreaterThan(0);
      const avoidance = drones[0].last_avoidance_event;
      expect(avoidance).toBeTruthy();
      expect(avoidance.command_source).toBe('edge_autonomous');
      expect(avoidance.decision_authority).toBe('edge');
      expect(['obstacle_bypass', 'resume_route']).toContain(avoidance.action);
      if (avoidance.action === 'obstacle_bypass') {
        expect(['left', 'right']).toContain(avoidance.bypass_direction);
      }
      capturedTelemetry = telemetry;
    }).toPass({ timeout: 75000, intervals: [1500, 2000] });
    console.log('E2E_TEST1_TELEMETRY:', JSON.stringify(capturedTelemetry));

    // 2. Verify C2 audit view records the edge-autonomous bypass event
    /** @type {any} */
    let capturedAuditEvent = null;
    await expect(async () => {
      const audit = await page.evaluate(async (sId) => {
        const token = sessionStorage.getItem('auth_token') || '';
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(`http://localhost:8000/api/v1/swarms/${sId}/audit`, {
          headers,
        });
        if (!res.ok) return null;
        return res.json();
      }, swarmId);
      expect(audit).not.toBeNull();
      const events = (audit.data && audit.data.events) || audit.events || [];
      const edgeEvent = events.find(
        (e) =>
          e.actor_type === 'agent' &&
          String(e.actor_id || '').startsWith('edge:') &&
          e.details &&
          e.details.command_source === 'edge_autonomous' &&
          e.details.action === 'obstacle_bypass',
      );
      expect(edgeEvent).toBeTruthy();
      capturedAuditEvent = edgeEvent;
    }).toPass({ timeout: 30000, intervals: [1500, 2000] });
    console.log('E2E_TEST1_AUDIT_EVENT:', JSON.stringify(capturedAuditEvent));

    // 3. Verify physical lateral course deviation away from the straight A -> B line
    let finalCrossTrack = 0;
    await expect(async () => {
      const current = await mapComponent.getDroneCoordinates();
      expect(current).not.toBeNull();
      if (current) {
        finalCrossTrack = crossTrackMeters(startPos, pointB, current);
        expect(finalCrossTrack).toBeGreaterThan(10);
      }
    }).toPass({ timeout: 45000, intervals: [1500, 2000] });
    console.log('E2E_TEST1_CROSS_TRACK_M:', finalCrossTrack.toFixed(2));
    await snap('02-obstacle-bypass-telemetry.png');
  });

  test('2. Target mismatch (not success story): ordered target "person" on lamp-post video MUST bypass the lamp post instead of approaching', async ({
    page,
  }) => {
    test.setTimeout(150000);
    await setVirtualCamFeed('clear');

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

    await dashboardPage.provisionSwarm(`obs-mismatch-${Date.now().toString().slice(-6)}`, 1);
    await mapComponent.expectDroneMarkers(1);

    let startPos = null;
    await expect(async () => {
      const coords = await mapComponent.getDroneCoordinates();
      expect(coords).not.toBeNull();
      expect(Math.abs(coords.lat) + Math.abs(coords.lng)).toBeGreaterThan(0.1);
      startPos = coords;
    }).toPass({ timeout: 45000, intervals: [1000, 2000] });

    const pointB = {
      lat: Number((startPos.lat + 0.003).toFixed(6)),
      lng: Number(startPos.lng.toFixed(6)),
    };

    await smeacPage.expectFormVisible();
    await smeacPage.fillOrder({
      situation: 'Drone is airborne seeking ordered target.',
      mission: `Fly to lat=${pointB.lat}, lon=${pointB.lng} at 15m and intercept target class 'person'.`,
      execution: `Fly to lat=${pointB.lat}, lon=${pointB.lng} at 15m. Mission type: intercept. Target object class: person.`,
      administration: 'Standard PX4 SITL battery reserve.',
      command: 'Intercept ordered target only; bypass non-target obstacles.',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();
    const orderId = await smeacPage.getSubmittedOrderId();
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(orderId).toBeTruthy();
    await expectOrderExecuted(page, swarmId, /** @type {string} */ (orderId));

    await setVirtualCamFeed('target', OBSTACLE_VIDEO_PATH);

    // Since there is no 'person' in the corridor, edge MUST bypass the lamp/bench obstacle
    /** @type {any} */
    let capturedMismatchTel = null;
    await expect(async () => {
      const telemetry = await page.evaluate(async (sId) => {
        const token = sessionStorage.getItem('auth_token') || '';
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(`http://localhost:8000/api/v1/swarms/${sId}/telemetry`, {
          headers,
        });
        if (!res.ok) return null;
        return res.json();
      }, swarmId);
      expect(telemetry).not.toBeNull();
      const drones = telemetry.drones || [];
      expect(drones.length).toBeGreaterThan(0);
      const avoidance = drones[0].last_avoidance_event;
      expect(avoidance).toBeTruthy();
      expect(avoidance.command_source).toBe('edge_autonomous');
      expect(['obstacle_bypass', 'resume_route']).toContain(avoidance.action);
      expect(avoidance.llm_matched_target).toBe(false);
      capturedMismatchTel = telemetry;
    }).toPass({ timeout: 75000, intervals: [1500, 2000] });
    console.log('E2E_TEST2_MISMATCH_BYPASS_TELEMETRY:', JSON.stringify(capturedMismatchTel));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-mismatch-person-bypasses-lamp.png'), fullPage: true });
  });

  test('3. Ordered target discrimination (success story): ordered target "lamp" on lamp-post video approaches without bypassing', async ({
    page,
  }) => {
    test.setTimeout(150000);
    await setVirtualCamFeed('clear');

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

    await dashboardPage.provisionSwarm(`obs-target-lamp-${Date.now().toString().slice(-6)}`, 1);
    await mapComponent.expectDroneMarkers(1);

    let startPos = null;
    await expect(async () => {
      const coords = await mapComponent.getDroneCoordinates();
      expect(coords).not.toBeNull();
      expect(Math.abs(coords.lat) + Math.abs(coords.lng)).toBeGreaterThan(0.1);
      startPos = coords;
    }).toPass({ timeout: 45000, intervals: [1000, 2000] });

    const pointB = {
      lat: Number((startPos.lat + 0.003).toFixed(6)),
      lng: Number(startPos.lng.toFixed(6)),
    };

    await smeacPage.expectFormVisible();
    await smeacPage.fillOrder({
      situation: 'Drone is airborne seeking ordered lamp post target.',
      mission: `Conduct strike intercept toward waypoint lat=${pointB.lat}, lon=${pointB.lng} at 15m and engage target class 'lamp'.`,
      execution: `Fly to lat=${pointB.lat}, lon=${pointB.lng} at 15m. Mission type: strike. Target object class: lamp.`,
      administration: 'Standard PX4 SITL battery reserve.',
      command: 'Require HITL approval; fly to ordered lamp target without bypassing it.',
    });
    await smeacPage.submit();
    await expect(smeacPage.resultDiv).toBeVisible();
    await expect(smeacPage.resultDiv).toContainText(/Status:\s*pending_hitl/i);
    const orderId = await smeacPage.getSubmittedOrderId();
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(orderId).toBeTruthy();

    await hitlPage.expectModalOpen();
    await hitlPage.approve();
    await hitlPage.expectModalClosed();

    await expectOrderExecuted(page, swarmId, /** @type {string} */ (orderId));

    await setVirtualCamFeed('target', OBSTACLE_VIDEO_PATH);

    // Verify edge strictly enters approaching/arrived for the matched lamp target (not 'active' or 'bypassing')
    /** @type {any} */
    let capturedEdgeTel = null;
    await expect(async () => {
      const res = await fetch('http://localhost:8090/telemetry');
      expect(res.ok).toBe(true);
      const edgeTel = await res.json();
      expect(
        edgeTel.target_intercepted === true || ['approaching', 'arrived'].includes(edgeTel.status),
      ).toBe(true);
      if (edgeTel.last_avoidance_command) {
        expect(edgeTel.last_avoidance_command.obstacle_class).not.toBe('street lamp');
        expect(edgeTel.last_avoidance_command.obstacle_class).not.toBe('lamp post');
      }
      capturedEdgeTel = edgeTel;
    }).toPass({ timeout: 90000, intervals: [1500, 2000] });
    console.log('E2E_TEST3_LAMP_TARGET_TELEMETRY:', JSON.stringify(capturedEdgeTel));
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-ordered-lamp-target-approach.png'), fullPage: true });
  });
});
