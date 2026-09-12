// @ts-check
const { expect } = require('@playwright/test');

/**
 * Page Object representing the main tactical dashboard header and controls
 */
class DashboardPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
    this.brandTitle = page.locator('.topbar__brand h1');
    this.authIndicator = page.locator('#auth-indicator');
    this.authBadge = page.locator('.auth-badge');
    this.swarmSelect = page.locator('#swarm-select');
    this.smeacPanel = page.locator('#smeac-panel');
    this.mapPanel = page.locator('#map-panel');
  }

  async expectLoaded() {
    await expect(this.brandTitle).toHaveText('Intent Swarm Commander');
    await expect(this.smeacPanel).toBeVisible();
    await expect(this.mapPanel).toBeVisible();
  }

  /**
   * @param {string} [commanderId]
   */
  async expectAuthenticated(commanderId) {
    await expect(this.authBadge).toBeVisible();
    await expect(this.authBadge).toHaveClass(/auth-badge--authenticated/);
    if (commanderId) {
      await expect(this.authBadge).toContainText(commanderId);
    }
  }

  async expectUnauthenticated() {
    await expect(this.authBadge).toBeVisible();
    await expect(this.authBadge).toHaveClass(/auth-badge--unauthenticated/);
    await expect(this.authBadge).toContainText('Not Authenticated');
  }

  /**
   * Returns list of option values in the swarm selector
   */
  async getSwarmOptions() {
    await this.swarmSelect.waitFor();
    return await this.swarmSelect.locator('option').allTextContents();
  }

  /**
   * @param {string} swarmId
   */
  async selectSwarm(swarmId) {
    await this.swarmSelect.selectOption(swarmId);
  }

  /**
   * Selects the first available non-empty swarm option
   */
  async selectFirstAvailableSwarm() {
    await expect(async () => {
      const count = await this.swarmSelect.locator('option').count();
      expect(count).toBeGreaterThan(1);
    }).toPass({ timeout: 10000 });

    const options = await this.swarmSelect.locator('option').all();
    for (let i = 1; i < options.length; i++) {
      const val = await options[i].getAttribute('value');
      if (val) {
        await this.swarmSelect.selectOption(val);
        return val;
      }
    }
    throw new Error('No valid swarm option found');
  }
}

module.exports = { DashboardPage };
