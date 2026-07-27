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
        return await res.json();
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
        
        return await res.json();
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
        return await res.json();
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
        return await res.json();
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
