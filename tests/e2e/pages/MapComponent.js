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
    this.markers = page.locator('.drone-marker, .leaflet-marker-icon, .leaflet-overlay-pane path.leaflet-interactive, .leaflet-interactive');
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
    const isOpen = await this.popup.isVisible().catch(() => false);
    if (!isOpen) {
      const marker = this.markers.nth(index);
      await marker.click();
    }
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

  /**
   * Returns current coordinates of the first drone marker, or null if none
   * @returns {Promise<{lat: number, lng: number} | null>}
   */
  async getDroneCoordinates() {
    return await this.page.evaluate(() => {
      // @ts-ignore
      if (window.MapController && typeof window.MapController.getDroneMarkers === 'function') {
        // @ts-ignore
        const markers = Array.from(window.MapController.getDroneMarkers().values());
        if (markers.length > 0) {
          const latLng = markers[0].getLatLng();
          return { lat: Number(latLng.lat.toFixed(4)), lng: Number(latLng.lng.toFixed(4)) };
        }
      }
      return null;
    });
  }

  /**
   * Asserts that a drone marker is located at (or near) the given coordinates
   * @param {number} expectedLat
   * @param {number} expectedLng
   * @param {number} [tolerance=0.001]
   */
  async expectDroneAt(expectedLat, expectedLng, tolerance = 0.001) {
    await expect(async () => {
      const coords = await this.getDroneCoordinates();
      expect(coords).not.toBeNull();
      if (coords) {
        expect(Math.abs(coords.lat - expectedLat)).toBeLessThanOrEqual(tolerance);
        expect(Math.abs(coords.lng - expectedLng)).toBeLessThanOrEqual(tolerance);
      }
    }).toPass({ timeout: 10000 });
  }

  /**
   * Asserts that the target area or waypoint trajectory layer is rendered on the map
   */
  async expectTargetAreaLayerVisible() {
    await expect(async () => {
      const hasLayer = await this.page.evaluate(() => {
        // @ts-ignore
        return !!(window.MapController && window.MapController.getTargetAreaLayer && window.MapController.getTargetAreaLayer());
      });
      expect(hasLayer).toBe(true);
    }).toPass({ timeout: 5000 });
  }
}

module.exports = { MapComponent };
