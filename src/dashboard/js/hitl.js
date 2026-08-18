/* HITL Modal and Decision Handling */

let activeDecisionId = null;
let activeSwarmId = null;
let onDecisionCallback = null;

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
 * Show the HITL approval modal.
 * @param {string} swarmId - ID of the swarm
 * @param {Object} decision - The decision object from API
 * @param {Function} callback - Callback on decision completion
 */
function showHitlModal(swarmId, decision, callback) {
    activeDecisionId = decision.decision_id;
    activeSwarmId = swarmId;
    onDecisionCallback = callback;

    const modal = document.getElementById('hitl-modal');
    const body = document.getElementById('hitl-modal-body');

    body.innerHTML = `
        <p><strong>Action Summary:</strong> ${decision.action_summary}</p>
        <p><strong>Command ID:</strong> <span style="font-family: monospace">${decision.command_id}</span></p>
        <p><strong>Time Remaining:</strong> <span id="hitl-timeout" style="color: var(--color-danger); font-weight: bold;">${decision.timeout_seconds}s</span></p>
    `;

    // Basic countdown timer for MVP
    let timeLeft = decision.timeout_seconds;
    const interval = setInterval(() => {
        timeLeft--;
        const el = document.getElementById('hitl-timeout');
        if (el) {
            el.textContent = `${timeLeft}s`;
        }
        if (timeLeft <= 0) {
            clearInterval(interval);
            modal.close();
            activeDecisionId = null;
        }
    }, 1000);

    // Store interval to clear on submit
    modal.dataset.intervalId = interval;

    modal.showModal();
}

/**
 * Submit the HITL decision to the API.
 * @param {string} choice - 'approved' or 'rejected'
 */
async function submitDecision(choice) {
    if (!activeDecisionId || !activeSwarmId) return;

    const modal = document.getElementById('hitl-modal');
    clearInterval(parseInt(modal.dataset.intervalId, 10));

    try {
        const res = await fetch(`http://localhost:8000/api/v1/swarms/${activeSwarmId}/hitl/${activeDecisionId}/decide`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...window.authManager.getAuthHeader()
            },
            body: JSON.stringify({
                decision: choice,
                rationale: `Commander explicitly ${choice} via dashboard.`
            })
        });

        if (!res.ok) {
            console.error("Failed to submit HITL decision", await res.text());
        } else {
            console.log(`HITL Decision: ${choice}`);
            if (onDecisionCallback) {
                onDecisionCallback(activeDecisionId, choice);
            }
        }
    } catch (e) {
        console.error("HITL submission error", e);
    } finally {
        modal.close();
        activeDecisionId = null;
    }
}

window.HitlController = {
    init: initHitl,
    showModal: showHitlModal
};
