// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8000/api/v1';
const VIRTUAL_CAM_BASE = process.env.VIRTUAL_CAM_BASE_URL || 'http://localhost:8091';

/**
 * Configure virtual_cam drone-1 feed into pose-aware corridor_scene mode.
 * @param {string} scenario
 * @param {boolean} [dynamicReturnBlock=false]
 */
async function setVirtualCamCorridorScenario(scenario, dynamicReturnBlock = false) {
  const res = await fetch(`${VIRTUAL_CAM_BASE}/feed/drone-1`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode: 'corridor_scene',
      scenario,
      dynamic_return_block: dynamicReturnBlock,
    }),
  });
  expect(res.ok).toBe(true);
}

/**
 * Poll C2 corridor survey list/report until predicate succeeds.
 * @param {import('@playwright/test').Page} page
 * @param {string} swarmId
 * @param {string} surveyId
 * @param {(report: any) => boolean} predicate
 */
async function waitForSurveyCondition(page, swarmId, surveyId, predicate, timeout = 120000) {
  let latest = null;
  await expect(async () => {
    latest = await page.evaluate(
      async ({ apiBase, sId, svId }) => {
        const token = sessionStorage.getItem('auth_token') || '';
        const res = await fetch(`${apiBase}/swarms/${sId}/corridor-surveys/${svId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) return null;
        const json = await res.json();
        return json.data || json;
      },
      { apiBase: API_BASE, sId: swarmId, svId: surveyId },
    );
    expect(latest).not.toBeNull();
    expect(predicate(latest)).toBe(true);
  }).toPass({ timeout, intervals: [1000, 1500] });
  return latest;
}

test.describe('Production Adaptive 3D Corridor Survey E2E (Zero Mocks)', () => {
  test.afterAll(async () => {
    await fetch(`${VIRTUAL_CAM_BASE}/feed/drone-1`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'clear' }),
    }).catch(() => {});
  });

  test('1. Coordinate-free 20m L-turn survey: 360 look-around hold, autonomous navigation, reverse return & full snapshot replay', async ({
    page,
  }) => {
    test.setTimeout(240000);
    await setVirtualCamCorridorScenario('l_turn_20m');

    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);
    const smeacPage = new SmeacPage(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectLoaded();

    const swarmName = `Corridor-LTurn-${Date.now()}`;
    await dashboardPage.provisionSwarm(swarmName, 3);
    const swarmId = await dashboardPage.swarmSelect.inputValue();
    expect(swarmId).toBeTruthy();

    await smeacPage.fillOrder({
      situation: 'Unknown industrial corridor ahead of lead drone.',
      mission: 'Go check the corridor next 20 meters and go back; report any vehicles or hazards.',
      execution: 'Assign single lead scout and hold remaining drones at staging.',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();

    const orderId = await smeacPage.getSubmittedOrderId();
    expect(orderId).toBeTruthy();

    // Wait for corridor survey record created & verify panel renders it
    let surveyId = null;
    await expect(async () => {
      surveyId = await page.evaluate(
        async ({ apiBase, sId }) => {
          const token = sessionStorage.getItem('auth_token') || '';
          const res = await fetch(`${apiBase}/swarms/${sId}/corridor-surveys`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          });
          if (!res.ok) return null;
          const body = await res.json();
          const list = body.data || [];
          return list.length > 0 ? list[0].survey_id : null;
        },
        { apiBase: API_BASE, sId: swarmId },
      );
      expect(surveyId).toBeTruthy();
    }).toPass({ timeout: 20000, intervals: [500, 1000] });

    const finalReport = await waitForSurveyCondition(
      page,
      swarmId,
      surveyId,
      (rep) => ['completed', 'completed_holding'].includes(rep.phase),
      150000,
    );

    expect(finalReport.lead_scout_drone_id).toBe('drone-1');
    expect(finalReport.staging_hold_drone_ids).toEqual(['drone-2', 'drone-3']);
    expect(finalReport.completion_reason).toBe('distance_reached');
    expect(finalReport.surveyed_distance_m).toBeGreaterThanOrEqual(17.5);
    expect(finalReport.snapshots.length).toBeGreaterThanOrEqual(8);
    expect(finalReport.decisions.length).toBeGreaterThanOrEqual(1);

    // Assert Corridor Survey & Intelligence panel renders SVG geometry & persisted snapshots without HITL modal interruption
    await expect(page.locator('#corridor-survey-panel')).toBeVisible();
    await expect(page.locator('#corridor-status-banner')).toContainText('drone-1');
    await expect(page.locator('#corridor-svg-plan polyline')).toBeVisible();
    await expect(page.locator('#corridor-svg-elevation')).toBeVisible();
    await expect(page.locator('#corridor-svg-elevation polyline')).toBeAttached();
    await expect(page.locator('#corridor-svg-elevation polyline')).toHaveAttribute('points', /\d+\.\d+,\d+\.\d+/);
    await expect(page.locator('#corridor-snapshot-filmstrip img').first()).toBeVisible();
    await expect(page.locator('#hitl-modal')).toBeHidden();
  });

  test('2. S-bend with low overhang, dead-end 12m early return, and two-tier Recall vs Emergency Abort overrides', async ({
    page,
  }) => {
    test.setTimeout(240000);
    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);
    const smeacPage = new SmeacPage(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.provisionSwarm(`Corridor-MultiShape-${Date.now()}`, 2);
    const swarmId = await dashboardPage.swarmSelect.inputValue();

    // 2A. Dead-end 12m early termination + reverse return
    await setVirtualCamCorridorScenario('dead_end_12m');
    await smeacPage.fillOrder({
      situation: 'Narrow utility tunnel ahead.',
      mission: 'Go check the corridor next 20 meters and go back.',
      execution: 'Reverse along verified path if passage terminates early.',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();

    let deadEndSurveyId = null;
    await expect(async () => {
      deadEndSurveyId = await page.evaluate(
        async ({ apiBase, sId }) => {
          const token = sessionStorage.getItem('auth_token') || '';
          const res = await fetch(`${apiBase}/swarms/${sId}/corridor-surveys`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          });
          if (!res.ok) return null;
          const body = await res.json();
          const list = body.data || [];
          return list.length > 0 ? list[0].survey_id : null;
        },
        { apiBase: API_BASE, sId: swarmId },
      );
      expect(deadEndSurveyId).toBeTruthy();
    }).toPass({ timeout: 20000 });

    const deadEndReport = await waitForSurveyCondition(
      page,
      swarmId,
      deadEndSurveyId,
      (rep) => rep.phase === 'completed',
      150000,
    );
    expect(deadEndReport.completion_reason).toBe('dead_end');
    expect(deadEndReport.surveyed_distance_m).toBeLessThan(18.0);

    // 2B. S-bend with low overhang + interactive Emergency Abort confirmation modal (zero native alert/confirm)
    await setVirtualCamCorridorScenario('s_bend_overhang_20m');
    await smeacPage.fillOrder({
      situation: 'Curved passage with low overhead pipes.',
      mission: 'Go check the corridor next 20 meters and go back.',
      execution: 'Adapt 3D altitude within [1.2m, 8.0m].',
    });
    await smeacPage.submit();
    await smeacPage.expectSuccess();

    await expect(page.locator('#btn-corridor-emergency-abort')).toBeEnabled({ timeout: 30000 });
    await page.locator('#btn-corridor-emergency-abort').click();
    await expect(page.locator('#corridor-abort-modal')).toBeVisible();
    await page.locator('#corridor-override-rationale').fill('E2E emergency hold verification');
    await page.locator('#corridor-modal-confirm').click();
    await expect(page.locator('#corridor-abort-modal')).toBeHidden();
    await expect(page.locator('#corridor-status-banner')).toContainText(/emergency_hold/i, { timeout: 20000 });
  });
});
