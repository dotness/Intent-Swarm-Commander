// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { VALID_COMMANDER, INVALID_COMMANDER } = require('./fixtures/credentials');

test.describe('User Story 1: Commander Authentication & Session Lifecycle', () => {
  test.beforeEach(async ({ page }) => {
    // Clear storage before each test for a clean slate
    await page.goto('/');
    await page.evaluate(() => sessionStorage.clear());
    await page.reload();
  });

  test('T010: should display login modal and reject invalid passphrase', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.expectModalVisible();

    await loginPage.login(INVALID_COMMANDER.commanderId, INVALID_COMMANDER.passphrase);
    await loginPage.expectError(/Invalid credentials|Authentication failed|Login failed/);
    await loginPage.expectModalVisible();
  });

  test('T011: should authenticate successfully with valid credentials and dismiss modal', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);

    await loginPage.expectModalVisible();
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);

    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated('commander-alpha');
  });

  test('T012: should persist authenticated session across browser page reloads', async ({ page }) => {
    const loginPage = new LoginPage(page);
    const dashboardPage = new DashboardPage(page);

    // Initial login
    await loginPage.login(VALID_COMMANDER.commanderId, VALID_COMMANDER.passphrase);
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated('commander-alpha');

    // Reload the page
    await page.reload();

    // Verify session persists without modal re-prompting
    await loginPage.expectModalHidden();
    await dashboardPage.expectAuthenticated('commander-alpha');
  });
});
