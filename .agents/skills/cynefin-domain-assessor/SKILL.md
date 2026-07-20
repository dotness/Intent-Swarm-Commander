---
name: cynefin-domain-assessor
description: Acts as a "Pre-flight Check" for Cone of Uncertainty operations by categorizing architectural challenges into Cynefin domains to determine the appropriate planning methodology.
---

# Cynefin Domain Assessor Skill

Goal: Categorize the current technological landscape or architectural problem into a Cynefin domain (Clear, Complicated, Complex, Chaotic) to dictate how the Cone of Uncertainty should be applied.

## Instructions

1. **Assess the Environment**:
   - Analyze the technological challenge or market signal (e.g., a new AI framework, a regulatory change, a legacy system failure).
   - Evaluate the cause-and-effect relationship of the situation. Are the rules known? Do experts agree? Is the environment highly turbulent?

2. **Domain Classification & Logging**:
   - Classify the problem into one of the four primary Cynefin domains using the script:
     `python skills/cynefin-domain-assessor/scripts/assess_domain.py --action log_assessment --name "<problem name>" --domain "<Clear|Complicated|Complex|Chaotic>" --reason "<justification>"`
   - Add details (e.g., specific technologies involved, metrics) in JSON using the `--metadata` flag.

3. **Applying the Methodology**:
   - Read the assessments before applying the Cone of Uncertainty:
     `python skills/cynefin-domain-assessor/scripts/assess_domain.py --action get_assessments`
   - **Rule of Thumb**:
     - **Clear**: Minimal application. Execute standard operating procedures. Do not over-engineer the Cone.
     - **Complicated**: Full Analytical Application. Build the Inverted Cone, define LTV, and identify Node Points.
     - **Complex**: Suspension of Backward Planning. Use Probe-Sense-Respond. Run safe-to-fail experiments until patterns emerge, then transition to the Complicated domain.
     - **Chaotic**: Total Suspension. Use Act-Sense-Respond to stabilize the environment before any LTV planning can resume.

## Constraints
- The assessment must be performed *before* attempting abductive reasoning or backward planning.
- The domain dictates the action: do not apply "Complicated" Cone methodologies to "Complex" or "Chaotic" problems.
