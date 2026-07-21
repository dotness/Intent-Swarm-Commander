---
name: ltv-reversed-cone-builder
description: Automates iterative deep web research to build reversed cones for LTV nodes. Use this skill when the user asks to build reversed cones or research prerequisite paths and technologies for LTV nodes.
---

# LTV Reversed Cone Builder Skill

Goal: Conduct iterative deep web research on nodes in the LTV (Long Term Vision) Cone of Uncertainty to discover necessary prerequisites, sub-paths, and false cones, working backwards from a target TO-BE state.

## Instructions

1. **Initialization**:
   - Determine the starting nodes to research (provided by the user, or extracted from the current LTV model using the `ltv-cone-manager` and `node-point-adder` skills).
   - Set the maximum number of iterations (default is 3 unless the user specifies otherwise).
   - Create or update a `task.md` artifact to track progress across iterations.

2. **Iterative Deep Web Research**:
   - **For each iteration:**
     a. Take the list of newly discovered nodes from the previous iteration (or the initial nodes for Iteration 1).
     b. For each node, perform deep web research using the `search_web` tool to find architectural prerequisites, necessary technologies, and false hype/distractors required to reach that node. Focus heavily on verified research, architectural patterns, and production viability.
     c. Log the findings using the other LTV skills:
        - **Paths**: Use `manage_cone.py` from `ltv-cone-manager` to log discovered technologies/steps as "aligned" or "hypothetical" paths.
        - **False Cones**: Use `log_false_cone.py` from `false-cone-detector` to explicitly log technologies or approaches that are hype-driven, insufficient, or do not lead to the goal. Provide objective reasons based on your research.
        - **New Nodes**: Use `add_node.py` from `node-point-adder` to log any major new milestones or gateways discovered during research that act as prerequisites to the current node.
     d. Collect all the *new nodes* discovered in this iteration. These become the target nodes for the next iteration.

3. **Termination**:
   - Stop when you reach the maximum iteration limit (default 3) or when an iteration yields no new nodes to research.
   - Generate a final summary artifact (e.g., `walkthrough.md`) documenting all paths, nodes, and false cones added across all iterations. Include a `mermaid` flowchart diagram illustrating the expanded reversed cone, showing the paths working backwards from the TO-BE state.

## Best Practices and Integration
- This skill acts as an orchestrator for `ltv-cone-manager`, `node-point-adder`, and `false-cone-detector`.
- When logging items via the scripts, always use appropriate JSON metadata to track the relationships (e.g., `{"parent_node": "...", "iteration": N, "source": "..."}`).
- Remember that "reversed cones" work backwards: the technologies you find during research are the *prerequisites* that must be completed *before* the target node can be achieved.
