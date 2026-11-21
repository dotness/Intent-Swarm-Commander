/* Main dashboard entry point */

let currentSwarmId = null;
let lastCopilotDraftRefs = null;
let telemetryInterval = null;
let hitlInterval = null;
let overlayInterval = null;

/**
 * Initialize the application on DOMContentLoaded.
 */
document.addEventListener("DOMContentLoaded", async () => {
    console.log("ISC Dashboard initializing...");
    
    // Init components
    window.AuthIndicator.update();
    window.MapController.initMap();
    window.HitlController.init();
    if (window.CorridorController && typeof window.CorridorController.init === "function") {
        window.CorridorController.init();
    }
    loadHistory();

    // Wire up the SMEAC form
    document.getElementById("smeac-form").addEventListener("submit", handleSmeacSubmit);

    const draftBtn = document.getElementById("btn-draft-copilot");
    if (draftBtn) {
        draftBtn.addEventListener("click", handleDraftCopilot);
    }
    const refreshAarBtn = document.getElementById("btn-refresh-aar");
    if (refreshAarBtn) {
        refreshAarBtn.addEventListener("click", refreshAarPanel);
    }
    const aarSelect = document.getElementById("aar-query-type");
    if (aarSelect) {
        aarSelect.addEventListener("change", refreshAarPanel);
    }
    const projectInput = document.getElementById("project-id-input");
    if (projectInput) {
        projectInput.addEventListener("change", () => {
            refreshTacticalOverlays();
            refreshAarPanel();
            refreshDroneVisionPanel();
        });
    }
    const visionSelect = document.getElementById("vision-drone-select");
    if (visionSelect) {
        visionSelect.addEventListener("change", refreshDroneVisionPanel);
    }
    const refreshVisionBtn = document.getElementById("btn-refresh-vision-snapshots");
    if (refreshVisionBtn) {
        refreshVisionBtn.addEventListener("click", refreshDroneVisionPanel);
    }
    refreshDroneVisionPanel();

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
    refreshTacticalOverlays();
    if (overlayInterval) clearInterval(overlayInterval);
    overlayInterval = setInterval(refreshTacticalOverlays, 5000);

    // Reload swarms when authentication status changes
    window.addEventListener('auth-changed', async (e) => {
        if (e.detail && e.detail.authenticated) {
            await loadSwarms();
            refreshTacticalOverlays();
        }
    });
});

/**
 * Fetch and populate the swarm selector.
 */
async function loadSwarms(skipAutoSelect = false) {
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
    if (!skipAutoSelect && data.swarms.length > 0) {
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
    if (window.HitlController && typeof window.HitlController.closeForOtherSwarm === "function") {
        window.HitlController.closeForOtherSwarm(swarmId);
    }

    // Clear old intervals
    if (telemetryInterval) clearInterval(telemetryInterval);
    if (hitlInterval) clearInterval(hitlInterval);

    // Initial fetch
    pollTelemetry();
    pollHitl();

    // Set polling intervals
    telemetryInterval = setInterval(pollTelemetry, 200); // 5 Hz polling rate per SC-002
    hitlInterval = setInterval(pollHitl, 5000);
    if (window.CorridorController && typeof window.CorridorController.setSwarm === "function") {
        window.CorridorController.setSwarm(swarmId);
    }
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

        // Refresh swarm selector and select newly created swarm without selecting an unrelated swarm first
        await loadSwarms(true);
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
    
    const resultDiv = document.getElementById("smeac-result");
    if (!currentSwarmId) {
        if (resultDiv) {
            resultDiv.hidden = false;
            const err = document.createElement("div");
            err.style.color = "var(--color-danger)";
            err.textContent = "Please select a swarm before submitting an order.";
            resultDiv.replaceChildren(err);
        }
        return;
    }

    const form = event.target;
    const submitBtn = document.getElementById("smeac-submit");
    
    const orderData = {
        project_id: window.ApiClient.getActiveProjectId ? window.ApiClient.getActiveProjectId() : "default-theater",
        situation: form.situation.value,
        mission: form.mission.value,
        execution: form.execution.value,
        admin_logistics: form.admin_logistics.value || null,
        command_signal: form.command_signal.value || null,
        draft_source_refs: lastCopilotDraftRefs
    };

    try {
        submitBtn.disabled = true;
        submitBtn.textContent = "Submitting...";
        if (resultDiv) {
            resultDiv.hidden = true;
            resultDiv.replaceChildren();
        }
        
        const result = await window.ApiClient.submitSmeac(currentSwarmId, orderData);
        lastCopilotDraftRefs = null;
        
        // Render target area directly from the Gemini LLM parsed command response
        const commands = result.commands || [];
        const primaryCmd = commands.find(c => c.target_area) || commands[0];
        if (primaryCmd && primaryCmd.target_area) {
            let targetArea = primaryCmd.target_area;
            if (typeof targetArea === 'string' && (targetArea.startsWith('{') || targetArea.startsWith('['))) {
                try { targetArea = JSON.parse(targetArea); } catch (e) {}
            }

            if (window.MapController && typeof window.MapController.drawTargetArea === 'function') {
                window.MapController.drawTargetArea(targetArea);
            }
        }
        await pollTelemetry();

        const savedSwarmId = currentSwarmId;
        form.reset();
        // Restore active swarm selection if form.reset cleared the select element
        if (savedSwarmId) {
            const select = document.getElementById("swarm-select");
            if (select) select.value = savedSwarmId;
            currentSwarmId = savedSwarmId;
        }

        if (resultDiv) {
            resultDiv.hidden = false;
            const titleEl = document.createElement("div");
            titleEl.style.color = result.status === "pending_hitl" ? "var(--color-warning)" : "var(--color-success)";
            titleEl.style.fontWeight = "bold";
            titleEl.style.marginBottom = "0.5rem";
            titleEl.textContent = result.status === "pending_hitl"
                ? "⚠️ Threat Conflict Detected — HITL Override Required"
                : "✅ Order Submitted Successfully";

            const idLine = document.createElement("div");
            const idSpan = document.createElement("span");
            idSpan.id = "smeac-submitted-id";
            idSpan.textContent = String(result.order_id || "");
            idLine.append("Order ID: ", idSpan);

            const statusLine = document.createElement("div");
            statusLine.style.fontSize = "0.85rem";
            statusLine.style.marginTop = "0.25rem";
            statusLine.textContent = `Status: ${result.status || "executed"}`;

            resultDiv.replaceChildren(titleEl, idLine, statusLine);
        }

        if (result.status === "pending_hitl") {
            pollHitl();
        }
        if (window.CorridorController && typeof window.CorridorController.refresh === "function") {
            window.CorridorController.refresh();
        }
        
        logHistory(`SMEAC Order ${result.order_id} (${result.status})`);
        
        setTimeout(() => {
            if (resultDiv) resultDiv.hidden = true;
        }, 5000);
        
    } catch (e) {
        if (resultDiv) {
            resultDiv.hidden = false;
            const errTitle = document.createElement("div");
            errTitle.style.color = "var(--color-danger)";
            errTitle.style.fontWeight = "bold";
            errTitle.textContent = "❌ Submission Failed";
            const errMsg = document.createElement("div");
            errMsg.textContent = e.message || "Unknown error";
            resultDiv.replaceChildren(errTitle, errMsg);
        }
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
        const emptyRow = document.createElement('tr');
        const emptyCell = document.createElement('td');
        emptyCell.colSpan = 4;
        emptyCell.className = 'roster-table__empty';
        emptyCell.textContent = 'No active units';
        emptyRow.appendChild(emptyCell);
        tbody.replaceChildren(emptyRow);
        return;
    }
    
    const rows = [];
    data.drones.forEach(drone => {
        const tr = document.createElement('tr');
        
        let batColor = "var(--color-success)";
        if (drone.battery_pct < 20) batColor = "var(--color-danger)";
        else if (drone.battery_pct < 40) batColor = "var(--color-warning)";

        const tdId = document.createElement('td');
        tdId.style.fontFamily = 'monospace';
        tdId.textContent = String(drone.id || '');

        const tdStatus = document.createElement('td');
        const statusSpan = document.createElement('span');
        statusSpan.style.color = 'var(--color-primary)';
        const avoidance = drone.last_avoidance_event;
        const statusText = avoidance && avoidance.command_source === 'edge_autonomous'
            ? `${String(drone.status || 'active')} (${avoidance.action}: ${avoidance.bypass_direction || 'hold'})`
            : String(drone.status || 'active');
        statusSpan.textContent = statusText;
        tdStatus.appendChild(statusSpan);

        const tdBat = document.createElement('td');
        const batWrap = document.createElement('div');
        batWrap.style.display = 'flex';
        batWrap.style.alignItems = 'center';
        batWrap.style.gap = '0.5rem';
        const barBg = document.createElement('div');
        barBg.style.width = '40px';
        barBg.style.height = '6px';
        barBg.style.background = '#333';
        barBg.style.borderRadius = '3px';
        barBg.style.overflow = 'hidden';
        const barFill = document.createElement('div');
        const pct = Math.max(0, Math.min(100, Number(drone.battery_pct || 0)));
        barFill.style.width = `${pct}%`;
        barFill.style.height = '100%';
        barFill.style.background = batColor;
        barBg.appendChild(barFill);
        batWrap.append(barBg, document.createTextNode(`${drone.battery_pct ?? 'n/a'}%`));
        tdBat.appendChild(batWrap);

        const tdMission = document.createElement('td');
        tdMission.textContent = String(drone.current_mission || '');

        tr.append(tdId, tdStatus, tdBat, tdMission);
        rows.push(tr);
    });
    tbody.replaceChildren(...rows);
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

        const items = [];
        entries.forEach(entry => {
            const li = document.createElement('li');
            const timeSpan = document.createElement('span');
            timeSpan.style.color = 'var(--color-text-muted)';
            timeSpan.textContent = `[${entry.time}] `;
            li.append(timeSpan, document.createTextNode(String(entry.msg || '')));
            items.push(li);
        });
        list.replaceChildren(...items);
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
    const timeSpan = document.createElement('span');
    timeSpan.style.color = 'var(--color-text-muted)';
    timeSpan.textContent = `[${time}] `;
    li.append(timeSpan, document.createTextNode(String(msg || '')));
    
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

/**
 * Invoke non-executing SMEAC Copilot to populate draft form fields without submitting.
 */
async function handleDraftCopilot() {
    const intentInput = document.getElementById("copilot-intent");
    const missionInput = document.getElementById("smeac-mission");
    const citationsBox = document.getElementById("copilot-citations");
    const draftBtn = document.getElementById("btn-draft-copilot");

    const intent = (intentInput && intentInput.value ? intentInput.value.trim() : "")
        || (missionInput && missionInput.value ? missionInput.value.trim() : "");
    if (!intent || intent.length < 5) {
        if (citationsBox) {
            citationsBox.hidden = false;
            citationsBox.textContent = "Enter at least 5 characters of Commander Intent before drafting.";
        }
        return;
    }

    try {
        if (draftBtn) {
            draftBtn.disabled = true;
            draftBtn.textContent = "Drafting...";
        }
        const { draft } = await window.ApiClient.draftSmeacWithCopilot(intent);
        if (!draft) return;

        lastCopilotDraftRefs = Array.isArray(draft.source_citations)
            ? draft.source_citations.map(c => `${c.source_type}:${c.source_id}`)
            : null;

        const sitEl = document.getElementById("smeac-situation");
        const misEl = document.getElementById("smeac-mission");
        const exeEl = document.getElementById("smeac-execution");
        const admEl = document.getElementById("smeac-admin");
        const sigEl = document.getElementById("smeac-signal");
        if (sitEl) sitEl.value = draft.situation || "";
        if (misEl) misEl.value = draft.mission || "";
        if (exeEl) exeEl.value = draft.execution || "";
        if (admEl) admEl.value = draft.admin_logistics || "";
        if (sigEl) sigEl.value = draft.command_signal || "";

        if (citationsBox) {
            citationsBox.hidden = false;
            const title = document.createElement("strong");
            title.textContent = "DRAFT ONLY (Not Submitted) — Grounded Citations:";
            const ul = document.createElement("ul");
            ul.style.margin = "0.25rem 0 0 1.25rem";
            for (const cite of draft.source_citations || []) {
                const li = document.createElement("li");
                li.textContent = `[${cite.source_type}] ${cite.label}`;
                ul.appendChild(li);
            }
            citationsBox.replaceChildren(title, ul);
        }
        logHistory("Copilot generated read-only SMEAC draft for review");
    } catch (e) {
        if (citationsBox) {
            citationsBox.hidden = false;
            citationsBox.textContent = `Copilot error: ${e.message || "unknown error"}`;
        }
    } finally {
        if (draftBtn) {
            draftBtn.disabled = false;
            draftBtn.textContent = "Draft with AI";
        }
    }
}

/**
 * Refresh Analytical After-Action Review (AAR) panel from MinIO Parquet backend.
 */
async function refreshAarPanel() {
    const typeSelect = document.getElementById("aar-query-type");
    const container = document.getElementById("aar-results");
    if (!container) return;

    const queryType = typeSelect ? typeSelect.value : "summary";
    try {
        const res = await window.ApiClient.fetchAar(queryType, currentSwarmId);
        const header = document.createElement("div");
        header.style.marginBottom = "0.35rem";
        header.textContent = `Engine: ${res.engine || "olap"} | Latency: ${res.execution_ms}ms | Rows: ${res.row_count}`;

        const list = document.createElement("ul");
        list.style.margin = "0";
        list.style.paddingLeft = "1.1rem";
        const previewRows = (res.rows || []).slice(0, 15);
        for (const row of previewRows) {
            const li = document.createElement("li");
            li.textContent = Object.entries(row)
                .map(([k, v]) => `${k}=${v}`)
                .join(" | ");
            list.appendChild(li);
        }
        container.replaceChildren(header, list);
    } catch (e) {
        const err = document.createElement("div");
        err.style.color = "var(--color-danger)";
        err.textContent = e.message || "AAR unavailable";
        container.replaceChildren(err);
    }
}

/**
 * Refresh Memgraph ThreatZones and correlated TargetEntities onto tactical map.
 */
async function refreshTacticalOverlays() {
    if (!window.ApiClient || !window.MapController) return;
    if (window.authManager && window.authManager.isAuthenticated && !window.authManager.isAuthenticated()) {
        return;
    }

    try {
        if (window.ApiClient.fetchThreats && window.MapController.renderThreatZones) {
            const threatRes = await window.ApiClient.fetchThreats();
            window.MapController.renderThreatZones(
                threatRes.threats,
                async (threatId, reason) => {
                    try {
                        await window.ApiClient.deactivateThreat(threatId, reason);
                        logHistory(`Deactivated threat ${threatId}`);
                        refreshTacticalOverlays();
                    } catch (err) {
                        console.error("Failed to deactivate threat", err);
                    }
                }
            );
        }
        if (window.ApiClient.fetchTargets && window.MapController.renderTargets) {
            const targets = await window.ApiClient.fetchTargets();
            window.MapController.renderTargets(targets, (targetId) => {
                window.MapController.openTargetLineageModal(targetId, refreshTacticalOverlays);
            });
        }
    } catch (e) {
        console.debug("Overlay refresh skipped:", e);
    }
}

let _visionSnapshotBlobUrls = [];

/**
 * Update the Drone Vision & Snapshots panel for the selected drone_id.
 */
async function refreshDroneVisionPanel() {
    const selectEl = document.getElementById("vision-drone-select");
    const streamImg = document.getElementById("vision-stream-img");
    const galleryEl = document.getElementById("vision-snapshot-gallery");
    if (!selectEl || !streamImg || !galleryEl) return;

    const droneId = selectEl.value || "drone-1";
    const base = window.VIRTUAL_CAM_URL || "http://localhost:8091";
    const desiredSrc = `${base}/stream/${encodeURIComponent(droneId)}`;
    if (streamImg.getAttribute("src") !== desiredSrc) {
        streamImg.setAttribute("src", desiredSrc);
    }

    if (!window.ApiClient || typeof window.ApiClient.fetchTargets !== "function") return;
    if (window.authManager && window.authManager.isAuthenticated && !window.authManager.isAuthenticated()) return;

    for (const url of _visionSnapshotBlobUrls) {
        URL.revokeObjectURL(url);
    }
    _visionSnapshotBlobUrls = [];

    try {
        const targetsData = await window.ApiClient.fetchTargets();
        const targets = Array.isArray(targetsData)
            ? targetsData
            : (targetsData && (targetsData.items || targetsData.targets)) || [];
        const matched = [];
        for (const tgt of targets.slice(0, 10)) {
            const tid = tgt.target_id || tgt.id;
            if (!tid) continue;
            const lineage = await window.ApiClient.fetchTargetLineage(tid);
            const obsList = (lineage && (lineage.observations || lineage.detections)) || [];
            for (const obs of obsList) {
                if (obs.drone_id === droneId && obs.snapshot_proxy_url) {
                    matched.push({ obs, targetClass: tgt.canonical_class || obs.target_class || "target" });
                }
            }
        }

        galleryEl.replaceChildren();
        if (matched.length === 0) {
            const empty = document.createElement("span");
            empty.className = "roster-table__empty";
            empty.textContent = `No detection snapshots for ${droneId} yet`;
            galleryEl.appendChild(empty);
            return;
        }

        for (const item of matched.slice(-6).reverse()) {
            const card = document.createElement("div");
            card.style.cssText = "border:1px solid #374151;border-radius:4px;padding:4px;background:#111827;width:120px;";
            const caption = document.createElement("div");
            caption.style.cssText = "font-size:0.75rem;margin-bottom:3px;color:#d1d5db;";
            caption.textContent = `${item.obs.drone_id}: ${item.targetClass}`;
            const thumb = document.createElement("img");
            thumb.alt = `${item.obs.drone_id} detection snapshot`;
            thumb.style.cssText = "width:100%;height:72px;object-fit:cover;border-radius:3px;";
            card.append(caption, thumb);
            galleryEl.appendChild(card);

            window.ApiClient.fetchSnapshotBlobUrl(item.obs.snapshot_proxy_url)
                .then((blobUrl) => {
                    if (blobUrl) {
                        _visionSnapshotBlobUrls.push(blobUrl);
                        thumb.src = blobUrl;
                    }
                })
                .catch(() => {});
        }
    } catch (_err) {
        // Ignore transient unauthenticated/network errors
    }
}
