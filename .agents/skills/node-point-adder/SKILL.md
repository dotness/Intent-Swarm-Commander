---
name: node-point-adder
description: Adds Node Points (milestones) to the LTV Cone of Uncertainty model in the SQLite database. Use this skill when the user asks to define critical stages.
---

# Node Point Adder Skill

Goal: Identify and add Node Points in the reversed cone of uncertainty model and save them to the SQLite database.

## Instructions

1. **Context Analysis**:
   - Use `python ../ltv-cone-manager/scripts/manage_cone.py --action get_vision` to check the current LTV model.
   - Receive information from the user about a new technology, legal requirement, or milestone.

2. **Adding a Node Point to the Database**:
   - Once you identify a node point, add it using the script:
     `python scripts/add_node.py --action add_node --name "<name>" --description "<description>" --timestamp "<time/stage>"`
   - You can also save additional information from the ecosystem using the `--metadata '{"key": "value"}'` flag (e.g., links, related technologies).

3. **Visualizing Node Points**:
   - To list current points, use:
     `python scripts/add_node.py --action get_nodes`
   - After adding a point, update the model representation (e.g., LTV diagram).

## Constraints
- A node point must represent a critical gateway in the reversed cone model.
- Ensure the node name is unique.
