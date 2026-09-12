// @ts-check
const { expect } = require('@playwright/test');

/**
 * Page Object representing the Commander Login Modal and authentication interactions
 */
class LoginPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
    this.modal = page.locator('#login-modal');
    this.commanderInput = page.locator('#login-commander-id');
    this.passphraseInput = page.locator('#login-passphrase');
    this.submitButton = page.locator('#login-form button[type="submit"]');
    this.errorBanner = page.locator('#login-error');
  }

  async goto() {
    await this.page.goto('/');
  }

  async expectModalVisible() {
    await expect(this.modal).toBeVisible();
    await expect(this.commanderInput).toBeVisible();
    await expect(this.passphraseInput).toBeVisible();
  }

  async expectModalHidden() {
    await expect(this.modal).toBeHidden();
  }

  /**
   * @param {string} commanderId
   * @param {string} passphrase
   */
  async login(commanderId, passphrase) {
    await this.commanderInput.fill(commanderId);
    await this.passphraseInput.fill(passphrase);
    await this.submitButton.click();
  }

  /**
   * @param {string | RegExp} expectedText
   */
  async expectError(expectedText) {
    await expect(this.errorBanner).toBeVisible();
    await expect(this.errorBanner).toContainText(expectedText);
  }
}

module.exports = { LoginPage };
