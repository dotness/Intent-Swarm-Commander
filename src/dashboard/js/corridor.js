/* Adaptive Corridor Survey & 3D Intelligence Controller (strictly XSS-safe DOM/SVG construction) */

(function () {
    const SVG_NS = "http://www.w3.org/2000/svg";

    let _swarmId = null;
    let _selectedSurveyId = null;
    let _latestSeenSurveyId = null;
    let _surveys = [];
    let _activeReport = null;
    let _pollTimer = null;
    let _pendingOverrideType = null;
    const _snapshotBlobMap = new Map(); // snapshot_id -> blobUrl
    const _inFlightSnapshotIds = new Set();

    function svgEl(tag, attrs = {}, text = null) {
        const el = document.createElementNS(SVG_NS, tag);
        for (const [k, v] of Object.entries(attrs)) {
            if (v !== null && v !== undefined) {
                el.setAttribute(k, String(v));
            }
        }
        if (text !== null) {
            el.textContent = String(text);
        }
        return el;
    }

    function clearSnapshotBlobUrls(keepIds = new Set()) {
        for (const [snapId, url] of _snapshotBlobMap.entries()) {
            if (!keepIds.has(snapId)) {
                URL.revokeObjectURL(url);
                _snapshotBlobMap.delete(snapId);
            }
        }
    }

    function init() {
        const selectEl = document.getElementById("corridor-survey-select");
        const refreshBtn = document.getElementById("btn-corridor-refresh");
        const recallBtn = document.getElementById("btn-corridor-recall");
        const abortBtn = document.getElementById("btn-corridor-emergency-abort");
        const modal = document.getElementById("corridor-abort-modal");
        const modalCancel = document.getElementById("corridor-modal-cancel");
        const modalConfirm = document.getElementById("corridor-modal-confirm");

        if (selectEl) {
            selectEl.addEventListener("change", async (e) => {
                _selectedSurveyId = e.target.value || null;
                await refreshSelectedReport();
            });
        }
        if (refreshBtn) {
            refreshBtn.addEventListener("click", () => refresh());
        }
        if (recallBtn) {
            recallBtn.addEventListener("click", () => openOverrideModal("recall"));
        }
        if (abortBtn) {
            abortBtn.addEventListener("click", () => openOverrideModal("emergency_abort"));
        }
        if (modalCancel && modal) {
            modalCancel.addEventListener("click", () => {
                _pendingOverrideType = null;
                modal.close();
            });
        }
        if (modalConfirm) {
            modalConfirm.addEventListener("click", executePendingOverride);
        }
    }

    function setSwarm(swarmId) {
        _swarmId = swarmId || null;
        _selectedSurveyId = null;
        _activeReport = null;
        clearSnapshotBlobUrls();
        if (_pollTimer) {
            clearInterval(_pollTimer);
            _pollTimer = null;
        }
        if (_swarmId) {
            refresh();
            _pollTimer = setInterval(refresh, 1500);
        } else {
            renderEmpty();
        }
    }

    function openOverrideModal(overrideType) {
        if (!_swarmId || !_selectedSurveyId) return;
        const modal = document.getElementById("corridor-abort-modal");
        const titleEl = document.getElementById("corridor-modal-title");
        const descEl = document.getElementById("corridor-modal-description");
        const rationaleEl = document.getElementById("corridor-override-rationale");
        const confirmBtn = document.getElementById("corridor-modal-confirm");
        if (!modal || !titleEl || !descEl || !confirmBtn) return;

        _pendingOverrideType = overrideType;
        if (rationaleEl) rationaleEl.value = "";
        if (overrideType === "recall") {
            titleEl.textContent = "Confirm Scout Recall (Reverse-Path Return)";
            descEl.textContent =
                "End outbound corridor discovery now and guide the lead scout safely back to origin along verified 3D breadcrumbs, producing a partial Corridor Intelligence Report.";
            confirmBtn.textContent = "Recall Scout";
            confirmBtn.className = "btn btn--warning";
        } else {
            titleEl.textContent = "Confirm Emergency Abort (Hold in Place)";
            descEl.textContent =
                "Command immediate in-place MAVSDK hold via emergency abort while preserving all intelligence collected up to this point.";
            confirmBtn.textContent = "Emergency Abort";
            confirmBtn.className = "btn btn--danger";
        }
        modal.showModal();
    }

    async function executePendingOverride() {
        const modal = document.getElementById("corridor-abort-modal");
        const rationaleEl = document.getElementById("corridor-override-rationale");
        const rationale = rationaleEl && rationaleEl.value ? rationaleEl.value.trim() : null;
        const overrideType = _pendingOverrideType;
        _pendingOverrideType = null;
        if (modal) modal.close();
        if (!overrideType || !_swarmId || !_selectedSurveyId) return;

        try {
            if (overrideType === "recall") {
                await window.ApiClient.recallCorridorSurvey(_swarmId, _selectedSurveyId, rationale);
                if (window.HistoryController) {
                    window.HistoryController.log(`Corridor Recall sent for survey ${_selectedSurveyId}`);
                }
            } else {
                await window.ApiClient.emergencyAbortCorridorSurvey(_swarmId, _selectedSurveyId, rationale);
                if (window.HistoryController) {
                    window.HistoryController.log(`Corridor Emergency Abort invoked for survey ${_selectedSurveyId}`);
                }
            }
            await refresh();
        } catch (err) {
            renderErrorBanner(err.message || "Corridor override failed");
        }
    }

    function renderErrorBanner(msg) {
        const banner = document.getElementById("corridor-status-banner");
        if (!banner) return;
        const span = document.createElement("span");
        span.style.color = "var(--color-danger)";
        span.textContent = String(msg);
        banner.replaceChildren(span);
    }

    async function refresh() {
        if (!_swarmId || !window.ApiClient || typeof window.ApiClient.fetchCorridorSurveys !== "function") {
            return;
        }
        if (window.authManager && window.authManager.isAuthenticated && !window.authManager.isAuthenticated()) {
            return;
        }
        const { surveys } = await window.ApiClient.fetchCorridorSurveys(_swarmId);
        _surveys = Array.isArray(surveys) ? surveys : [];
        updateSelector(_surveys);

        if (_surveys.length === 0) {
            renderEmpty();
            return;
        }
        const newestSurveyId = _surveys[0].survey_id;
        if (
            !_selectedSurveyId
            || !_surveys.some((s) => s.survey_id === _selectedSurveyId)
            || newestSurveyId !== _latestSeenSurveyId
        ) {
            _selectedSurveyId = newestSurveyId;
            const selectEl = document.getElementById("corridor-survey-select");
            if (selectEl) selectEl.value = _selectedSurveyId;
        }
        _latestSeenSurveyId = newestSurveyId;
        await refreshSelectedReport();
    }

    function updateSelector(surveys) {
        const selectEl = document.getElementById("corridor-survey-select");
        if (!selectEl) return;
        if (surveys.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No corridor surveys yet";
            selectEl.replaceChildren(opt);
            return;
        }
        const opts = surveys.map((s) => {
            const opt = document.createElement("option");
            opt.value = s.survey_id;
            const dist = `${Number(s.surveyed_distance_m || 0).toFixed(1)}/${Number(s.requested_distance_m || 0).toFixed(0)}m`;
            opt.textContent = `${s.corridor_descriptor} [${s.phase}] (${dist})`;
            return opt;
        });
        selectEl.replaceChildren(...opts);
        if (_selectedSurveyId) {
            selectEl.value = _selectedSurveyId;
        }
    }

    async function refreshSelectedReport() {
        if (!_swarmId || !_selectedSurveyId) return;
        try {
            const report = await window.ApiClient.fetchCorridorSurveyReport(_swarmId, _selectedSurveyId);
            _activeReport = report;
            renderReport(report);
        } catch (err) {
            console.debug("Corridor report refresh skipped:", err);
        }
    }

    function renderEmpty() {
        const banner = document.getElementById("corridor-status-banner");
        const recallBtn = document.getElementById("btn-corridor-recall");
        const abortBtn = document.getElementById("btn-corridor-emergency-abort");
        const planSvg = document.getElementById("corridor-svg-plan");
        const elevSvg = document.getElementById("corridor-svg-elevation");
        const findingsList = document.getElementById("corridor-findings-list");
        const filmstrip = document.getElementById("corridor-snapshot-filmstrip");

        if (recallBtn) recallBtn.disabled = true;
        if (abortBtn) abortBtn.disabled = true;
        clearSnapshotBlobUrls();

        if (banner) {
            const msg = document.createElement("span");
            msg.className = "roster-table__empty";
            msg.textContent = "Submit a coordinate-free corridor survey SMEAC order to begin discovery.";
            banner.replaceChildren(msg);
        }
        if (planSvg) {
            planSvg.replaceChildren(
                svgEl("text", { x: 180, y: 112, "text-anchor": "middle", fill: "#64748b", "font-size": 12 }, "No active corridor path")
            );
        }
        if (elevSvg) {
            elevSvg.replaceChildren(
                svgEl("text", { x: 180, y: 112, "text-anchor": "middle", fill: "#64748b", "font-size": 12 }, "No elevation profile yet")
            );
        }
        if (findingsList) {
            const li = document.createElement("li");
            li.className = "roster-table__empty";
            li.textContent = "No intelligence findings recorded yet";
            findingsList.replaceChildren(li);
        }
        if (filmstrip) {
            const empty = document.createElement("span");
            empty.className = "roster-table__empty";
            empty.textContent = "No corridor snapshots captured yet";
            filmstrip.replaceChildren(empty);
        }
    }

    function renderReport(report) {
        if (!report) return;
        const terminalPhases = new Set(["completed", "completed_holding", "impassable_start", "emergency_hold"]);
        const isTerminal = terminalPhases.has(report.phase);

        const recallBtn = document.getElementById("btn-corridor-recall");
        const abortBtn = document.getElementById("btn-corridor-emergency-abort");
        if (recallBtn) recallBtn.disabled = isTerminal || report.phase === "returning";
        if (abortBtn) abortBtn.disabled = isTerminal;

        renderBanner(report);
        renderTopDownPlan(report);
        renderElevationProfile(report);
        renderFindingsAndProvenance(report);
        renderSnapshotFilmstrip(report);
    }

    function renderBanner(report) {
        const banner = document.getElementById("corridor-status-banner");
        if (!banner) return;

        const phaseBadge = document.createElement("span");
        phaseBadge.className = report.status === "aborted" || report.phase === "impassable_start"
            ? "corridor-badge corridor-badge--warn"
            : "corridor-badge corridor-badge--ok";
        phaseBadge.textContent = `Phase: ${report.phase} (${report.status})`;

        const distSpan = document.createElement("span");
        const defaultedLabel = report.distance_defaulted ? " [20m default]" : "";
        distSpan.textContent = `Distance: ${Number(report.surveyed_distance_m || 0).toFixed(1)}m / ${Number(report.requested_distance_m || 0).toFixed(1)}m${defaultedLabel}`;

        const scoutBadge = document.createElement("span");
        scoutBadge.className = "corridor-badge";
        const stagingTxt = Array.isArray(report.staging_hold_drone_ids) && report.staging_hold_drone_ids.length > 0
            ? ` | Staging Hold: ${report.staging_hold_drone_ids.join(", ")}`
            : "";
        scoutBadge.textContent = `Lead Scout: ${report.lead_scout_drone_id}${stagingTxt}`;

        const countsSpan = document.createElement("span");
        countsSpan.textContent = `Snapshots: ${(report.snapshots || []).length} | Decisions: ${(report.decisions || []).length} | Findings: ${(report.findings || []).length}`;

        const parts = [phaseBadge, distSpan, scoutBadge, countsSpan];
        if (report.completion_reason) {
            const reasonBadge = document.createElement("span");
            reasonBadge.className = "corridor-badge";
            reasonBadge.textContent = `Outcome: ${report.completion_reason}`;
            parts.push(reasonBadge);
        }
        banner.replaceChildren(...parts);
    }

    function renderTopDownPlan(report) {
        const svg = document.getElementById("corridor-svg-plan");
        if (!svg) return;

        const W = 360;
        const H = 220;
        const PAD = 24;
        const pathPts = Array.isArray(report.discovered_path) ? report.discovered_path : [];
        const snapshots = Array.isArray(report.snapshots) ? report.snapshots : [];
        const pts = pathPts.length > 0
            ? pathPts
            : snapshots.map((s) => ({ rel_x_m: s.rel_x_m, rel_y_m: s.rel_y_m, rel_z_m: s.rel_z_m }));

        if (pts.length === 0) {
            pts.push({ rel_x_m: 0, rel_y_m: 0, rel_z_m: report.min_altitude_m || 2.0 });
        }

        const xs = pts.map((p) => Number(p.rel_x_m || 0));
        const ys = pts.map((p) => Number(p.rel_y_m || 0));
        xs.push(0);
        ys.push(0);

        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        const span = Math.max(8, maxX - minX, maxY - minY);
        const midX = (minX + maxX) / 2;
        const midY = (minY + maxY) / 2;
        const scale = (Math.min(W, H) - PAD * 2) / span;

        const mapX = (x) => (W / 2) + (Number(x || 0) - midX) * scale;
        const mapY = (y) => (H / 2) - (Number(y || 0) - midY) * scale;

        const children = [];
        // Grid lines
        children.push(svgEl("line", { x1: PAD, y1: mapY(0), x2: W - PAD, y2: mapY(0), stroke: "#1e293b", "stroke-width": 1 }));
        children.push(svgEl("line", { x1: mapX(0), y1: PAD, x2: mapX(0), y2: H - PAD, stroke: "#1e293b", "stroke-width": 1 }));
        // Origin 360 look-around halo
        children.push(svgEl("circle", { cx: mapX(0), cy: mapY(0), r: 10, fill: "none", stroke: "#38bdf8", "stroke-width": 1.5, "stroke-dasharray": "3 2" }));
        children.push(svgEl("circle", { cx: mapX(0), cy: mapY(0), r: 3.5, fill: "#22c55e" }));
        children.push(svgEl("text", { x: mapX(0) + 6, y: mapY(0) - 6, fill: "#94a3b8", "font-size": 9 }, "Origin (0,0)"));

        // Centerline polyline
        if (pts.length > 1) {
            const polyPts = pts.map((p) => `${mapX(p.rel_x_m).toFixed(1)},${mapY(p.rel_y_m).toFixed(1)}`).join(" ");
            children.push(svgEl("polyline", { points: polyPts, fill: "none", stroke: "#3b82f6", "stroke-width": 3, "stroke-linecap": "round", "stroke-linejoin": "round" }));
        }

        // Unexplored side branches
        for (const br of report.unexplored_branches || []) {
            const rp = br.relative_pose || br;
            const bx = mapX(rp.rel_x_m || 0);
            const by = mapY(rp.rel_y_m || 0);
            const rad = ((Number(br.heading_deg || 0)) * Math.PI) / 180;
            const ex = bx + Math.sin(rad) * 22;
            const ey = by - Math.cos(rad) * 22;
            children.push(svgEl("line", { x1: bx, y1: by, x2: ex, y2: ey, stroke: "#f59e0b", "stroke-width": 2, "stroke-dasharray": "3 2" }));
        }

        // Findings & hazards markers
        for (const f of report.findings || []) {
            if (f.finding_type === "side_branch") continue;
            const fx = mapX(f.rel_x_m);
            const fy = mapY(f.rel_y_m);
            const fill = f.matches_mission_interest ? "#22c55e" : "#ef4444";
            children.push(svgEl("circle", { cx: fx, cy: fy, r: 4, fill, stroke: "#0f172a", "stroke-width": 1 }));
        }

        // Current/last scout pose marker
        const lastSnap = snapshots.length > 0 ? snapshots[snapshots.length - 1] : pts[pts.length - 1];
        children.push(svgEl("circle", { cx: mapX(lastSnap.rel_x_m), cy: mapY(lastSnap.rel_y_m), r: 5, fill: "#f8fafc", stroke: "#3b82f6", "stroke-width": 2 }));

        svg.replaceChildren(...children);
    }

    function renderElevationProfile(report) {
        const svg = document.getElementById("corridor-svg-elevation");
        if (!svg) return;

        const W = 360;
        const H = 220;
        const PAD_L = 34;
        const PAD_R = 16;
        const PAD_T = 18;
        const PAD_B = 26;

        const minBound = Number(report.min_altitude_m ?? 1.2);
        const maxBound = Number(report.max_altitude_m ?? 8.0);
        const snapshots = Array.isArray(report.snapshots) ? report.snapshots : [];
        const pathPts = Array.isArray(report.discovered_path) ? report.discovered_path : [];
        const series = pathPts.length > 0 ? pathPts : snapshots;

        const maxD = Math.max(
            Number(report.requested_distance_m || 20.0),
            ...series.map((p) => Number(p.cumulative_distance_m || 0)),
            1.0
        );
        const yMax = Math.max(maxBound + 1.0, ...series.map((p) => Number(p.rel_z_m || 0) + 0.5), 4.0);
        const mapD = (d) => PAD_L + (Number(d || 0) / maxD) * (W - PAD_L - PAD_R);
        const mapZ = (z) => (H - PAD_B) - (Number(z || 0) / yMax) * (H - PAD_T - PAD_B);

        const children = [];
        // Ground reference
        children.push(svgEl("line", { x1: PAD_L, y1: mapZ(0), x2: W - PAD_R, y2: mapZ(0), stroke: "#334155", "stroke-width": 1 }));
        // Configured safety floor & ceiling (`FR-021`)
        children.push(svgEl("line", { x1: PAD_L, y1: mapZ(minBound), x2: W - PAD_R, y2: mapZ(minBound), stroke: "#f59e0b", "stroke-width": 1.2, "stroke-dasharray": "4 3" }));
        children.push(svgEl("text", { x: PAD_L + 4, y: mapZ(minBound) - 3, fill: "#f59e0b", "font-size": 9 }, `Min Alt ${minBound.toFixed(1)}m`));
        children.push(svgEl("line", { x1: PAD_L, y1: mapZ(maxBound), x2: W - PAD_R, y2: mapZ(maxBound), stroke: "#ef4444", "stroke-width": 1.2, "stroke-dasharray": "4 3" }));
        children.push(svgEl("text", { x: PAD_L + 4, y: mapZ(maxBound) + 10, fill: "#ef4444", "font-size": 9 }, `Max Alt ${maxBound.toFixed(1)}m`));

        if (series.length > 0) {
            const polyPts = series
                .map((p) => `${mapD(p.cumulative_distance_m).toFixed(1)},${mapZ(p.rel_z_m).toFixed(1)}`)
                .join(" ");
            children.push(svgEl("polyline", { points: polyPts, fill: "none", stroke: "#22c55e", "stroke-width": 2.5 }));
            for (const p of series) {
                children.push(svgEl("circle", { cx: mapD(p.cumulative_distance_m), cy: mapZ(p.rel_z_m), r: 3, fill: "#22c55e" }));
            }
        }
        children.push(svgEl("text", { x: W / 2, y: H - 6, "text-anchor": "middle", fill: "#94a3b8", "font-size": 9 }, `Cumulative 3D Path Distance (0 - ${maxD.toFixed(1)}m)`));

        svg.replaceChildren(...children);
    }

    function renderFindingsAndProvenance(report) {
        const listEl = document.getElementById("corridor-findings-list");
        if (!listEl) return;

        const items = [];
        if (Array.isArray(report.structural_features) && report.structural_features.length > 0) {
            const li = document.createElement("li");
            const strong = document.createElement("strong");
            strong.textContent = "Structural Cues: ";
            li.append(strong, document.createTextNode(report.structural_features.join(", ")));
            items.push(li);
        }

        for (const f of report.findings || []) {
            const li = document.createElement("li");
            const badge = document.createElement("strong");
            badge.style.color = f.matches_mission_interest ? "var(--color-success)" : "var(--color-warning)";
            badge.textContent = `[${f.finding_type}] ${f.label} `;
            const meta = document.createTextNode(
                `(${Math.round(Number(f.confidence || 0) * 100)}% @ ${Number(f.cumulative_distance_m || 0).toFixed(1)}m, hdg ${Math.round(Number(f.heading_deg || 0))}°)`
            );
            li.append(badge, meta);
            items.push(li);
        }

        for (const dec of (report.decisions || []).slice(-6).reverse()) {
            const li = document.createElement("li");
            const strong = document.createElement("strong");
            strong.textContent = `#${dec.sequence_num} [${dec.decision_authority}] ${dec.action}: `;
            const snapRefCount = Array.isArray(dec.trigger_snapshot_ids) ? dec.trigger_snapshot_ids.length : 0;
            li.append(
                strong,
                document.createTextNode(`${dec.rationale} (snapshots: ${snapRefCount})`)
            );
            items.push(li);
        }

        if (items.length === 0) {
            const empty = document.createElement("li");
            empty.className = "roster-table__empty";
            empty.textContent = "No intelligence findings or edge decisions recorded yet";
            listEl.replaceChildren(empty);
            return;
        }
        listEl.replaceChildren(...items);
    }

    function renderSnapshotFilmstrip(report) {
        const container = document.getElementById("corridor-snapshot-filmstrip");
        if (!container) return;

        const snaps = Array.isArray(report.snapshots) ? report.snapshots : [];
        if (snaps.length === 0) {
            clearSnapshotBlobUrls();
            const empty = document.createElement("span");
            empty.className = "roster-table__empty";
            empty.textContent = "No corridor snapshots captured yet";
            container.replaceChildren(empty);
            return;
        }

        const keepIds = new Set(snaps.map((s) => s.snapshot_id));
        clearSnapshotBlobUrls(keepIds);

        const cards = snaps.map((snap) => {
            const card = document.createElement("div");
            card.className = "corridor-snap-card";

            const img = document.createElement("img");
            img.alt = `Snapshot #${snap.sequence_num} (${snap.phase})`;
            if (_snapshotBlobMap.has(snap.snapshot_id)) {
                img.src = _snapshotBlobMap.get(snap.snapshot_id);
            } else if (
                snap.image_proxy_url
                && !_inFlightSnapshotIds.has(snap.snapshot_id)
                && window.ApiClient
                && typeof window.ApiClient.fetchSnapshotBlobUrl === "function"
            ) {
                _inFlightSnapshotIds.add(snap.snapshot_id);
                window.ApiClient.fetchSnapshotBlobUrl(snap.image_proxy_url)
                    .then((blobUrl) => {
                        if (blobUrl) {
                            const prevUrl = _snapshotBlobMap.get(snap.snapshot_id);
                            if (prevUrl && prevUrl !== blobUrl) {
                                URL.revokeObjectURL(prevUrl);
                            }
                            _snapshotBlobMap.set(snap.snapshot_id, blobUrl);
                            img.src = blobUrl;
                        }
                    })
                    .catch(() => {})
                    .finally(() => {
                        _inFlightSnapshotIds.delete(snap.snapshot_id);
                    });
            }

            const title = document.createElement("div");
            title.textContent = `#${snap.sequence_num} ${snap.phase}`;

            const pose = document.createElement("div");
            pose.style.color = "var(--color-text-muted)";
            pose.textContent = `${Number(snap.cumulative_distance_m || 0).toFixed(1)}m | z=${Number(snap.rel_z_m || 0).toFixed(1)}m | ${Math.round(Number(snap.heading_deg || 0))}°`;

            card.append(img, title, pose);
            return card;
        });

        container.replaceChildren(...cards);
    }

    window.CorridorController = {
        init,
        setSwarm,
        refresh,
        renderReport,
    };
})();
