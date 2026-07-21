import sqlite3
import os
import json

os.makedirs('design', exist_ok=True)
md_file = 'design/LTV.md'

LTV_DB = 'ltv_database.db'
CYNEFIN_DB = '.agents/skills/cynefin-domain-assessor/scripts/cynefin.db'
OODA_DB = '.agents/skills/ooda-loop-navigator/scripts/ooda.db'

def dump_ltv(f):
    if not os.path.exists(LTV_DB): return
    conn = sqlite3.connect(LTV_DB)
    c = conn.cursor()
    
    f.write("# LTV (Long Term Vision) Database Dump\n\n")
    
    # Vision
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ltv_vision'")
    if c.fetchone():
        c.execute("SELECT as_is, to_be FROM ltv_vision WHERE id = 1")
        row = c.fetchone()
        if row:
            f.write("## Vision\n")
            f.write(f"**AS-IS:** {row[0]}\n\n")
            f.write(f"**TO-BE:** {row[1]}\n\n")
            
    # Paths
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cone_paths'")
    if c.fetchone():
        c.execute("SELECT name, status, description, metadata FROM cone_paths")
        paths = c.fetchall()
        if paths:
            f.write("## Cone Paths\n")
            for p in paths:
                f.write(f"### {p[0]}\n")
                f.write(f"- **Status:** {p[1]}\n")
                f.write(f"- **Description:** {p[2]}\n")
                f.write(f"- **Metadata:** {p[3]}\n\n")
                
    # Nodes
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='node_points'")
    if c.fetchone():
        c.execute("SELECT name, description, timestamp, metadata FROM node_points ORDER BY id ASC")
        nodes = c.fetchall()
        if nodes:
            f.write("## Node Points\n")
            for n in nodes:
                f.write(f"### {n[0]}\n")
                f.write(f"- **Timestamp:** {n[2]}\n")
                f.write(f"- **Description:** {n[1]}\n")
                f.write(f"- **Metadata:** {n[3]}\n\n")
                
    # False Cones
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='false_cones'")
    if c.fetchone():
        c.execute("SELECT name, reason, metadata FROM false_cones")
        false_cones = c.fetchall()
        if false_cones:
            f.write("## False Cones\n")
            for fc in false_cones:
                f.write(f"### {fc[0]}\n")
                f.write(f"- **Reason:** {fc[1]}\n")
                f.write(f"- **Metadata:** {fc[2]}\n\n")

    conn.close()

def dump_cynefin(f):
    if not os.path.exists(CYNEFIN_DB): return
    conn = sqlite3.connect(CYNEFIN_DB)
    c = conn.cursor()
    
    f.write("# Cynefin Database Dump\n\n")
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assessments'")
    if c.fetchone():
        c.execute("SELECT name, domain, reason, timestamp FROM assessments")
        rows = c.fetchall()
        if rows:
            f.write("## Assessments\n")
            for r in rows:
                f.write(f"### {r[0]}\n")
                f.write(f"- **Domain:** {r[1]}\n")
                f.write(f"- **Timestamp:** {r[3]}\n")
                f.write(f"- **Reason:** {r[2]}\n\n")
    
    conn.close()

def dump_ooda(f):
    if not os.path.exists(OODA_DB): return
    conn = sqlite3.connect(OODA_DB)
    c = conn.cursor()
    
    f.write("# OODA Database Dump\n\n")
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ooda_loops'")
    if c.fetchone():
        # Get column names dynamically in case schema varies
        c.execute("PRAGMA table_info(ooda_loops)")
        columns = [col[1] for col in c.fetchall()]
        
        c.execute("SELECT * FROM ooda_loops")
        rows = c.fetchall()
        if rows:
            f.write("## OODA Loops\n")
            for r in rows:
                target_node = r[columns.index('target_node')] if 'target_node' in columns else "Unknown"
                f.write(f"### Loop for {target_node}\n")
                for i, col in enumerate(columns):
                    if col not in ['id', 'target_node']:
                        f.write(f"- **{col}:** {r[i]}\n")
                f.write("\n")
                
    conn.close()

with open(md_file, 'w') as f:
    dump_ltv(f)
    f.write("---\n\n")
    dump_cynefin(f)
    f.write("---\n\n")
    dump_ooda(f)

print(f"Databases dumped to {md_file} successfully.")
