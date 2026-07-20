---
name: ooda-loop-navigator
description: Manages high-velocity micro-level execution and hypothesis testing between Node Points in the Cone of Uncertainty using the Observe, Orient, Decide, Act (OODA) loop.
---

# OODA Loop Navigator Skill

Goal: Execute rapid feedback loops (OODA) to navigate the space between the present architecture and the next established Node Point, filtering out hype and adapting to market volatility.

## Instructions

1. **Observe**:
   - Gather telemetry from existing systems or monitor the AI ecosystem for emerging technologies.
   - Run the script to log a new observation:
     `python skills/ooda-loop-navigator/scripts/navigate_ooda.py --action log_observation --target_node "<node_name>" --observation "<data/telemetry>"`

2. **Orient**:
   - Contextualize the observation against the Long Term Vision (LTV).
   - Filter out "False Cones" (technological hype) by checking if the observation aligns with the shrinking boundaries of the Inverted Cone.
   - If an anomaly is detected, flag it for architectural review.
   - Run the script to log the orientation:
     `python skills/ooda-loop-navigator/scripts/navigate_ooda.py --action log_orientation --observation_id <id> --analysis "<contextualization>" --anomaly_detected <True/False>`

3. **Decide**:
   - Formulate a small, actionable hypothesis designed to move the system toward the *very next* Node Point.
   - Avoid massive, irreversible architectural decisions. Focus on short-term architectural spikes or Proof of Concepts (PoCs).
   - Run the script to log the decision:
     `python skills/ooda-loop-navigator/scripts/navigate_ooda.py --action log_decision --observation_id <id> --hypothesis "<hypothesis>" --action_plan "<plan>"`

4. **Act**:
   - Execute the decision rapidly (e.g., deploy the PoC).
   - Record the outcome of the action to feed the next loop.
   - Run the script to log the action outcome:
     `python skills/ooda-loop-navigator/scripts/navigate_ooda.py --action log_action --observation_id <id> --outcome "<result of action>"`

5. **Review OODA Loops**:
   - To list all current and past OODA loops for a specific Node Point:
     `python skills/ooda-loop-navigator/scripts/navigate_ooda.py --action get_loops --target_node "<node_name>"`

## Constraints
- The OODA loop must be explicitly tied to a specific Node Point defined by the Cone of Uncertainty.
- Actions must be small, iterative, and safe-to-fail (micro-hypotheses).
