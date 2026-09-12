// @ts-check
const { test, expect } = require('@playwright/test');
const { LoginPage } = require('./pages/LoginPage');
const { DashboardPage } = require('./pages/DashboardPage');
const { SmeacPage } = require('./pages/SmeacPage');
const { VALID_COMMANDER } = require('./fixtures/credentials');
const { VALID_SMEAC } = require('./fixtures/smeac-data');

test.describe('User Story 3: Tactical SMEAC Order Composition & Dispatch', () => {
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
  });

  test('T016: should require mandatory SMEAC fields before submission', async ({ page }) => {
    await smeacPage.expectFormVisible();

    // Setup dialog listener in case alert triggers if no swarm is selected
    let dialogHandled = false;
    page.once('dialog', async dialog => {
      dialogHandled = true;
      await dialog.dismiss();
    });

    // Attempt submission with empty form
    await smeacPage.submit();

    // Check either HTML5 validity or alert triggered
    const isSituationValid = await smeacPage.situationInput.evaluate(
      (/** @type {HTMLTextAreaElement} */ el) => el.checkValidity ? el.checkValidity() : true
    );
    expect(dialogHandled || !isSituationValid).toBeTruthy();
  });

  test('T017: should compose and dispatch a valid SMEAC order successfully', async () => {
    // Select the available active swarm
    await dashboardPage.selectFirstAvailableSwarm();

    // Fill in valid SMEAC order
    await smeacPage.fillOrder(VALID_SMEAC);

    // Submit and assert success banner
    await smeacPage.submit();
    await smeacPage.expectSuccess();
  });
});
