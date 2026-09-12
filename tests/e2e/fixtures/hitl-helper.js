// @ts-check
const { execSync } = require('child_process');

/**
 * Helper to seed and inspect HITL records in the live PostgreSQL database container
 */
const HitlDbHelper = {
  /**
   * Seed a pending HITL decision
   * @param {Object} opts
   * @param {string} opts.id
   * @param {string} [opts.commandId]
   * @param {string} [opts.actionSummary]
   * @param {number} [opts.timeoutSeconds]
   */
  seedPendingDecision({
    id,
    commandId = 'c0000000-0000-0000-0000-000000000001',
    actionSummary = 'Authorize Kinetic Strike Vector Alpha',
    timeoutSeconds = 120,
  }) {
    const sql = `
      INSERT INTO hitl_decisions (id, swarm_command_id, commander_id, decision, action_summary, timeout_seconds, status, timeout_triggered, created_at, updated_at)
      VALUES ('${id}', '${commandId}', 'commander-alpha', 'pending', '${actionSummary}', ${timeoutSeconds}, 'pending', false, NOW(), NOW())
      ON CONFLICT (id) DO UPDATE SET
        decision = 'pending',
        status = 'pending',
        action_summary = '${actionSummary}',
        updated_at = NOW();
    `;
    execSync(`docker exec isc_postgres psql -U isc_user -d isc_db -c "${sql.replace(/\n/g, ' ')}"`);
  },

  /**
   * Query the decision record by ID
   * @param {string} id
   * @returns {{ id: string, decision: string, status: string, rationale: string }}
   */
  getDecision(id) {
    const output = execSync(
      `docker exec isc_postgres psql -U isc_user -d isc_db -t -A -F "|" -c "SELECT id, decision, status, COALESCE(rationale, '') FROM hitl_decisions WHERE id = '${id}';"`
    )
      .toString()
      .trim();

    if (!output) {
      return null;
    }

    const [recId, decision, status, rationale] = output.split('|');
    return { id: recId, decision, status, rationale };
  },

  /**
   * Clear all HITL decisions from database
   */
  clearAll() {
    execSync('docker exec isc_postgres psql -U isc_user -d isc_db -c "DELETE FROM hitl_decisions;"');
  },
};

module.exports = { HitlDbHelper };
