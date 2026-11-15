/* Map initialization and rendering using Leaflet.js */

let map;
let droneMarkers = new Map(); // swarm_id-drone_id -> L.marker
let targetAreaLayer = null;
let threatLayerGroup = null;
let targetEntityLayerGroup = null;
let _lineageObjectUrls = [];

function _buildSafePopupElement(title, rows) {
    const container = document.createElement('div');
    const heading = document.createElement('strong');
    heading.textContent = String(title);
    container.appendChild(heading);

    for (const [label, value] of rows) {
        const line = document.createElement('div');
        line.textContent = `${label}: ${value}`;
        container.appendChild(line);
    }
    return container;
}

/**
 * Initialize the Leaflet map in the #tactical-map container.
 */
function initMap() {
    map = L.map('tactical-map').setView([52.5200, 13.4050], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    threatLayerGroup = L.layerGroup().addTo(map);
    targetEntityLayerGroup = L.layerGroup().addTo(map);
    console.log("Tactical map initialized");
}

/**
 * Update the map with current drone positions using safe DOM popups.
 * @param {string} swarmId - The ID of the swarm
 * @param {Array} drones - Array of drone objects from telemetry API
 */
function updateDronePositions(swarmId, drones) {
    if (!map) return;

    const currentIds = new Set();

    drones.forEach(drone => {
        if (!drone.position || drone.position.lat == null || drone.position.lng == null) {
            return;
        }
        const markerId = `${swarmId}-${drone.id}`;
        currentIds.add(markerId);
        const popupEl = _buildSafePopupElement(drone.id, [
            ['Alt', `${drone.position.alt_m ?? 'n/a'}m`],
            ['Bat', `${drone.battery_pct ?? 'n/a'}%`],
            ['Task', `${drone.current_mission || 'unknown'}`]
        ]);

        if (droneMarkers.has(markerId)) {
            const marker = droneMarkers.get(markerId);
            marker.setLatLng([drone.position.lat, drone.position.lng]);
            marker.setPopupContent(popupEl);
        } else {
            const marker = L.circleMarker([drone.position.lat, drone.position.lng], {
                color: '#3b82f6',
                fillColor: '#3b82f6',
                fillOpacity: 0.8,
                radius: 6,
                className: 'drone-marker'
            }).addTo(map);

            marker.bindPopup(popupEl);
            droneMarkers.set(markerId, marker);
        }
    });

    for (const [id, marker] of droneMarkers.entries()) {
        if (!currentIds.has(id)) {
            map.removeLayer(marker);
            droneMarkers.delete(id);
        }
    }
}

/**
 * Render active Memgraph ThreatZones cleanly.
 */
function renderThreatZones(threats = [], onDeactivate = null) {
    if (!map) return;
    if (!threatLayerGroup) {
        threatLayerGroup = L.layerGroup().addTo(map);
    }
    threatLayerGroup.clearLayers();

    for (const threat of threats) {
        const layer = L.circle([threat.lat, threat.lon], {
            radius: threat.radius_m || 500,
            color: threat.severity === 'critical' ? '#dc2626' : '#f97316',
            fillColor: '#ef4444',
            fillOpacity: 0.2,
            weight: 2,
            className: 'threat-zone-layer'
        });

        const popupEl = _buildSafePopupElement(threat.name || 'Threat Zone', [
            ['Type', `${threat.threat_type || 'RESTRICTED'} (${threat.severity || 'high'})`],
            ['Alt Envelope', `${threat.min_alt_m ?? 0}m - ${threat.max_alt_m ?? 500}m`],
            ['Source', threat.source || 'memgraph']
        ]);

        if (typeof onDeactivate === 'function' && threat.active !== false) {
            const controls = document.createElement('div');
            controls.style.marginTop = '0.5rem';

            const reasonInput = document.createElement('input');
            reasonInput.type = 'text';
            reasonInput.placeholder = 'Deactivation reason (>=5 chars)';
            reasonInput.style.width = '100%';
            reasonInput.style.marginBottom = '0.35rem';

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = 'Deactivate Threat';
            btn.className = 'btn btn--danger';
            btn.addEventListener('click', () => {
                const reason = reasonInput.value.trim();
                if (reason.length >= 5) {
                    onDeactivate(threat.threat_id, reason);
                } else {
                    reasonInput.focus();
                }
            });
            controls.append(reasonInput, btn);
            popupEl.appendChild(controls);
        }

        layer.bindPopup(popupEl);
        layer.addTo(threatLayerGroup);

        if (threat.polygon_geojson) {
            L.geoJSON(threat.polygon_geojson, {
                style: { color: '#dc2626', weight: 2, fillOpacity: 0.15 }
            }).addTo(threatLayerGroup);
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
/**
 * Render correlated TargetEntity markers on the map and open Target Lineage modal cleanly.
 */
function renderTargets(targets = [], onSelectTarget = null) {
    if (!map) return;
    if (!targetEntityLayerGroup) {
        targetEntityLayerGroup = L.layerGroup().addTo(map);
    }
    targetEntityLayerGroup.clearLayers();

    for (const target of targets) {
        if (target.last_lat == null || target.last_lon == null) continue;
        const color = target.status === 'confirmed' ? '#22c55e' : '#eab308';
        const marker = L.circleMarker([target.last_lat, target.last_lon], {
            radius: 8,
            color,
            fillColor: color,
            fillOpacity: 0.85,
            className: 'target-entity-marker'
        });

        const popupEl = _buildSafePopupElement(
            `${String(target.canonical_class || 'target').toUpperCase()} (${target.status})`,
            [
                ['Observations', String(target.observation_count || 1)],
                ['Target ID', String(target.target_id || '')]
            ]
        );
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn--secondary';
        btn.style.marginTop = '0.4rem';
        btn.textContent = 'View Target Lineage';
        btn.addEventListener('click', () => {
            if (typeof onSelectTarget === 'function') {
                onSelectTarget(target.target_id);
            } else {
                openTargetLineageModal(target.target_id);
            }
        });
        popupEl.appendChild(btn);

        marker.bindPopup(popupEl);
        marker.addTo(targetEntityLayerGroup);
    }
}

function _cleanupLineageObjectUrls() {
    for (const url of _lineageObjectUrls) {
        URL.revokeObjectURL(url);
    }
    _lineageObjectUrls = [];
}

async function openTargetLineageModal(targetId, onReviewed = null) {
    const modal = document.getElementById('target-lineage-modal');
    const titleEl = document.getElementById('lineage-title');
    const bodyEl = document.getElementById('lineage-observations');
    const errorEl = document.getElementById('lineage-error');
    const confirmBtn = document.getElementById('lineage-confirm');
    const closeBtn = document.getElementById('lineage-close');
    if (!modal || !titleEl || !bodyEl) return;

    _cleanupLineageObjectUrls();
    if (errorEl) {
        errorEl.textContent = '';
        errorEl.hidden = true;
    }

    try {
        const lineage = await window.ApiClient.fetchTargetLineage(targetId);
        titleEl.textContent = `Target Lineage — ${String(lineage.canonical_class || '').toUpperCase()} (${lineage.status})`;

        const cards = [];
        for (const obs of lineage.observations || []) {
            const card = document.createElement('div');
            card.style.padding = '0.5rem';
            card.style.marginBottom = '0.5rem';
            card.style.border = '1px solid #374151';
            card.style.borderRadius = '4px';

            const hdr = document.createElement('div');
            hdr.textContent = `Drone: ${obs.drone_id} | Conf: ${(Number(obs.confidence || 0) * 100).toFixed(0)}% | Method: ${obs.match_method}`;
            const meta = document.createElement('div');
            meta.style.fontSize = '0.85rem';
            meta.textContent = `Detected: ${obs.detected_at} (${Number(obs.lat).toFixed(4)}, ${Number(obs.lon).toFixed(4)})`;
            card.append(hdr, meta);

            if (obs.snapshot_proxy_url && window.ApiClient.fetchSnapshotBlobUrl) {
                const imgWrap = document.createElement('div');
                imgWrap.style.marginTop = '0.35rem';
                card.appendChild(imgWrap);
                window.ApiClient.fetchSnapshotBlobUrl(obs.snapshot_proxy_url).then((blobUrl) => {
                    if (blobUrl) {
                        _lineageObjectUrls.push(blobUrl);
                        const img = document.createElement('img');
                        img.src = blobUrl;
                        img.alt = `Snapshot ${obs.target_class}`;
                        img.style.maxWidth = '160px';
                        img.style.borderRadius = '4px';
                        imgWrap.replaceChildren(img);
                    }
                }).catch(() => {});
            }

            if ((lineage.observations || []).length > 1) {
                const splitBtn = document.createElement('button');
                splitBtn.type = 'button';
                splitBtn.className = 'btn btn--secondary';
                splitBtn.style.marginTop = '0.35rem';
                splitBtn.textContent = 'Split Observation';
                splitBtn.addEventListener('click', async () => {
                    try {
                        await window.ApiClient.reviewTarget(targetId, 'split_event', obs.event_id);
                        _cleanupLineageObjectUrls();
                        modal.close();
                        if (typeof onReviewed === 'function') onReviewed();
                    } catch (err) {
                        if (errorEl) {
                            errorEl.textContent = err.message || 'Split failed';
                            errorEl.hidden = false;
                        }
                    }
                });
                card.appendChild(splitBtn);
            }

            cards.push(card);
        }
        bodyEl.replaceChildren(...cards);

        if (confirmBtn) {
            confirmBtn.onclick = async () => {
                try {
                    await window.ApiClient.reviewTarget(targetId, 'confirm');
                    _cleanupLineageObjectUrls();
                    modal.close();
                    if (typeof onReviewed === 'function') onReviewed();
                } catch (err) {
                    if (errorEl) {
                        errorEl.textContent = err.message || 'Confirm failed';
                        errorEl.hidden = false;
                    }
                }
            };
        }
        if (closeBtn) {
            closeBtn.onclick = () => {
                _cleanupLineageObjectUrls();
                modal.close();
            };
        }

        modal.showModal();
    } catch (err) {
        if (errorEl) {
            errorEl.textContent = err.message || 'Failed to load lineage';
            errorEl.hidden = false;
        }
    }
}

window.MapController = {
    initMap,
    updateDronePositions,
    renderThreatZones,
    renderTargets,
    openTargetLineageModal,
    drawTargetArea,
    getDroneMarkers: () => droneMarkers,
    getTargetAreaLayer: () => targetAreaLayer,
    getThreatLayerGroup: () => threatLayerGroup,
    getTargetEntityLayerGroup: () => targetEntityLayerGroup
};
