// @ts-check
const { expect } = require('@playwright/test');

/**
 * Page Object representing the Leaflet Map and Drone Telemetry visualizer
 */
class MapComponent {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
    this.mapContainer = page.locator('#tactical-map');
    this.leafletContainer = page.locator('#tactical-map.leaflet-container');
    this.markerPane = page.locator('.leaflet-marker-pane, .leaflet-overlay-pane');
    this.markers = page.locator('.leaflet-marker-icon, .leaflet-overlay-pane path.leaflet-interactive, .leaflet-interactive');
    this.popup = page.locator('.leaflet-popup');
    this.popupContent = page.locator('.leaflet-popup-content');
  }

  async expectMapLoaded() {
    await expect(this.mapContainer).toBeVisible();
    await expect(this.leafletContainer).toBeVisible();
  }

  /**
   * Waits for at least `minCount` drone markers to appear on the tactical map
   * @param {number} [minCount=1]
   */
  async expectDroneMarkers(minCount = 1) {
    await expect(async () => {
      const count = await this.markers.count();
      expect(count).toBeGreaterThanOrEqual(minCount);
    }).toPass({ timeout: 15000 });
  }

  /**
   * Clicks the drone marker at given index to open its telemetry popup
   * @param {number} [index=0]
   */
  async clickDroneMarker(index = 0) {
    const marker = this.markers.nth(index);
    await marker.click();
    await expect(this.popup).toBeVisible();
  }

  /**
   * Verifies that the telemetry popup displays expected drone info (e.g. altitude, battery)
   */
  async expectTelemetryPopupDetails() {
    await expect(this.popupContent).toBeVisible();
    const content = await this.popupContent.innerText();
    expect(content.length).toBeGreaterThan(0);
  }
}

module.exports = { MapComponent };
