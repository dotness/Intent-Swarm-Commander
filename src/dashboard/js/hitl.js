/* HITL Modal and Decision Handling */

let activeDecisionId = null;
let activeSwarmId = null;
let activeRequiresOverrideJustification = false;
let onDecisionCallback = null;

function _clearCountdown(modal) {
    if (modal && modal.dataset && modal.dataset.intervalId) {
        clearInterval(parseInt(modal.dataset.intervalId, 10));
        delete modal.dataset.intervalId;
    }
}

/**
 * Initialize HITL UI bindings.
 */
function initHitl() {
    const modal = document.getElementById('hitl-modal');
    const approveBtn = document.getElementById('hitl-approve');
    const rejectBtn = document.getElementById('hitl-reject');

    if (!modal || !approveBtn || !rejectBtn) return;

    approveBtn.addEventListener('click', () => submitDecision('approved'));
    rejectBtn.addEventListener('click', () => submitDecision('rejected'));
}

/**
 * Show the HITL approval modal using safe DOM construction.
 * @param {string} swarmId - ID of the swarm
 * @param {Object} decision - The decision object from API
 * @param {Function} callback - Callback on decision completion
 */
function showHitlModal(swarmId, decision, callback) {
    activeDecisionId = decision.decision_id;
    activeSwarmId = swarmId;
    activeRequiresOverrideJustification = Boolean(
        decision.is_threat_override || decision.requires_override_justification
    );
    onDecisionCallback = callback;

    const modal = document.getElementById('hitl-modal');
    const body = document.getElementById('hitl-modal-body');
    const rationaleInput = document.getElementById('hitl-rationale');
    const errorEl = document.getElementById('hitl-error');

    if (errorEl) {
        errorEl.textContent = '';
        errorEl.hidden = true;
    }
    if (rationaleInput) {
        rationaleInput.value = '';
        rationaleInput.required = activeRequiresOverrideJustification;
    }

    const nodes = [];
    const pSummary = document.createElement('p');
    const strongSum = document.createElement('strong');
    strongSum.textContent = 'Action Summary: ';
    pSummary.append(strongSum, document.createTextNode(String(decision.action_summary || 'Pending action')));
    nodes.push(pSummary);

    const pCmd = document.createElement('p');
    const strongCmd = document.createElement('strong');
    strongCmd.textContent = 'Command ID: ';
    const spanCmd = document.createElement('span');
    spanCmd.style.fontFamily = 'monospace';
    spanCmd.textContent = String(decision.command_id || '');
    pCmd.append(strongCmd, spanCmd);
    nodes.push(pCmd);

    const pTimeout = document.createElement('p');
    const strongTime = document.createElement('strong');
    strongTime.textContent = 'Time Remaining: ';
    const spanTime = document.createElement('span');
    spanTime.id = 'hitl-timeout';
    spanTime.style.color = 'var(--color-danger)';
    spanTime.style.fontWeight = 'bold';
    spanTime.textContent = `${decision.timeout_seconds}s`;
    pTimeout.append(strongTime, spanTime);
    nodes.push(pTimeout);

    if (Array.isArray(decision.threat_conflicts) && decision.threat_conflicts.length > 0) {
        const conflictBox = document.createElement('div');
        conflictBox.style.marginTop = '0.5rem';
        conflictBox.style.padding = '0.5rem';
        conflictBox.style.border = '1px solid #ef4444';
        conflictBox.style.borderRadius = '4px';

        const heading = document.createElement('strong');
        heading.textContent = 'Threat Zone Conflicts (Override Justification Mandatory):';
        const list = document.createElement('ul');
        list.style.margin = '0.35rem 0 0 1.25rem';

        for (const c of decision.threat_conflicts) {
            const li = document.createElement('li');
            const label = c.name ? `${c.name} (${c.threat_type || 'THREAT'}, ${c.severity || 'high'})` : String(c.threat_id || '');
            li.textContent = label;
            list.appendChild(li);
        }
        conflictBox.append(heading, list);
        nodes.push(conflictBox);
    }

    body.replaceChildren(...nodes);

    _clearCountdown(modal);
    let timeLeft = Number(decision.timeout_seconds || 600);
    const interval = setInterval(() => {
        timeLeft--;
        const el = document.getElementById('hitl-timeout');
        if (el) {
            el.textContent = `${timeLeft}s`;
        }
        if (timeLeft <= 0) {
            _clearCountdown(modal);
            modal.close();
            activeDecisionId = null;
        }
    }, 1000);

    modal.dataset.intervalId = String(interval);
    modal.showModal();
}

/**
 * Submit the HITL decision to the API.
 * @param {string} choice - 'approved' or 'rejected'
 */
async function submitDecision(choice) {
    if (!activeDecisionId || !activeSwarmId) return;

    const modal = document.getElementById('hitl-modal');
    const rationaleEl = document.getElementById('hitl-rationale');
    const errorEl = document.getElementById('hitl-error');
    const rationale = rationaleEl && rationaleEl.value ? rationaleEl.value.trim() : '';

    if (choice === 'approved' && activeRequiresOverrideJustification && !rationale) {
        if (errorEl) {
            errorEl.textContent = 'Override justification is required before approving a Threat Zone intersection.';
            errorEl.hidden = false;
        }
        return;
    }

    try {
        const res = await fetch(`http://localhost:8000/api/v1/swarms/${activeSwarmId}/hitl/${activeDecisionId}/decide`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...window.authManager.getAuthHeader()
            },
            body: JSON.stringify({
                decision: choice,
                rationale: rationale || `Commander explicitly ${choice} via dashboard.`,
                override_justification: rationale || null
            })
        });

        if (!res.ok) {
            const errJson = await res.json().catch(() => ({}));
            if (errorEl) {
                errorEl.textContent = errJson.detail || errJson.error || `Failed (${res.status})`;
                errorEl.hidden = false;
            }
            return;
        }

        _clearCountdown(modal);
        console.log(`HITL Decision: ${choice}`);
        const decidedId = activeDecisionId;
        activeDecisionId = null;
        modal.close();
        if (onDecisionCallback) {
            onDecisionCallback(decidedId, choice);
        }
    } catch (e) {
        console.error("HITL submission error", e);
        if (errorEl) {
            errorEl.textContent = 'Network error submitting HITL decision.';
            errorEl.hidden = false;
        }
    }
}

window.HitlController = {
    init: initHitl,
    showModal: showHitlModal
};
