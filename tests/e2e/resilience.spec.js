// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');
const { VALID_SMEAC } = require('./fixtures/smeac-data');

test.describe('User Story 5 — Resiliency, Error Handling, and Security Boundaries', () => {
  /** @type {LoginPage} */
  let loginPage;
  /** @type {DashboardPage} */
  let dashboardPage;
  /** @type {SmeacPage} */
  let smeacPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    smeacPage = new SmeacPage(page);

    await loginPage.goto();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated();
    await dashboardPage.selectFirstAvailableSwarm();
  });

  test('T021: should handle 401 Unauthorized by clearing session and prompting login modal', async ({ page }) => {
    // Tamper the active session token to simulate expiration or invalid credentials
    await page.evaluate(() => {
      // @ts-ignore
      window.authManager.token = 'tampered.invalid.token';
      sessionStorage.setItem('auth_token', 'tampered.invalid.token');
    });

    // Trigger an API call that requires authentication
    await page.evaluate(async () => {
      try {
        // @ts-ignore
        await window.ApiClient.fetchSwarms();
      } catch (e) {
        // Expected unauthorized rejection
      }
    });

    // Verify session was cleared and login prompt is shown
    await loginPage.expectModalVisible();
    await dashboardPage.expectUnauthenticated();

    // Verify token was purged from sessionStorage
    const storedToken = await page.evaluate(() => sessionStorage.getItem('auth_token'));
    expect(storedToken).toBeNull();
  });

  test('T022: should handle network failure gracefully without crashing the UI', async ({ page }) => {
    // Intercept and abort orders submission API to simulate network disconnect
    await page.route('**/orders', (route) => route.abort('failed'));

    // Fill valid SMEAC order and submit
    await smeacPage.fillOrder(VALID_SMEAC);
    await smeacPage.submit();

    // Verify graceful error banner is presented
    await smeacPage.expectError('Submission Failed');

    // Verify submit button is recovered and interactive
    await expect(smeacPage.submitBtn).toBeEnabled();
    await expect(smeacPage.submitBtn).toContainText('Submit Order');

    // Verify core UI components remain intact and active
    await expect(dashboardPage.swarmSelect).toBeVisible();
    await expect(dashboardPage.authBadge).toBeVisible();
  });
});
