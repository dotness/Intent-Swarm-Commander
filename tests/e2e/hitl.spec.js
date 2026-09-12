// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { HitlPage } = require('./pages/HitlPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');
const { HitlDbHelper } = require('./fixtures/hitl-helper');

test.describe('User Story 4 — Human-in-the-Loop (HITL) Safety Gate', () => {
  let loginPage;
  let dashboardPage;
  let hitlPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    hitlPage = new HitlPage(page);

    // Clean prior decisions before each test
    HitlDbHelper.clearAll();

    // Navigate and authenticate
    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated();

    // Ensure a swarm is selected
    await dashboardPage.selectFirstAvailableSwarm();
  });

  test.afterEach(() => {
    HitlDbHelper.clearAll();
  });

  test('T018: should detect pending HITL decision and display approval modal', async ({ page }) => {
    const decisionId = 'b0000000-0000-0000-0000-000000000018';
    const actionSummary = 'Deploy Autonomous Counter-Measure Drone Swarm';

    // Seed pending decision in PostgreSQL
    HitlDbHelper.seedPendingDecision({
      id: decisionId,
      actionSummary,
      timeoutSeconds: 180,
    });

    // Trigger HITL poll on the active swarm
    await page.evaluate(() => {
      // @ts-ignore
      if (typeof pollHitl === 'function') {
        // @ts-ignore
        pollHitl();
      }
    });

    // Modal should become visible with the action summary
    await hitlPage.expectModalOpen();
    await hitlPage.expectActionSummary(actionSummary);
  });

  test('T019: should approve pending decision, close modal, and update state', async ({ page }) => {
    const decisionId = 'b0000000-0000-0000-0000-000000000019';
    const actionSummary = 'Authorize Emergency Kinetic Intercept Operation';

    HitlDbHelper.seedPendingDecision({
      id: decisionId,
      actionSummary,
      timeoutSeconds: 120,
    });

    // Trigger HITL poll
    await page.evaluate(() => {
      // @ts-ignore
      if (typeof pollHitl === 'function') {
        // @ts-ignore
        pollHitl();
      }
    });

    await hitlPage.expectModalOpen();
    await hitlPage.expectActionSummary(actionSummary);

    // Click approve and wait for decision to process
    const decidePromise = page.waitForResponse(
      (res) => res.url().includes(`/hitl/${decisionId}/decide`) && res.status() === 200
    );
    await hitlPage.approve();
    await decidePromise;

    // Modal should close
    await hitlPage.expectModalClosed();

    // Verify DB state transitioned to approved and decided
    const record = HitlDbHelper.getDecision(decisionId);
    expect(record).not.toBeNull();
    expect(record?.decision).toBe('approved');
    expect(record?.status).toBe('decided');
  });

  test('T020: should reject pending decision, close modal, and update state', async ({ page }) => {
    const decisionId = 'b0000000-0000-0000-0000-000000000020';
    const actionSummary = 'Unauthorized Deep Penetration Reconnaissance';

    HitlDbHelper.seedPendingDecision({
      id: decisionId,
      actionSummary,
      timeoutSeconds: 90,
    });

    // Trigger HITL poll
    await page.evaluate(() => {
      // @ts-ignore
      if (typeof pollHitl === 'function') {
        // @ts-ignore
        pollHitl();
      }
    });

    await hitlPage.expectModalOpen();
    await hitlPage.expectActionSummary(actionSummary);

    // Click reject and wait for decision to process
    const decidePromise = page.waitForResponse(
      (res) => res.url().includes(`/hitl/${decisionId}/decide`) && res.status() === 200
    );
    await hitlPage.reject();
    await decidePromise;

    // Modal should close
    await hitlPage.expectModalClosed();

    // Verify DB state transitioned to rejected and decided
    const record = HitlDbHelper.getDecision(decisionId);
    expect(record).not.toBeNull();
    expect(record?.decision).toBe('rejected');
    expect(record?.status).toBe('decided');
  });
});
