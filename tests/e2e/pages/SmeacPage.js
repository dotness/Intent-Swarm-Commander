// @ts-check
const { expect } = require('@playwright/test');

/**
 * Page Object representing the SMEAC Order Form panel
 */
class SmeacPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
    this.form = page.locator('#smeac-form');
    this.situationInput = page.locator('#smeac-situation');
    this.missionInput = page.locator('#smeac-mission');
    this.executionInput = page.locator('#smeac-execution');
    this.adminInput = page.locator('#smeac-admin');
    this.commandInput = page.locator('#smeac-signal');
    this.submitBtn = page.locator('#smeac-submit');
    this.resultDiv = page.locator('#smeac-result');
  }

  async expectFormVisible() {
    await expect(this.form).toBeVisible();
    await expect(this.submitBtn).toBeVisible();
  }

  /**
   * @param {{ situation?: string, mission?: string, execution?: string, administration?: string, command?: string }} order
   */
  async fillOrder(order) {
    if (order.situation !== undefined) await this.situationInput.fill(order.situation);
    if (order.mission !== undefined) await this.missionInput.fill(order.mission);
    if (order.execution !== undefined) await this.executionInput.fill(order.execution);
    if (order.administration !== undefined) await this.adminInput.fill(order.administration);
    if (order.command !== undefined) await this.commandInput.fill(order.command);
  }

  async submit() {
    await this.submitBtn.click();
  }

  async expectSuccess() {
    await expect(this.resultDiv).toBeVisible();
    await expect(this.resultDiv).toContainText('Order Submitted Successfully');
  }

  async expectExecuted() {
    await expect(this.resultDiv).toBeVisible();
    await expect(this.resultDiv).toContainText('Status: Executed');
  }

  /**
   * Retrieve the submitted order ID from result banner
   */
  async getSubmittedOrderId() {
    await expect(this.resultDiv).toBeVisible();
    const idSpan = this.resultDiv.locator('#smeac-submitted-id');
    if (await idSpan.count() > 0) {
      return (await idSpan.textContent())?.trim();
    }
    const text = await this.resultDiv.textContent();
    const match = text?.match(/Order ID:\s*([a-f0-9-]+)/i);
    return match ? match[1] : null;
  }

  /**
   * @param {string | RegExp} [expectedError]
   */
  async expectError(expectedError) {
    await expect(this.resultDiv).toBeVisible();
    await expect(this.resultDiv).toContainText('Submission Failed');
    if (expectedError) {
      await expect(this.resultDiv).toContainText(expectedError);
    }
  }
}

module.exports = { SmeacPage };
