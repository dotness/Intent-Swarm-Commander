/* Main dashboard entry point */

let currentSwarmId = null;
let telemetryInterval = null;
let hitlInterval = null;

/**
 * Initialize the application on DOMContentLoaded.
 */
document.addEventListener("DOMContentLoaded", async () => {
    console.log("ISC Dashboard initializing...");
    
    // Init components
    window.AuthIndicator.update();
    window.MapController.initMap();
    window.HitlController.init();
    loadHistory();

    // Wire up the SMEAC form
    document.getElementById("smeac-form").addEventListener("submit", handleSmeacSubmit);

    // Wire up Create Swarm Modal
    const createSwarmBtn = document.getElementById("btn-create-swarm");
    const createSwarmModal = document.getElementById("create-swarm-modal");
    const createSwarmForm = document.getElementById("create-swarm-form");
    const createSwarmCancel = document.getElementById("create-swarm-cancel");

    if (createSwarmBtn && createSwarmModal) {
        createSwarmBtn.addEventListener("click", () => {
            const errorDiv = document.getElementById("create-swarm-error");
            if (errorDiv) errorDiv.hidden = true;
            createSwarmModal.showModal();
        });
    }
    if (createSwarmCancel && createSwarmModal) {
        createSwarmCancel.addEventListener("click", () => {
            createSwarmModal.close();
        });
    }
    if (createSwarmForm && createSwarmModal) {
        createSwarmForm.addEventListener("submit", handleCreateSwarmSubmit);
    }
    
    // Handle swarm selection changes
    const swarmSelect = document.getElementById("swarm-select");
    swarmSelect.addEventListener("change", (e) => {
        const swarmId = e.target.value;
        if (swarmId) {
            selectSwarm(swarmId);
        }
    });

    // Populate swarms
    await loadSwarms();

    // Reload swarms when authentication status changes
    window.addEventListener('auth-changed', async (e) => {
        if (e.detail && e.detail.authenticated) {
            await loadSwarms();
        }
    });
});

/**
 * Fetch and populate the swarm selector.
 */
async function loadSwarms() {
    const data = await window.ApiClient.fetchSwarms();
    const select = document.getElementById("swarm-select");
    
    // Clear existing options except the first placeholder
    while (select.options.length > 1) {
        select.remove(1);
    }

    data.swarms.forEach(swarm => {
        const option = document.createElement("option");
        option.value = swarm.id;
        option.textContent = `${swarm.name} (${swarm.status})`;
        select.appendChild(option);
    });

    // If swarms exist, auto-select the first one
    if (data.swarms.length > 0) {
        select.value = data.swarms[0].id;
        selectSwarm(data.swarms[0].id);
    }
}

/**
 * Switch the active swarm context and start polling.
 */
function selectSwarm(swarmId) {
    console.log(`Swarm selected: ${swarmId}`);
    currentSwarmId = swarmId;

    // Clear old intervals
    if (telemetryInterval) clearInterval(telemetryInterval);
    if (hitlInterval) clearInterval(hitlInterval);

    // Initial fetch
    pollTelemetry();
    pollHitl();

    // Set polling intervals
    telemetryInterval = setInterval(pollTelemetry, 200); // 5 Hz polling rate per SC-002
    hitlInterval = setInterval(pollHitl, 5000);
}

/**
 * Handle Provision Swarm form submission.
 */
async function handleCreateSwarmSubmit(event) {
    event.preventDefault();
    const form = event.target;
    const submitBtn = document.getElementById("create-swarm-submit");
    const errorDiv = document.getElementById("create-swarm-error");
    const modal = document.getElementById("create-swarm-modal");

    const name = document.getElementById("create-swarm-name").value.trim();
    const droneCount = parseInt(document.getElementById("create-swarm-drones").value, 10) || 3;

    try {
        submitBtn.disabled = true;
        submitBtn.textContent = "Provisioning...";
        if (errorDiv) errorDiv.hidden = true;

        let swarm;
        if (window.ApiClient && typeof window.ApiClient.createSwarm === 'function') {
            swarm = await window.ApiClient.createSwarm({
                name: name,
                drone_count: droneCount
            });
        } else {
            const authHeader = (window.authManager && window.authManager.getAuthHeader) ? window.authManager.getAuthHeader() : {};
            const res = await fetch("http://localhost:8000/api/v1/swarms", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...authHeader
                },
                body: JSON.stringify({ name: name, drone_count: droneCount })
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || err.detail || "Failed to create swarm");
            }
            const json = await res.json();
            swarm = json.data || json;
        }

        form.reset();
        modal.close();
        logHistory(`Swarm '${swarm.name}' provisioned (${swarm.id})`);

        // Refresh swarm selector and select newly created swarm
        await loadSwarms();
        const select = document.getElementById("swarm-select");
        if (select) {
            select.value = swarm.id;
            selectSwarm(swarm.id);
        }
    } catch (e) {
        if (errorDiv) {
            errorDiv.hidden = false;
            errorDiv.textContent = e.message || "Failed to create swarm";
        }
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Provision";
    }
}

/**
 * Handle SMEAC form submission.
 */
async function handleSmeacSubmit(event) {
    event.preventDefault();
    
    if (!currentSwarmId) {
        alert("Please select a swarm first.");
        return;
    }

    const form = event.target;
    const submitBtn = document.getElementById("smeac-submit");
    const resultDiv = document.getElementById("smeac-result");
    
    const orderData = {
        situation: form.situation.value,
        mission: form.mission.value,
        execution: form.execution.value,
        admin_logistics: form.admin_logistics.value || null,
        command_signal: form.command_signal.value || null
    };

    try {
        submitBtn.disabled = true;
        submitBtn.textContent = "Submitting...";
        
        const result = await window.ApiClient.submitSmeac(currentSwarmId, orderData);
        
        form.reset();
        resultDiv.hidden = false;
        resultDiv.innerHTML = `
            <div style="color: var(--color-success); font-weight: bold; margin-bottom: 0.5rem;">✅ Order Submitted Successfully</div>
            <div>Order ID: <span id="smeac-submitted-id">${result.order_id}</span></div>
            <div style="color: var(--color-primary); font-size: 0.85rem; margin-top: 0.25rem;">Status: Executed</div>
        `;
        
        logHistory(`SMEAC Order ${result.order_id} executed`);
        
        // Hide result after 5s
        setTimeout(() => {
            resultDiv.hidden = true;
        }, 5000);
        
    } catch (e) {
        resultDiv.hidden = false;
        resultDiv.innerHTML = `
            <div style="color: var(--color-danger); font-weight: bold; margin-bottom: 0.5rem;">❌ Submission Failed</div>
            <div>${e.message}</div>
        `;
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit Order";
    }
}

/**
 * Update the telemetry map and roster.
 */
async function pollTelemetry() {
    if (!currentSwarmId) return;
    
    const data = await window.ApiClient.fetchTelemetry(currentSwarmId);
    
    // Update Map
    window.MapController.updateDronePositions(currentSwarmId, data.drones);
    
    // Update Roster Table
    const tbody = document.getElementById("roster-body");
    
    if (data.drones.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="roster-table__empty">No active units</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    data.drones.forEach(drone => {
        const tr = document.createElement('tr');
        
        let batColor = "var(--color-success)";
        if (drone.battery_pct < 20) batColor = "var(--color-danger)";
        else if (drone.battery_pct < 40) batColor = "var(--color-warning)";

        tr.innerHTML = `
            <td style="font-family: monospace;">${drone.id}</td>
            <td><span style="color: var(--color-primary)">${drone.status || 'active'}</span></td>
            <td>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <div style="width: 40px; height: 6px; background: #333; border-radius: 3px; overflow: hidden;">
                        <div style="width: ${drone.battery_pct}%; height: 100%; background: ${batColor}"></div>
                    </div>
                    ${drone.battery_pct}%
                </div>
            </td>
            <td>${drone.current_mission}</td>
        `;
        tbody.appendChild(tr);
    });
}

/**
 * Check for pending HITL requests.
 */
async function pollHitl() {
    if (!currentSwarmId) return;
    
    // Don't poll if modal is already open
    if (document.getElementById('hitl-modal').open) return;
    
    const data = await window.ApiClient.checkPendingHitl(currentSwarmId);
    
    if (data.pending && data.pending.length > 0) {
        const decision = data.pending[0]; // Handle first pending
        window.HitlController.showModal(currentSwarmId, decision, (decId, choice) => {
            logHistory(`HITL Decision ${choice} for command ${decision.command_id}`);
        });
    }
}

const HISTORY_STORAGE_KEY = 'isc_activity_history';

/**
 * Load history entries from localStorage into the UI.
 */
function loadHistory() {
    const list = document.getElementById("history-list");
    if (!list) return;

    try {
        const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
        if (!raw) return;
        const entries = JSON.parse(raw);
        if (!Array.isArray(entries) || entries.length === 0) return;

        list.innerHTML = '';
        entries.forEach(entry => {
            const li = document.createElement('li');
            li.innerHTML = `<span style="color: var(--color-text-muted)">[${entry.time}]</span> ${entry.msg}`;
            list.appendChild(li);
        });
    } catch (e) {
        console.error("Failed to load activity history from storage", e);
    }
}

/**
 * Add a log entry to the history panel and persist to storage.
 */
function logHistory(msg) {
    const list = document.getElementById("history-list");
    if (!list) return;

    const empty = list.querySelector('.history-list__empty');
    if (empty) {
        empty.remove();
    }
    
    const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    const li = document.createElement('li');
    li.innerHTML = `<span style="color: var(--color-text-muted)">[${time}]</span> ${msg}`;
    
    list.insertBefore(li, list.firstChild);
    
    // Keep max 50 items in DOM
    while (list.children.length > 50) {
        list.removeChild(list.lastChild);
    }

    // Persist in localStorage
    try {
        const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
        const entries = raw ? JSON.parse(raw) : [];
        entries.unshift({ time, msg });
        while (entries.length > 50) {
            entries.pop();
        }
        localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
    } catch (e) {
        console.error("Failed to persist activity history to storage", e);
    }
}

window.HistoryController = {
    load: loadHistory,
    log: logHistory
};
