/* Map initialization and rendering using Leaflet.js */

let map;
let droneMarkers = new Map(); // swarm_id-drone_id -> L.marker
let targetAreaLayer = null;

/**
 * Initialize the Leaflet map in the #tactical-map container.
 */
function initMap() {
    // Default center (e.g., somewhere in Europe for MVP)
    map = L.map('tactical-map').setView([52.5200, 13.4050], 13);

    // Standard OpenStreetMap tiles (free, no API key required for MVP)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    console.log("Tactical map initialized");
}

/**
 * Update the map with current drone positions.
 * @param {string} swarmId - The ID of the swarm
 * @param {Array} drones - Array of drone objects from telemetry API
 */
function updateDronePositions(swarmId, drones) {
    if (!map) return;

    const currentIds = new Set();

    drones.forEach(drone => {
        const markerId = `${swarmId}-${drone.id}`;
        currentIds.add(markerId);

        if (droneMarkers.has(markerId)) {
            // Update existing marker
            const marker = droneMarkers.get(markerId);
            marker.setLatLng([drone.position.lat, drone.position.lng]);
            marker.setPopupContent(`
                <strong>${drone.id}</strong><br>
                Alt: ${drone.position.alt_m}m<br>
                Bat: ${drone.battery_pct}%<br>
                Task: ${drone.current_mission}
            `);
        } else {
            // Create new marker
            // MVP: simple blue circle marker
            const marker = L.circleMarker([drone.position.lat, drone.position.lng], {
                color: '#3b82f6',
                fillColor: '#3b82f6',
                fillOpacity: 0.8,
                radius: 6,
                className: 'drone-marker'
            }).addTo(map);
            
            marker.bindPopup(`
                <strong>${drone.id}</strong><br>
                Alt: ${drone.position.alt_m}m<br>
                Bat: ${drone.battery_pct}%<br>
                Task: ${drone.current_mission}
            `);
            
            droneMarkers.set(markerId, marker);
        }
    });

    // Clean up old markers
    for (const [id, marker] of droneMarkers.entries()) {
        if (!currentIds.has(id)) {
            map.removeLayer(marker);
            droneMarkers.delete(id);
        }
    }
}

/**
 * Draw a target area polygon on the map.
 * @param {Object} geoJson - GeoJSON geometry object
 */
function drawTargetArea(geoJson) {
    if (!map) return;

    if (targetAreaLayer) {
        map.removeLayer(targetAreaLayer);
    }

    if (geoJson && (geoJson.type === 'Polygon' || geoJson.type === 'Point' || geoJson.type === 'LineString')) {
        targetAreaLayer = L.geoJSON(geoJson, {
            style: {
                color: '#ef4444',
                weight: 3,
                dashArray: '6, 6',
                fillOpacity: 0.2
            }
        }).addTo(map);

        // Fit map bounds to show the area or flight corridor
        if (geoJson.type === 'Polygon' || geoJson.type === 'LineString') {
            map.fitBounds(targetAreaLayer.getBounds(), { padding: [30, 30] });
        } else {
            map.setView(targetAreaLayer.getBounds().getCenter(), 15);
        }
    }
}

// Export for use in main.js and test harness
window.MapController = {
    initMap,
    updateDronePositions,
    drawTargetArea,
    getDroneMarkers: () => droneMarkers,
    getTargetAreaLayer: () => targetAreaLayer
};
