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
        const res = await fetch(`${API_BASE}/swarms/${swarmId}/orders`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...window.authManager.getAuthHeader()
            },
            body: JSON.stringify(orderData)
        });
        
        if (res.status === 401) { window.authManager.clearSession(); throw new Error("Unauthorized"); }
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Submission failed");
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
 * Poll for telemetry (simulated data for MVP).
 * The actual endpoint will be implemented in Phase 10.
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
        // Normalize single drone telemetry returned directly from edge drone
        return {
            drones: [
                {
                    id: `${swarmId}-drone-1`,
                    status: json.status || 'idle',
                    battery_pct: json.battery !== undefined ? json.battery : 100,
                    position: {
                        lat: (json.position && json.position.lat !== undefined) ? json.position.lat : 52.5200,
                        lng: (json.position && (json.position.lng !== undefined ? json.position.lng : json.position.lon)) !== undefined ? (json.position.lng || json.position.lon) : 13.4050,
                        alt_m: (json.position && json.position.alt !== undefined) ? json.position.alt : 50.0
                    },
                    heading: json.heading || 0,
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

window.ApiClient = {
    fetchSwarms,
    submitSmeac,
    checkPendingHitl,
    fetchTelemetry
};
