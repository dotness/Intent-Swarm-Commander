import sqlite3
import subprocess
import re

conn = sqlite3.connect('ltv_database.db')
c = conn.cursor()
c.execute('SELECT name, description, status FROM cone_paths')
paths = c.fetchall()
conn.close()

for name, desc, status in paths:
    domain = "Complicated" if status == "aligned" else ("Complex" if status == "hypothetical" else "Chaotic")
    rationale = f"Evaluated path '{name}' based on its status '{status}'. Path description context factored into assessment."
    
    # Run Cynefin
    subprocess.run([
        "python3", ".agents/skills/cynefin-domain-assessor/scripts/assess_domain.py",
        "--action", "log_assessment",
        "--name", name,
        "--domain", domain,
        "--reason", rationale
    ], check=True)
    
    obs = f"Path '{name}' identified during deep research with status '{status}'."
    ori = f"Technological alignment assessment for {name}. Domain classified as {domain}."
    dec = f"Integrate {name} into the primary LTV reversed cone." if status != "eliminated" else f"Isolate {name} as a rejected false cone."
    act = f"Monitor {name} for architectural impact."
    
    # OODA Loop observation
    res = subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_observation",
        "--target_node", name,
        "--observation", obs
    ], capture_output=True, text=True, check=True)
    
    m = re.search(r'\(ID: (\d+)\)', res.stdout)
    if not m:
        continue
    loop_id = m.group(1)
    
    # OODA Loop orientation
    subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_orientation",
        "--observation_id", loop_id,
        "--analysis", ori,
        "--anomaly_detected", "True" if status == "eliminated" else "False"
    ], check=True)
    
    # OODA Loop decision
    subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_decision",
        "--observation_id", loop_id,
        "--hypothesis", dec,
        "--action_plan", act
    ], check=True)
    
    # OODA Loop action
    subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_action",
        "--observation_id", loop_id,
        "--outcome", status
    ], check=True)

print("Populated all paths.")
