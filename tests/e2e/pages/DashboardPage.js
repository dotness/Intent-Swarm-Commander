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
    this.historyList = page.locator('#history-list');

    // Create Swarm modal locators
    this.createSwarmBtn = page.locator('#btn-create-swarm');
    this.createSwarmModal = page.locator('#create-swarm-modal');
    this.createSwarmNameInput = page.locator('#create-swarm-name');
    this.createSwarmDronesInput = page.locator('#create-swarm-drones');
    this.createSwarmSubmitBtn = page.locator('#create-swarm-submit');
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

  /**
   * Provision a new swarm via the dashboard modal
   * @param {string} name
   * @param {number} [droneCount=3]
   */
  async provisionSwarm(name, droneCount = 3) {
    await this.createSwarmBtn.click();
    await expect(this.createSwarmModal).toBeVisible();
    await this.createSwarmNameInput.fill(name);
    await this.createSwarmDronesInput.fill(String(droneCount));
    await this.createSwarmSubmitBtn.click();
    await expect(this.createSwarmModal).toBeHidden();

    // Verify the newly created swarm is present and selected
    await expect(this.swarmSelect).toContainText(name);
    const selectedOption = await this.swarmSelect.locator('option:checked').textContent();
    expect(selectedOption).toContain(name);
  }

  /**
   * Check if history contains a specific text snippet
   * @param {string | RegExp} snippet
   */
  async expectHistoryContains(snippet) {
    await expect(this.historyList).toContainText(snippet);
  }

  /**
   * Retrieve all text items from the activity history
   */
  async getHistoryItems() {
    return await this.historyList.locator('li').allTextContents();
  }
}

module.exports = { DashboardPage };
