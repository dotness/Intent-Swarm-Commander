/**
 * Test credentials for Intent Swarm Commander authentication
 */
const commanderPassphrase = process.env.COMMANDER_PASSPHRASE;
if (!commanderPassphrase) {
  throw new Error('COMMANDER_PASSPHRASE environment variable is required for E2E tests.');
}

module.exports = {
  VALID_COMMANDER: {
    commanderId: 'commander-alpha',
    passphrase: commanderPassphrase,
  },
  INVALID_COMMANDER: {
    commanderId: 'commander-alpha',
    passphrase: 'wrong_super_secret_passphrase',
  },
  UNKNOWN_USER: {
    commanderId: 'unauthorized-user',
    passphrase: 'wrong_passphrase',
  }
};
