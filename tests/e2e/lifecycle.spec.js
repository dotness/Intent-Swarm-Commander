// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');

test.describe('End-to-End Operational Lifecycle: Swarm Creation, Multi-Order Execution, and History Persistence', () => {
  /** @type {LoginPage} */
  let loginPage;
  /** @type {DashboardPage} */
  let dashboardPage;
  /** @type {SmeacPage} */
  let smeacPage;

  test('should execute full 9-step operational scenario with order execution and history persistence across reloads', async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    smeacPage = new SmeacPage(page);

    // ── Step 1: Login ──────────────────────────────────────────────────────────
    await loginPage.goto();
    await loginPage.expectModalVisible();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated();

    // ── Step 2: Create a Swarm ─────────────────────────────────────────────────
    const swarmName = `Delta Recon Swarm ${Date.now()}`;
    await dashboardPage.provisionSwarm(swarmName, 4);

    // Retrieve active swarm ID from selector
    const activeSwarmId = await page.$eval('#swarm-select', (el) => /** @type {HTMLSelectElement} */ (el).value);
    expect(activeSwarmId).toBeTruthy();

    // ── Step 3: Issue Order to Swarm ───────────────────────────────────────────
    const order1Data = {
      situation: 'Hostile radar active in quadrant 7. Radar emission detected.',
      mission: 'Conduct aerial reconnaissance along flight corridor Delta-1.',
      execution: 'Advance in wedge formation at 120m AGL, maintaining RF discipline.',
      administration: 'Reserve battery swaps available at FOB Echo.',
      command: 'Commander Alpha leading; fallback channel Delta-9.'
    };
    await smeacPage.fillOrder(order1Data);
    await smeacPage.submit();

    // ── Step 4: Check that Order is Executed ────────────────────────────────────
    await smeacPage.expectSuccess();
    await smeacPage.expectExecuted();
    const orderId1 = await smeacPage.getSubmittedOrderId();
    expect(orderId1).toBeTruthy();

    // Verify order execution record via API
    const order1Status = await page.evaluate(async ({ swarmId, orderId }) => {
      // @ts-ignore
      return await window.ApiClient.getOrderStatus(swarmId, orderId);
    }, { swarmId: activeSwarmId, orderId: orderId1 });
    expect(order1Status).not.toBeNull();
    expect(order1Status.order_id).toBe(orderId1);

    // ── Step 5: Add Another Order ──────────────────────────────────────────────
    const order2Data = {
      situation: 'Forward outpost reporting perimeter movement at grid Bravo-4.',
      mission: 'Establish 360-degree security overwatch perimeter.',
      execution: 'Deploy circular surveillance orbit at 150m AGL.',
      administration: 'Automated return-to-base on 20% battery threshold.',
      command: 'Tactical link on channel Zulu-3.'
    };
    await smeacPage.fillOrder(order2Data);
    await smeacPage.submit();

    // ── Step 6: Check that Order Was Executed ───────────────────────────────────
    await smeacPage.expectSuccess();
    await smeacPage.expectExecuted();
    const orderId2 = await smeacPage.getSubmittedOrderId();
    expect(orderId2).toBeTruthy();
    expect(orderId2).not.toBe(orderId1);

    // Verify second order execution record via API
    const order2Status = await page.evaluate(async ({ swarmId, orderId }) => {
      // @ts-ignore
      return await window.ApiClient.getOrderStatus(swarmId, orderId);
    }, { swarmId: activeSwarmId, orderId: orderId2 });
    expect(order2Status).not.toBeNull();
    expect(order2Status.order_id).toBe(orderId2);

    // ── Step 7: History is Visible ─────────────────────────────────────────────
    await dashboardPage.expectHistoryContains(orderId1);
    await dashboardPage.expectHistoryContains(orderId2);
    await dashboardPage.expectHistoryContains(swarmName);

    // ── Step 8: Refresh / Login Again ──────────────────────────────────────────
    await page.reload();

    // If modal appears due to fresh session, log in again; otherwise verify persistence
    const isLoginVisible = await loginPage.modal.isVisible();
    if (isLoginVisible) {
      await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
      await loginPage.expectModalHidden();
    }
    await dashboardPage.expectAuthenticated();

    // ── Step 9: History is Still Visible ───────────────────────────────────────
    await dashboardPage.expectHistoryContains(orderId1);
    await dashboardPage.expectHistoryContains(orderId2);
    await dashboardPage.expectHistoryContains(swarmName);
  });
});
