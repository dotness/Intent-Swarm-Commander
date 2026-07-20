# AI Agent Instructions for Cone of Uncertainty Framework

These rules apply to all AI agents working within this repository.

## Versioning Rules

- **Check Version**: All AI agents must check the repository version upon initialization or when checking for updates.
- **VERSION File**: The current version of the repository is stored in the `VERSION` file located in the root directory.
- **Action**: Always read the `VERSION` file to determine if you have the latest version or are operating within the correct major/minor release context (e.g., v2).

## Cone of Uncertainty and Long Term Vision (LTV) Rules

- **The Traditional Cone**: Represents the rapidly multiplying possibilities from the current system architecture ("AS-IS" state) over time. It demonstrates the impossibility of predicting a single forward path.
- **The Inverted Cone (Reversed Cone)**: Start from a defined End State or Long Term Vision ("TO-BE" state) and work backward to eliminate paths that do not lead to the goal. This reduces uncertainty and identifies required steps.
- **Node Points**: Identify inevitable convergence points on the timeline that the system must pass through to achieve the vision (e.g., critical technological gateways).
- **False Cones**: Be vigilant of deliberate deceptive actions or technological "hype." Distinguish genuine evolution from corporate marketing noise to avoid paths that diverge from the desired state.

## LTV Cone Manager Rules

- **Purpose**: Creates and updates the Long Term Vision (LTV) and Cone of Uncertainty models in the SQLite database (`ltv_database.db`).
- **Scripts**: Always use `manage_cone.py` located in `skills/ltv-cone-manager/scripts/` to interact with the database. Do not modify the database manually.
- **Actions**:
  - `get_vision`: Read current AS-IS and TO-BE states before creating new models.
  - `set_vision`: Save new AS-IS or TO-BE states.
  - `add_path`: Add new paths with status "hypothetical".
  - `update_path_status`: Change status to "aligned" (leads to goal) or "eliminated" (does not lead to goal).
- **Visualization**: Generate a summary for the user after modifications. Generating visual HTML diagrams (via test scripts) is optional and primarily intended for UATs; do not run HTML generation automatically after every change unless explicitly requested.

## Node Point Adder Rules

- **Purpose**: Identify and log critical milestones or gateways (Node Points) on the Inverted Cone timeline.
- **Scripts**: Use `add_node.py` located in `skills/node-point-adder/scripts/` to manage Node Points in the database.
- **Actions**:
  - `add_node`: Save new Node Points with specific timestamps/stages and ensure names are unique.
  - `get_nodes`: List current Node Points.
- **Integration**: Consider using the LTV Cone Manager's `get_vision` beforehand for context. Updating visual model representations (e.g., generating HTML diagrams) is optional and intended mainly for UATs.

## False Cone Detector Rules

- **Purpose**: Detect and filter out technological hype or "false cones," and persistently log them to protect the LTV model.
- **Scripts**: Use `log_false_cone.py` located in `skills/false-cone-detector/scripts/`.
- **Actions**:
  - `log_cone`: Log a rejected trend with a specific reason for rejection based on objective cross-analysis.
  - `get_cones`: List identified false cones to prevent repeating mistakes when adding new technologies.
- **Evaluation**: Assessments must rely on verifiable data fusion, comparing new trends directly against the target TO-BE goal.

## Cynefin Domain Assessor Rules

- Before applying any backward planning or Inverted Cone methodology, you must classify the environment using the Cynefin Domain Assessor skill.
- Call the `assess_domain.py` script located in `skills/cynefin-domain-assessor/scripts/` to log the domain classification (Clear, Complicated, Complex, Chaotic).
- Only apply full analytical Cone operations if the problem is in the "Complicated" domain.
- If the problem is "Complex," switch to a Probe-Sense-Respond methodology instead.
- If the problem is "Chaotic," suspend all long-term planning and use Act-Sense-Respond.

## OODA Loop Navigator Rules

- For short-term execution between Node Points in the Cone of Uncertainty, use the OODA Loop Navigator skill.
- Call the `navigate_ooda.py` script located in `skills/ooda-loop-navigator/scripts/` to log your observations, orientations, decisions, and actions.
- All OODA loops must be explicitly tied to a predefined target Node Point from the Long Term Vision.
- Do not make massive, irreversible architectural decisions within an OODA loop; focus on micro-hypotheses and short-term iterations (e.g., PoCs).
