/**
 * Test credentials for Intent Swarm Commander authentication
 */
module.exports = {
  VALID_COMMANDER: {
    commanderId: 'commander-alpha',
    passphrase: 'dev_passphrase',
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
