---
name: false-cone-detector
description: Detects "false cones" of disinformation or technological hype in the AI ecosystem, and logs rejected trends to the SQLite database.
---

# False Cone Detector Skill

Goal: Recognize, filter, and persistently log false cones (technological hype) in the database to protect the Long Term Vision model.

## Instructions

1. **Identification of a Potential False Cone**:
   - Read the vision and paths (using `manage_cone.py`). Compare the new trend with the target goal (TO-BE).
   - Conduct cross-analysis of the trend to detect an "information bubble".

2. **Logging to the Database**:
   - If the logical sequence leads to an artificially created state, reject it and save it in the database:
     `python scripts/log_false_cone.py --action log_cone --name "<trend name>" --reason "<reason for rejection>"`
   - Add details (e.g., sources of hype) in JSON using the `--metadata` flag.

3. **Review of Rejected Paths**:
   - To list identified false cones (e.g., before adding a new technology to the LTV, to avoid repeating a mistake), use:
     `python scripts/log_false_cone.py --action get_cones`

## Constraints
- The assessment must be based on objective verification and data fusion.
- Every rejected trend must have a specific reason for rejection.
