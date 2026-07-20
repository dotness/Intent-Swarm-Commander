import sqlite3
import json
import os

LTV_DB = 'ltv_database.db'
CYNEFIN_DB = '.agents/skills/cynefin-domain-assessor/scripts/cynefin.db'
OODA_DB = '.agents/skills/ooda-loop-navigator/scripts/ooda.db'

def get_cynefin_map():
    if not os.path.exists(CYNEFIN_DB): return {}
    conn = sqlite3.connect(CYNEFIN_DB)
    c = conn.cursor()
    c.execute('SELECT name, domain FROM assessments')
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def get_ooda_map():
    if not os.path.exists(OODA_DB): return {}
    conn = sqlite3.connect(OODA_DB)
    c = conn.cursor()
    c.execute('SELECT target_node, COUNT(id), MAX(status) FROM ooda_loops GROUP BY target_node')
    rows = c.fetchall()
    conn.close()
    return {r[0]: {"count": r[1], "status": r[2]} for r in rows}

def get_vision():
    conn = sqlite3.connect('ltv_database.db')
    c = conn.cursor()
    c.execute('SELECT as_is, to_be FROM ltv_vision WHERE id = 1')
    row = c.fetchone()
    conn.close()
    return row

def get_paths():
    conn = sqlite3.connect('ltv_database.db')
    c = conn.cursor()
    c.execute("SELECT name, status, description, metadata FROM cone_paths")
    rows = c.fetchall()
    conn.close()
    return rows

def get_nodes():
    conn = sqlite3.connect('ltv_database.db')
    c = conn.cursor()
    c.execute("SELECT name, description, timestamp, metadata FROM node_points ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_false_cones():
    conn = sqlite3.connect('ltv_database.db')
    c = conn.cursor()
    c.execute("SELECT name, reason, metadata FROM false_cones")
    rows = c.fetchall()
    conn.close()
    return rows

vision = get_vision()
as_is = vision[0] if vision else "Unknown AS-IS"
to_be = vision[1] if vision else "Unknown TO-BE"

paths = get_paths()
all_nodes = get_nodes()
false_cones = get_false_cones()
cynefin_map = get_cynefin_map()
ooda_map = get_ooda_map()

# Process Nodes into hierarchy
subs_by_parent = {}
parent_nodes = []

for n in all_nodes:
    name, desc, ts, meta_str = n
    meta = json.loads(meta_str) if meta_str else {}
    if "parent" in meta:
        parent = meta["parent"]
        if parent not in subs_by_parent:
            subs_by_parent[parent] = []
        subs_by_parent[parent].append(n)
    else:
        parent_nodes.append(n)

path_funnel = {
    "Intent_Driven_Swarm_Commander": ("Neuro_Symbolic_Verification", "MCP_Integration_Standard")
}

node_details = {}
node_details["CurrentState"] = f"<strong>AS-IS State</strong><br/><br/>{as_is}"

mermaid_code = """
graph LR
    classDef current fill:#1e40af,stroke:#60a5fa,stroke-width:2px,color:#fff
    classDef target fill:#991b1b,stroke:#f87171,stroke-width:2px,color:#fff
    classDef hypothetical fill:#854d0e,stroke:#facc15,stroke-width:1px,stroke-dasharray: 5 5,color:#fff
    classDef rejected fill:#450a0a,stroke:#f87171,stroke-width:1px,stroke-dasharray: 5 5,color:#fff
    classDef node fill:#4c1d95,stroke:#a78bfa,stroke-width:2px,color:#fff
    classDef subnode fill:#312e81,stroke:#818cf8,stroke-width:1px,color:#fff

    CurrentState["AS-IS State"]:::current
"""

# Render node definitions
for n in all_nodes:
    name = n[0]
    desc = n[1]
    title = name.replace("_", " ").title()
    meta = json.loads(n[3] or '{}')
    
    cynefin_domain = cynefin_map.get(name, "Not Assessed")
    ooda_info = ooda_map.get(name, {"count": 0, "status": "None"})
    ooda_str = f"OODA Loops: {ooda_info['count']} | Status: {ooda_info['status']}"
    
    research = meta.get("research_summary", "")
    research_html = f"<br/><br/><span style='color: #fbbf24;'><strong>Research (2026):</strong> {research}</span>" if research else ""
    
    node_details[name] = f"<strong>{title}</strong><br/>{desc}{research_html}<br/><br/><span style='color: #60a5fa;'>Domain: {cynefin_domain}</span><br/><span style='color: #34d399;'>{ooda_str}</span>"
    
    if "parent" in meta:
        mermaid_code += f'    {name}["{title}"]:::subnode\n'
    else:
        mermaid_code += f'    {name}["{title}"]:::node\n'

for p in paths:
    name, status, desc, _ = p
    title = name.replace("_", " ").title()
    
    status_label = "TO-BE Goal" if status == "aligned" else status
    cynefin_domain = cynefin_map.get(name, "Not Assessed")
    
    node_details[name] = f"<strong>{title}</strong><br/><em>{status_label}</em><br/><br/>{desc}<br/><br/><span style='color: #60a5fa;'>Domain: {cynefin_domain}</span>"
    
    if status == "aligned":
        title = f"{title} (TO-BE Goal)"
        
    mermaid_code += f'    {name}["{title}"]\n'
    
    if status == "aligned":
        mermaid_code += f'    class {name} target\n'
        
        if name in path_funnel:
            parent_name, gen_name = path_funnel[name]
            
            mermaid_code += f'    CurrentState ==> {gen_name}\n'
            
            subs = subs_by_parent.get(parent_name, [])
            if subs:
                mermaid_code += f'    {gen_name} ==> {subs[0][0]}\n'
                for i in range(len(subs)-1):
                    mermaid_code += f'    {subs[i][0]} ==> {subs[i+1][0]}\n'
                mermaid_code += f'    {subs[-1][0]} ==> {parent_name}\n'
            else:
                mermaid_code += f'    {gen_name} ==> {parent_name}\n'
                
            mermaid_code += f'    {parent_name} ==> {name}\n'
        else:
            mermaid_code += f'    CurrentState ==> {name}\n'
            
    elif status == "hypothetical":
        mermaid_code += f'    CurrentState -.-> {name}\n'
        mermaid_code += f'    class {name} hypothetical\n'
    elif status == "eliminated":
        mermaid_code += f'    CurrentState -.-> {name}\n'
        mermaid_code += f'    class {name} rejected\n'


html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Intent-Swarm-Commander Cone of Uncertainty</title>
    <script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});
    </script>
    <style>
        body {{ background-color: #0f172a; color: #f8fafc; font-family: sans-serif; padding: 2rem; }}
        .card {{ background: #1e293b; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; overflow-x: auto; }}
        h1, h2 {{ margin-top: 0; }}
        .path-list {{ list-style: none; padding: 0; }}
        .path-list li {{ margin-bottom: 1rem; padding: 1rem; border-left: 4px solid; background: #0f172a; }}
        .path-list li.aligned {{ border-color: #f87171; }}
        .path-list li.hypothetical {{ border-color: #facc15; }}
        .path-list li.eliminated {{ border-color: #f87171; }}
        .node-list li {{ border-color: #a78bfa !important; }}
        .sub-node-list {{ list-style: none; padding-left: 2rem; margin-top: 1rem; border-left: 2px dashed #6366f1; }}
        .sub-node-list li {{ border-color: #818cf8 !important; padding: 0.5rem 1rem; margin-bottom: 0.5rem; background: #1e1b4b; }}
        
        /* Fullscreen styles */
        .fullscreen-btn {{
            float: right;
            padding: 8px 16px;
            background-color: #3b82f6;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background-color 0.2s;
        }}
        .fullscreen-btn:hover {{ background-color: #2563eb; }}
        
        :fullscreen #diagram-container {{
            width: 100vw !important;
            height: 100vh !important;
            margin: 0;
            border-radius: 0;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        :fullscreen .mermaid {{
            flex-grow: 1;
            height: 100%;
            overflow: hidden;
        }}
        
        /* Tooltip Styles */
        #tooltip {{
            position: absolute;
            display: none;
            background: #0f172a;
            border: 1px solid #3b82f6;
            border-radius: 6px;
            padding: 1rem;
            color: #f8fafc;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
            z-index: 1000;
            max-width: 350px;
            font-size: 0.9rem;
            line-height: 1.4;
            pointer-events: none;
        }}
    </style>
</head>
<body>
    <div id="tooltip"></div>
    <h1>Intent-Swarm-Commander Ideation: Cone of Uncertainty</h1>
    
    <div class="card">
        <h2>Vision</h2>
        <p><strong>AS-IS:</strong> {as_is}</p>
        <p><strong>TO-BE:</strong> {to_be}</p>
    </div>

    <div class="card" id="diagram-container">
        <h2>LTV Cone Diagram <button class="fullscreen-btn" onclick="toggleFullScreen()">Toggle Fullscreen</button></h2>
        <div class="mermaid">
        {mermaid_code}
        </div>
    </div>

    <div class="card">
        <h2>Paths (TO-BE Goals)</h2>
        <ul class="path-list">
"""

for p in paths:
    name, status, desc, _ = p
    html_class = status if status != "aligned" else "target"
    status_label = "TO-BE Goal" if status == "aligned" else status
    border_color = "#f87171" if status == "aligned" else ("#facc15" if status == "hypothetical" else "#f87171")
    cynefin_domain = cynefin_map.get(name, "Not Assessed")
    
    html += f'            <li style="border-color: {border_color};"><strong>{name.replace("_", " ").title()}</strong> ({status_label}) <span style="color: #60a5fa;">[Domain: {cynefin_domain}]</span><br/>{desc}</li>\n'

html += """
        </ul>
    </div>
"""

if parent_nodes:
    html += """
    <div class="card">
        <h2>Reversed Cone: Critical Node Points</h2>
        <ul class="path-list node-list">
"""
    for n in parent_nodes:
        name, desc, timestamp, meta = n
        meta_dict = json.loads(meta) if meta else {}
        research = meta_dict.get("research_summary", "")
        research_html = f"<br/><br/><strong>Research:</strong> {research}" if research else ""
        cynefin_domain = cynefin_map.get(name, "Not Assessed")
        ooda_info = ooda_map.get(name, {"count": 0, "status": "None"})
        ooda_str = f"OODA Loops: {ooda_info['count']} | Status: {ooda_info['status']}"
        html += f'            <li><strong>{name.replace("_", " ").title()}</strong> ({timestamp}) <span style="color: #60a5fa;">[Domain: {cynefin_domain}]</span> <span style="color: #34d399;">[{ooda_str}]</span><br/>{desc}{research_html}'
        
        subs = subs_by_parent.get(name, [])
        if subs:
            html += '\n                <ul class="sub-node-list">\n'
            for s in subs:
                s_name, s_desc, s_ts, _ = s
                s_cynefin = cynefin_map.get(s_name, "Not Assessed")
                s_ooda = ooda_map.get(s_name, {"count": 0, "status": "None"})
                s_ooda_str = f"OODA Loops: {s_ooda['count']} | Status: {s_ooda['status']}"
                html += f'                    <li><strong>{s_name.replace("_", " ").title()}</strong> ({s_ts}) <span style="color: #60a5fa;">[Domain: {s_cynefin}]</span> <span style="color: #34d399;">[{s_ooda_str}]</span><br/>{s_desc}</li>\n'
            html += '                </ul>\n'
            
        html += '            </li>\n'
        
    html += """
        </ul>
    </div>
"""

if false_cones:
    html += """
    <div class="card">
        <h2>False Cones (Rejected Paths)</h2>
        <ul class="path-list">
"""
    for f in false_cones:
        name, reason, meta = f
        html += f'            <li class="eliminated"><strong>{name.replace("_", " ").title()}</strong><br/>{reason}</li>\n'
    html += """
        </ul>
    </div>
"""

html += f"""
    <script>
        const nodeDetails = {json.dumps(node_details)};
        let panZoomInstance = null;
        
        // Setup Pan and Zoom after Mermaid renders
        const observer = new MutationObserver((mutations, obs) => {{
            const svg = document.querySelector('.mermaid svg');
            if (svg) {{
                // Set initial height so panzoom behaves
                svg.style.maxHeight = 'none';
                svg.style.height = '600px'; 
                
                panZoomInstance = svgPanZoom(svg, {{
                    zoomEnabled: true,
                    controlIconsEnabled: true,
                    fit: true,
                    center: true,
                    minZoom: 0.1,
                    maxZoom: 10
                }});
                obs.disconnect();
            }}
        }});
        
        observer.observe(document.getElementById('diagram-container'), {{ childList: true, subtree: true }});

        // Fullscreen Logic
        function toggleFullScreen() {{
            const container = document.getElementById('diagram-container');
            if (!document.fullscreenElement) {{
                container.requestFullscreen().catch(err => {{
                    console.error(`Error attempting to enable fullscreen: ${{err.message}}`);
                }});
            }} else {{
                document.exitFullscreen();
            }}
        }}

        document.addEventListener("fullscreenchange", function() {{
            const svg = document.querySelector('.mermaid svg');
            if (svg && panZoomInstance) {{
                if (document.fullscreenElement) {{
                    svg.style.height = '100%';
                }} else {{
                    svg.style.height = '600px';
                }}
                // Wait for the browser to recalculate dimensions, then resize diagram
                setTimeout(() => {{
                    panZoomInstance.resize();
                    panZoomInstance.fit();
                    panZoomInstance.center();
                }}, 100);
            }}
        }});
        
        // Tooltip Logic
        document.addEventListener('mouseover', function(e) {{
            const node = e.target.closest('.node');
            const tooltip = document.getElementById('tooltip');
            
            if (node) {{
                const idAttr = node.getAttribute('id') || '';
                let foundKey = null;
                
                for (const key in nodeDetails) {{
                    if (idAttr.includes(key)) {{
                        foundKey = key;
                        break;
                    }}
                }}
                
                if (foundKey) {{
                    tooltip.innerHTML = nodeDetails[foundKey];
                    tooltip.style.display = 'block';
                }}
            }}
        }});
        
        document.addEventListener('mousemove', function(e) {{
            const tooltip = document.getElementById('tooltip');
            if (tooltip.style.display === 'block') {{
                let x = e.pageX + 15;
                let y = e.pageY + 15;
                if (x + 350 > window.innerWidth) x = e.pageX - 365;
                tooltip.style.left = x + 'px';
                tooltip.style.top = y + 'px';
            }}
        }});

        document.addEventListener('mouseout', function(e) {{
            const node = e.target.closest('.node');
            if (node) {{
                document.getElementById('tooltip').style.display = 'none';
            }}
        }});
    </script>
</body>
</html>
"""

with open('ltv_cone_visualization.html', 'w') as f:
    f.write(html)

print("Generated ltv_cone_visualization.html successfully.")
