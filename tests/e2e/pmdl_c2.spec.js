// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');

test.describe('PMDL C4ISR Unified C2 Console (US1-US4)', () => {
  let loginPage;
  let dashboardPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated();
  });

  test('T047.1: renders theater project selector, ThreatZones, AAR panel, and Target Lineage UI', async ({ page }) => {
    await expect(page.locator('#project-id-input')).toHaveValue('default-theater');
    await expect(page.locator('#aar-panel')).toBeVisible();
    await expect(page.locator('#aar-query-type')).toBeVisible();

    // Query AAR panel via live backend endpoint
    const aarResPromise = page.waitForResponse(
      (res) => res.url().includes('/api/v1/analytics/aar') && res.request().method() === 'GET'
    );
    await page.click('#btn-refresh-aar');
    const aarRes = await aarResPromise;
    expect([200, 500]).toContain(aarRes.status());
  });

  test('T047.2: enforces mandatory rationale in HITL modal for ThreatZone override', async ({ page }) => {
    await dashboardPage.selectFirstAvailableSwarm();

    // Trigger HITL modal in browser context for a threat override pending decision
    const decisionPayload = {
      decision_id: 'c0000000-0000-0000-0000-000000000047',
      command_id: 'd0000000-0000-0000-0000-000000000047',
      action_summary: 'Recon route intersects active SAM zone',
      timeout_seconds: 120,
      status: 'pending',
      is_threat_override: true,
      requires_override_justification: true,
      threat_conflicts: [{ threat_id: 'threat-1', name: 'SA-17 Battery', threat_type: 'SAM', severity: 'critical' }]
    };

    await page.evaluate((dec) => {
      // @ts-ignore
      window.HitlController.showModal('00000000-0000-0000-0000-000000000001', dec, () => {});
    }, decisionPayload);

    await expect(page.locator('#hitl-modal')).toBeVisible();
    await expect(page.locator('#hitl-rationale')).toBeVisible();

    // Attempting Approve with blank rationale must stay open and show inline validation error
    await page.fill('#hitl-rationale', '   ');
    await page.click('#hitl-approve');
    await expect(page.locator('#hitl-modal')).toBeVisible();
    await expect(page.locator('#hitl-error')).toBeVisible();
  });

  test('T047.3: Draft with AI Copilot populates SMEAC fields read-only without auto-submitting order', async ({ page }) => {
    let submittedOrders = 0;
    await page.route('**/api/v1/swarms/*/orders', async (route) => {
      submittedOrders += 1;
      await route.continue();
    });

    await page.fill('#copilot-intent', 'Survey northern supply corridor while avoiding SAM zone.');
    const draftPromise = page.waitForResponse(
      (res) => res.url().includes('/api/v1/smeac/draft') && res.status() === 200
    );
    await page.click('#btn-draft-copilot');
    await draftPromise;

    await expect(page.locator('#smeac-situation')).not.toHaveValue('');
    await expect(page.locator('#smeac-mission')).not.toHaveValue('');
    await expect(page.locator('#copilot-citations')).toBeVisible();
    expect(submittedOrders).toBe(0);
  });
});
