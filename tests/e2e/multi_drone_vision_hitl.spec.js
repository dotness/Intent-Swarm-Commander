// @ts-check
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { HitlPage } = require('./pages/HitlPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');

const VIRTUAL_CAM_BASE = process.env.VIRTUAL_CAM_URL || 'http://localhost:8091';
const EDGE_BASE = process.env.EDGE_URL || 'http://localhost:8090';
const SCREENSHOT_DIR =
  process.env.E2E_SCREENSHOT_DIR ||
  '/home/remi/.gemini/antigravity/brain/90c79937-29f7-4eda-8263-b3f41aab8025/screenshots';

/**
 * @param {string} droneId
 * @param {'clear' | 'target'} mode
 */
async function setDroneFeed(droneId, mode) {
  const res = await fetch(`${VIRTUAL_CAM_BASE}/feed/${encodeURIComponent(droneId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  expect(res.ok).toBe(true);
  return await res.json();
}

test.describe('Multi-Drone Vision Streams, Web GUI Snapshots & HITL Snapshot Modal (Zero Mocks)', () => {
  test.afterAll(async () => {
    await fetch(`${EDGE_BASE}/target/stop`, { method: 'POST' }).catch(() => {});
    await setDroneFeed('drone-1', 'target').catch(() => {});
    for (const d of ['drone-2', 'drone-3', 'drone-4', 'drone-5']) {
      await setDroneFeed(d, 'clear').catch(() => {});
    }
  });

  test('supports independent 5-drone /feed and /stream, Web GUI per-drone snapshot gallery, and HITL detection snapshot modal', async ({
    page,
  }) => {
    test.setTimeout(120000);
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    const snap = (name) =>
      page.screenshot({ path: path.join(SCREENSHOT_DIR, name), fullPage: true });

    // 1. Configure 5 independent drone video feeds: only drone-3 sees a target
    await setDroneFeed('drone-1', 'clear');
    await setDroneFeed('drone-2', 'clear');
    await setDroneFeed('drone-3', 'target');
    await setDroneFeed('drone-4', 'clear');
    await setDroneFeed('drone-5', 'clear');

    const statusRes = await fetch(`${VIRTUAL_CAM_BASE}/feed`);
    expect(statusRes.ok).toBe(true);
    const feedStatus = await statusRes.json();
    expect(feedStatus.channels['drone-3'].mode).toBe('target');
    expect(feedStatus.channels['drone-1'].mode).toBe('clear');
    expect(feedStatus.channels['drone-2'].mode).toBe('clear');
    expect(feedStatus.channels['drone-4'].mode).toBe('clear');
    expect(feedStatus.channels['drone-5'].mode).toBe('clear');

    // 2. Authenticate and provision swarm
    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);
    const hitlPage = new HitlPage(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectLoaded();

    await dashboardPage.provisionSwarm(`multi-vis-${Date.now().toString().slice(-6)}`, 5);

    // 3. Activate vision detection specifically on drone-3 (intercept mode triggers detection HITL)
    const targetRes = await fetch(`${EDGE_BASE}/target`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_object_class: 'person',
        command_id: '00000000-0000-0000-0000-000000000033',
        confidence_threshold: 0.5,
        detection_mode: 'intercept',
        drone_id: 'drone-3',
      }),
    });
    expect(targetRes.ok).toBe(true);
    const targetJson = await targetRes.json();
    expect(targetJson.drone_id).toBe('drone-3');

    // 4. Wait for detection HITL modal with drone-3's cropped JPEG snapshot
    await expect(hitlPage.modal).toBeVisible({ timeout: 20000 });
    await hitlPage.expectModalOpen();
    await expect(hitlPage.body).toContainText('drone-3');
    await expect(hitlPage.body).toContainText('person');
    const hitlSnapImg = page.locator('#hitl-detection-snapshot');
    await expect(hitlSnapImg).toBeVisible();
    await expect(async () => {
      const loaded = await hitlSnapImg.evaluate((el) => el.complete && el.naturalWidth > 0);
      expect(loaded).toBe(true);
    }).toPass({ timeout: 20000, intervals: [500, 1000] });
    await snap('md-01-hitl-detection-snapshot.png');

    // Stop drone-3's vision loop and switch feed back to clear before approving so no extra detection HITL fires
    await fetch(`${EDGE_BASE}/target/stop?drone_id=drone-3`, { method: 'POST' }).catch(() => {});
    await setDroneFeed('drone-3', 'clear');
    await page.waitForTimeout(1000);

    // Approve drone-3's HITL decision (and any in-flight duplicate that arrived before stop)
    for (let i = 0; i < 3; i++) {
      if (!(await hitlPage.modal.isVisible())) break;
      await hitlPage.approve();
      await hitlPage.expectModalClosed();
      await page.waitForTimeout(1200);
    }

    // 5. Verify Web GUI Drone Vision & Snapshots panel per drone_id
    const visionSelect = page.locator('#vision-drone-select');
    const visionImg = page.locator('#vision-stream-img');
    const gallery = page.locator('#vision-snapshot-gallery');

    await visionSelect.selectOption('drone-3');
    await expect(visionImg).toHaveAttribute('src', `${VIRTUAL_CAM_BASE}/stream/drone-3`);
    await expect(async () => {
      await page.click('#btn-refresh-vision-snapshots');
      const count = await gallery.locator('img').count();
      expect(count).toBeGreaterThan(0);
      const ok = await gallery.locator('img').first().evaluate((el) => el.complete && el.naturalWidth > 0);
      expect(ok).toBe(true);
    }).toPass({ timeout: 20000, intervals: [1000, 1500] });
    await expect(gallery).toContainText('drone-3');
    await snap('md-02-vision-panel-drone3.png');

    // Switching to drone-2 shows drone-2's separate stream and empty snapshot state
    await visionSelect.selectOption('drone-2');
    await expect(visionImg).toHaveAttribute('src', `${VIRTUAL_CAM_BASE}/stream/drone-2`);
    await expect(gallery).toContainText('No detection snapshots for drone-2 yet');
  });
});
