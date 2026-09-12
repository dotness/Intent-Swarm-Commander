/**
 * SMEAC Order test data payloads
 */
module.exports = {
  VALID_SMEAC: {
    situation: 'Hostile radar installation active in quadrant 7. Terrain is hilly with sparse tree cover.',
    mission: 'Conduct aerial reconnaissance along flight corridor Bravo-2 to locate target coordinates.',
    execution: 'Alpha drones advance in wedge formation at 120m AGL. Maintain RF silence until rally point.',
    administration: 'Reserve battery swaps available at FOB Echo. Recovery protocol standard.',
    command: 'Commander Alpha leading; fallback channel Delta-9.'
  },
  HIGH_IMPACT_SMEAC: {
    situation: 'Unidentified drone swarm breaching southern perimeter near critical infrastructure.',
    mission: 'INTERCEPT AND NEUTRALIZE HOSTILE SWARM; AUTHORIZE EMERGENCY COUNTERMEASURES.',
    execution: 'Deploy electronic countermeasures and defensive intercept vector immediately.',
    administration: 'Emergency ordnance authorization level Red.',
    command: 'Commander Alpha direct command override.'
  },
  INCOMPLETE_SMEAC: {
    situation: '',
    mission: '',
    execution: 'Move north.',
    administration: '',
    command: ''
  }
};
