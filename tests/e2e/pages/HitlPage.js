// @ts-check
const { expect } = require('@playwright/test');

/**
 * Page Object representing the Human-in-the-Loop (HITL) approval dialog
 */
class HitlPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
    this.modal = page.locator('#hitl-modal');
    this.body = page.locator('#hitl-modal-body');
    this.approveBtn = page.locator('#hitl-approve');
    this.rejectBtn = page.locator('#hitl-reject');
  }

  /**
   * Waits for the HITL approval dialog to open
   */
  async expectModalOpen() {
    await expect(this.modal).toBeVisible();
    await expect(this.approveBtn).toBeVisible();
    await expect(this.rejectBtn).toBeVisible();
  }

  async expectModalClosed() {
    await expect(this.modal).toBeHidden();
  }

  /**
   * @param {string} textSnippet
   */
  async expectActionSummary(textSnippet) {
    await expect(this.body).toContainText(textSnippet);
  }

  async approve() {
    await this.approveBtn.click();
  }

  async reject() {
    await this.rejectBtn.click();
  }

  /**
   * Helper to trigger a synthetic or polled HITL modal for testing
   * @param {string} swarmId
   * @param {object} decision
   */
  async triggerModalInBrowser(swarmId, decision) {
    await this.page.evaluate(({ swarmId, decision }) => {
      window.HitlController.showModal(swarmId, decision, () => {});
    }, { swarmId, decision });
  }
}

module.exports = { HitlPage };
