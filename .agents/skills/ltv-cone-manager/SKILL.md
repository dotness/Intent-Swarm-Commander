---
name: ltv-cone-manager
description: Creates and updates the Cone of Uncertainty model for Long Term Vision (LTV) of IT systems, saving to an SQLite database. Use this skill when the user asks to build, update, or read the LTV model.
---

# LTV Cone Manager Skill

Goal: Create, read, and update the Cone of Uncertainty model to support Long Term Vision (LTV) planning for computer systems. The model's state is persistently stored in an SQLite database (`ltv_database.db`).

## Instructions

1. **Initialization / Reading State**:
   - Before creating a new model, always check the current state of the database using the `scripts/manage_cone.py` script.
   - Run `python scripts/manage_cone.py --action get_vision` to read the current AS-IS and TO-BE vision.

2. **Setting or Updating the Vision**:
   - If the user provides a new initial state (AS-IS) or target state (TO-BE), use the script to save it:
   - Run `python scripts/manage_cone.py --action set_vision --as_is "<as-is description>" --to_be "<to-be description>"`

3. **Creating Paths (Traditional Cone and Reversed Cone)**:
   - To add a new possible development path (traditional cone), run:
     `python scripts/manage_cone.py --action add_path --name "<name>" --description "<description>" --status "hypothetical"`
   - When working backward from the target state (TO-BE) and determining that a path leads to the goal (reversed cone), update its status:
     `python scripts/manage_cone.py --action update_path_status --name "<name>" --status "aligned"`
   - When determining that it does not lead to the goal, mark it:
     `python scripts/manage_cone.py --action update_path_status --name "<name>" --status "eliminated"`

4. **Correction against the AI Ecosystem**:
   - Use statuses to reflect the real direction of the market. Paths can have arbitrary JSON metadata assigned (using the `--metadata '{"key": "value"}'` argument).

5. **Visualization / Representation**:
   - After any modifications, always generate a summary (or Mermaid.js diagram) for the user based on the data read from the script (`--action get_all_paths`).

## Constraints
- Do not modify the database manually; always use the provided Python script.
- Ensure that the JSON structure in the metadata (if added) is valid.
