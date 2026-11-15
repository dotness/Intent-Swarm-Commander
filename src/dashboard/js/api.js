/* API interactions */

const API_BASE = "http://localhost:8000/api/v1";

/**
 * Fetch available swarms to populate the select dropdown.
 */
async function fetchSwarms() {
    try {
        const res = await fetch(`${API_BASE}/swarms`, { headers: window.authManager.getAuthHeader() });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) throw new Error("Failed to fetch swarms");
        const json = await res.json();
        return { swarms: json.swarms || json.data || [] };
    } catch (e) {
        console.error(e);
        return { swarms: [] };
    }
}

/**
 * Submit a SMEAC order to a specific swarm.
 */
async function submitSmeac(swarmId, orderData) {
    try {
        const payload = { project_id: getActiveProjectId(), ...orderData };
        const res = await fetch(`${API_BASE}/swarms/${swarmId}/orders`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...window.authManager.getAuthHeader()
            },
            body: JSON.stringify(payload)
        });
        
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || err.detail || "Submission failed");
        }
        
        const json = await res.json();
        return json.data || json;
    } catch (e) {
        console.error(e);
        throw e;
    }
}

/**
 * Poll for HITL decisions.
 */
async function checkPendingHitl(swarmId) {
    try {
        const res = await fetch(`${API_BASE}/swarms/${swarmId}/hitl/pending`, { headers: window.authManager.getAuthHeader() });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) return { pending: [] };
        const json = await res.json();
        return { pending: json.pending || json.data || [] };
    } catch (e) {
        return { pending: [] };
    }
}

/**
 * Fetch latest MQTT-ingested telemetry state via central ISC API facade.
 */
async function fetchTelemetry(swarmId) {
    try {
        const res = await fetch(`${API_BASE}/swarms/${swarmId}/telemetry`, { headers: window.authManager.getAuthHeader() });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) throw new Error("Failed to fetch telemetry");
        const json = await res.json();
        if (json && Array.isArray(json.drones)) {
            return json;
        }
        const pos = json.position || {};
        return {
            drones: [
                {
                    id: `${swarmId}-drone-1`,
                    status: json.status || 'unknown',
                    battery_pct: json.battery !== undefined ? json.battery : null,
                    position: {
                        lat: pos.lat ?? null,
                        lng: pos.lng ?? pos.lon ?? null,
                        alt_m: pos.alt ?? pos.alt_m ?? null
                    },
                    heading: json.heading ?? 0,
                    speed: json.speed || 0,
                    current_mission: json.status || 'patrol'
                }
            ]
        };
    } catch (e) {
        console.error(e);
        return { drones: [] };
    }
}

/**
 * Provision a new swarm instance.
 */
async function createSwarm(swarmData) {
    try {
        const res = await fetch(`${API_BASE}/swarms`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...window.authManager.getAuthHeader()
            },
            body: JSON.stringify(swarmData)
        });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || err.detail || "Failed to create swarm");
        }
        const json = await res.json();
        return json.data || json;
    } catch (e) {
        console.error(e);
        throw e;
    }
}

/**
 * Get status of an existing order.
 */
async function getOrderStatus(swarmId, orderId) {
    try {
        const res = await fetch(`${API_BASE}/swarms/${swarmId}/orders/${orderId}`, {
            headers: window.authManager.getAuthHeader()
        });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || err.detail || "Failed to fetch order status");
        }
        const json = await res.json();
        return json.data || json;
    } catch (e) {
        console.error(e);
        throw e;
    }
}

function getActiveProjectId() {
    const el = document.getElementById('project-id-input');
    const val = el && el.value ? el.value.trim() : '';
    return val || 'default-theater';
}

async function fetchThreats(projectId = getActiveProjectId(), includeInactive = false) {
    try {
        const params = new URLSearchParams({ project_id: projectId, include_inactive: String(includeInactive) });
        const res = await fetch(`${API_BASE}/threats?${params.toString()}`, { headers: window.authManager.getAuthHeader() });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) throw new Error("Failed to fetch threats");
        const json = await res.json();
        const data = json.data || {};
        return {
            threats: data.threats || [],
            meta: json.meta || {}
        };
    } catch (e) {
        console.error(e);
        return { threats: [], meta: {} };
    }
}

async function createThreat(threatPayload) {
    const payload = { project_id: getActiveProjectId(), ...threatPayload };
    const res = await fetch(`${API_BASE}/threats`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...window.authManager.getAuthHeader()
        },
        body: JSON.stringify(payload)
    });
    if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Failed to create threat");
    }
    const json = await res.json();
    return json.data || json;
}

async function deactivateThreat(threatId, reason, projectId = getActiveProjectId()) {
    const res = await fetch(`${API_BASE}/threats/${encodeURIComponent(threatId)}/deactivate`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
            ...window.authManager.getAuthHeader()
        },
        body: JSON.stringify({ project_id: projectId, reason })
    });
    if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Failed to deactivate threat");
    }
    const json = await res.json();
    return json.data || json;
}

async function fetchTargets(projectId = getActiveProjectId()) {
    try {
        const params = new URLSearchParams({ project_id: projectId });
        const res = await fetch(`${API_BASE}/targets?${params.toString()}`, { headers: window.authManager.getAuthHeader() });
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) return [];
        const json = await res.json();
        return (json.data && json.data.items) || [];
    } catch (e) {
        console.error(e);
        return [];
    }
}

async function fetchTargetLineage(targetId, projectId = getActiveProjectId()) {
    const params = new URLSearchParams({ project_id: projectId });
    const res = await fetch(`${API_BASE}/targets/${encodeURIComponent(targetId)}/lineage?${params.toString()}`, {
        headers: window.authManager.getAuthHeader()
    });
    if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Failed to load target lineage");
    }
    const json = await res.json();
    return json.data || json;
}

async function reviewTarget(targetId, action, splitEventId = null, projectId = getActiveProjectId()) {
    const res = await fetch(`${API_BASE}/targets/${encodeURIComponent(targetId)}/review`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...window.authManager.getAuthHeader()
        },
        body: JSON.stringify({
            project_id: projectId,
            action,
            split_event_id: splitEventId
        })
    });
    if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Failed to submit target review");
    }
    const json = await res.json();
    return json.data || json;
}

async function fetchSnapshotBlobUrl(proxyUrl) {
    const url = proxyUrl.startsWith('http') ? proxyUrl : `http://localhost:8000${proxyUrl}`;
    const res = await fetch(url, { headers: window.authManager.getAuthHeader() });
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
}

async function fetchAar(queryType = 'summary', swarmId = null, projectId = getActiveProjectId()) {
    const params = new URLSearchParams({ project_id: projectId, query_type: queryType });
    if (swarmId) params.set('swarm_id', swarmId);
    const res = await fetch(`${API_BASE}/analytics/aar?${params.toString()}`, {
        headers: window.authManager.getAuthHeader()
    });
    if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Failed to fetch AAR report");
    }
    const json = await res.json();
    return json.data || json;
}

async function draftSmeacWithCopilot(commanderIntent, projectId = getActiveProjectId()) {
    const res = await fetch(`${API_BASE}/smeac/draft`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...window.authManager.getAuthHeader()
        },
        body: JSON.stringify({
            project_id: projectId,
            commander_intent: commanderIntent,
            include_aar_context: true,
            include_threat_context: true
        })
    });
    if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Copilot draft generation failed");
    }
    const json = await res.json();
    return { draft: json.data, meta: json.meta || {} };
}

window.ApiClient = Object.assign(window.ApiClient || {}, {
    getActiveProjectId,
    fetchSwarms,
    createSwarm,
    submitSmeac,
    getOrderStatus,
    checkPendingHitl,
    fetchTelemetry,
    fetchThreats,
    createThreat,
    deactivateThreat,
    fetchTargets,
    fetchTargetLineage,
    reviewTarget,
    fetchSnapshotBlobUrl,
    fetchAar,
    draftSmeacWithCopilot
});
