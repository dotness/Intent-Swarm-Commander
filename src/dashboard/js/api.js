/* API interactions */

const API_BASE = "http://localhost:8000/api/v1";
// Mock token for MVP
const AUTH_HEADER = { 'Authorization': 'Bearer placeholder-token' };

/**
 * Fetch available swarms to populate the select dropdown.
 */
async function fetchSwarms() {
    try {
        const res = await fetch(`${API_BASE}/swarms`, { headers: AUTH_HEADER });
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
                ...AUTH_HEADER
            },
            body: JSON.stringify(orderData)
        });
        
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
        const res = await fetch(`${API_BASE}/swarms/${swarmId}/hitl/pending`, { headers: AUTH_HEADER });
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
    // Placeholder telemetry generation to make the dashboard alive
    // In full implementation, this calls /api/v1/swarms/{swarm_id}/telemetry
    return {
        drones: [
            { id: "UAV-Alpha-1", position: { lat: 52.5200 + Math.random()*0.01, lng: 13.4050 + Math.random()*0.01, alt_m: 200 }, battery_pct: 85, current_mission: "recon" },
            { id: "UAV-Alpha-2", position: { lat: 52.5250 + Math.random()*0.01, lng: 13.4100 + Math.random()*0.01, alt_m: 200 }, battery_pct: 82, current_mission: "recon" }
        ]
    };
}

window.ApiClient = {
    fetchSwarms,
    submitSmeac,
    checkPendingHitl,
    fetchTelemetry
};
