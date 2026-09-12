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

    // Wire up the SMEAC form
    document.getElementById("smeac-form").addEventListener("submit", handleSmeacSubmit);
    
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
            <div>Order ID: ${result.order_id}</div>
        `;
        
        logHistory(`SMEAC Order submitted (${result.order_id})`);
        
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

/**
 * Add a log entry to the history panel.
 */
function logHistory(msg) {
    const list = document.getElementById("history-list");
    const empty = list.querySelector('.history-list__empty');
    if (empty) {
        empty.remove();
    }
    
    const li = document.createElement('li');
    const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    li.innerHTML = `<span style="color: var(--color-text-muted)">[${time}]</span> ${msg}`;
    
    list.insertBefore(li, list.firstChild);
    
    // Keep max 50 items
    while (list.children.length > 50) {
        list.removeChild(list.lastChild);
    }
}
