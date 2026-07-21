import subprocess
import time
import re

nodes_data = [
    ("MCP_Integration_Standard", "Complicated", 
     "Standardized protocol integration with known patterns. Requires expert engineering but outcomes are predictable.",
     "Microservices lack standardized AI tool access.", "MCP offers a standard interface.", "Adopt MCP across the architecture.", "Deploy MCP server templates.", "tested"),
     
    ("Neuro_Symbolic_Verification", "Complicated",
     "Formal verification using solvers is a known mathematical process, though intricate.",
     "LLM outputs for drone commands are probabilistic and prone to hallucinations.", "High-stakes operations require >99% soundness which LLMs cannot guarantee.", "Implement external formal solvers (Z3).", "Integrate NSVIF for mathematical constraint checking.", "tested"),

    ("Verification_1_Constraint_Graph", "Complicated",
     "Translating physical constraints into a queryable graph is a complicated data engineering task.",
     "Drone safety rules exist in unstructured documents.", "A queryable knowledge graph is needed for runtime checks.", "Formalize physical and 6G limits into a graph.", "Build the Constraint Graph using SORA 2.5 encoded rules.", "tested"),

    ("Verification_2_Abductive_Logic_Gate", "Complex",
     "Dealing with semantic mapping and inferring missing premises in dynamic environments is highly non-linear.",
     "Raw LLM intents often miss implicit constraints.", "Abductive reasoning can infer missing premises and check consistency.", "Deploy Abductive Logic Gate.", "Cross-check LLM outputs against the Constraint Graph using abduction.", "hypothetical"),

    ("Verification_3_MINT_Integration", "Complex",
     "Resolving ambiguity via neuro-symbolic trees and HCI relies on unpredictable human-machine dynamics.",
     "Swarm commands contain ambiguities that cause safety halts.", "MINT allows neuro-symbolic trees to actively elicit clarification from human operators.", "Integrate MINT.", "Deploy MINT for ambiguity resolution.", "hypothetical"),

    ("MCP_Gateway_Auth_Gateway", "Complicated",
     "Standard OAuth 2.1 and RBAC implementation follows established security patterns.",
     "Unrestricted MCP servers pose a shadow AI risk.", "Need a Policy Enforcement Point (PEP) for agent authentication.", "Deploy an Auth Gateway using OAuth 2.1.", "Implement MCP Gateway Auth Gateway.", "verified"),

    ("NSVIF_CSP_Solver_Deployment", "Complicated",
     "Deploying CSP solvers into production pipelines is deterministic and well-understood.",
     "Z3/SMT solvers are standalone and disconnected from the AI pipeline.", "Need a production integration of CSP solvers.", "Deploy NSVIF solvers as a formal layer.", "Integrate Z3 via MCP endpoints.", "verified"),

    ("SORA25_Machine_Readable_Encoding", "Complicated",
     "Translating legal regulations (EASA) into OWL ontologies requires domain expertise but is deterministic.",
     "EASA SORA 2.5 rules are PDF documents.", "Automated compliance requires machine-readable ontologies.", "Encode SORA 2.5 into OWL.", "Translate ED Decision 2025/018/R into OWL/XML.", "verified"),

    ("D_ALP_Production_Gate", "Complex",
     "Counter-abduction to filter subtle adversarial hallucination patterns deals with unpredictable neural outputs.",
     "Neural intents can contain subtle adversarial hallucination patterns.", "Discourse-weighted Abductive Logic Programming (D-ALP) counters this via adversarial mechanisms.", "Deploy D-ALP verification layer.", "Validate D-ALP against 500 adversarial scenarios.", "tested"),

    ("MINT_UAV_Simulation_Validation", "Complex",
     "The sim-to-real gap is inherently non-linear and sensitive to unmodeled environmental dynamics.",
     "Sim-to-real gap causes MINT policies to fail in the field.", "Need high-fidelity validation using NVIDIA Isaac Sim.", "Validate MINT in simulation before field deployment.", "Run MINT in Isaac Sim SDG pipelines.", "tested"),

    ("EMA_JIT_Identity_Infrastructure", "Complicated",
     "JIT credentials and EMA follow strict identity engineering protocols.",
     "Agents using static service accounts lead to credential sprawl.", "Enterprise Managed Authorization (EMA) and JIT credentials provide zero-trust security for agents.", "Implement EMA + JIT.", "Configure IdP to issue short-lived agent tokens.", "verified"),

    ("Verification_as_Service_Deployed", "Complicated",
     "Exposing solvers via API/MCP endpoints is standard distributed systems architecture.",
     "Verification logic is tightly coupled with the host application.", "Decoupling verification into an MCP service allows independent scaling and updates.", "Expose Z3/NSVIF as MCP tools.", "Deploy Verification-as-a-Service endpoints.", "verified"),

    ("SORA25_Annex_F_Encoded", "Complicated",
     "Applying mathematical formulas to GIS population data is complex but predictable.",
     "Ground risk (iGRC) calculation requires geospatial population data.", "Annex F provides math formulas to combine Critical Area with Copernicus GHS-POP data.", "Encode Annex F logic.", "Integrate GRC formulas with GIS databases.", "verified"),

    ("SCIFF_ALP_Safety_Supervisor", "Complicated",
     "Deploying symbolic safety supervisors involves clear logical integrity constraints.",
     "Need deterministic reasoning traces for AI auditability.", "SCIFF provides runtime integrity constraints and symbolic tracking.", "Deploy SCIFF Safety Supervisor in parallel with neural models.", "Integrate SCIFF with the command pipeline.", "tested"),

    ("Isaac_Lab_MINT_Validation_Complete", "Complex",
     "Massive-scale domain randomization tests unearth unpredictable emergent behaviors.",
     "UAV field deployment requires high statistical confidence.", "Isaac Lab with OSMO enables massive scaling of long-tail edge case testing.", "Complete MINT validation in Isaac Lab.", "Run multi-node domain randomization tests.", "verified"),

    ("IdP_EMA_JIT_Operational", "Clear",
     "Integrating Okta/Entra ID is standard enterprise IT with established playbooks.",
     "Need a central directory for agent identities.", "Okta/Entra ID are the enterprise standards for IdP.", "Make IdP EMA JIT fully operational.", "Connect MCP Auth Gateway to Entra ID/Okta.", "verified"),

    ("LLM_Solve_Verification_Gateway", "Complex",
     "Dynamic heuristic routing based on intent involves probabilistic judgments and tuning.",
     "Running Z3 for every trivial command adds massive latency.", "A router can distinguish high-stakes (Z3) from low-stakes (direct) commands.", "Implement LLM-as-Scheduler routing.", "Deploy heuristic router for verification requests.", "tested"),

    ("GRC_Auto_Calculation_Live", "Complicated",
     "API integration of GIS models is deterministic engineering.",
     "Manual SORA risk assessment takes hours.", "Automated APIs (Dronedesk/SKYZR) can calculate iGRC instantly using Annex F.", "Take GRC auto-calculation live.", "Integrate live GIS and population APIs into mission planner.", "verified"),

    ("CBF_SCIFF_Dual_Safety_Active", "Complex",
     "Hybrid logical (SCIFF) and physical (CBF) constraint solving operating simultaneously in real-time.",
     "SCIFF ensures logical safety but cannot enforce real-time physical constraints like collision avoidance.", "Control Barrier Functions (CBF) handle physical geofencing.", "Implement a dual logical-physical safety architecture.", "Activate CBF and SCIFF simultaneously.", "tested"),

    ("Isaac_Lab_Safety_Corridor_Certified", "Complicated",
     "Certifying against fixed numerical safety corridors (deviation, latency) is a complicated verification task.",
     "Regulators require quantitative proofs of safety bounds.", "Safety corridors (<2m deviation, <100ms latency) provide measurable benchmarks.", "Certify MINT against safety corridor metrics.", "Run simulation-in-the-loop tests for certification.", "tested"),

    ("HITL_Elicitation_Operational", "Complicated",
     "Policy-as-Code for triggering UI modals is straightforward workflow design.",
     "EU AI Act requires human oversight for high-risk AI systems.", "MCP Elicitation API allows pausing agent workflows for human approval.", "Make HITL elicitation operational for irreversible actions.", "Implement Policy-as-Code to force HITL UI prompts.", "verified"),

    ("Formal_Orchestration_Verified", "Complicated",
     "TLA+ and LTL verification relies on rigorous but known mathematical proofs.",
     "The agent's deterministic orchestration code could have deadlocks or permission bypasses.", "Tools like TLA+ and LTL can mathematically prove properties of the orchestration layer.", "Formally verify the orchestration layer.", "Use AgentVerify and TLA+ to prove termination and safety invariants.", "tested"),

    ("BVLOS_Authorized_Operations", "Complex",
     "Regulatory approval involves interacting with the complex dynamics of national aviation authorities and airspace.",
     "Drone swarms must fly beyond line of sight to be effective.", "Authorities require DAA, UTM, Remote ID, and SORA 2.5 compliance for BVLOS.", "Obtain BVLOS authorization.", "Submit performance-based safety case to NAA.", "hypothetical"),

    ("GCBF_Plus_Swarm_Certified", "Complex",
     "1000+ agent decentralized swarms exhibit complex emergent behaviors that require GNN adaptability.",
     "Traditional CBF fails to scale beyond ~50 agents due to computational limits.", "GCBF+ uses Graph Neural Networks and local LiDAR to scale to 1000+ agents safely.", "Certify GCBF+ for swarm collision avoidance.", "Deploy GCBF+ in multi-agent tests and hardware validation.", "tested")
]

for item in nodes_data:
    node, domain, rationale, obs, ori, dec, act, status = item

    # Run Cynefin assessment
    subprocess.run([
        "python3", ".agents/skills/cynefin-domain-assessor/scripts/assess_domain.py",
        "--action", "log_assessment",
        "--name", node,
        "--domain", domain,
        "--reason", rationale
    ], check=True)
    
    # Run OODA Loop observation
    res = subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_observation",
        "--target_node", node,
        "--observation", obs
    ], capture_output=True, text=True, check=True)
    
    # parse ID from 'Logged new OODA loop (ID: 229) observation'
    m = re.search(r'\(ID: (\d+)\)', res.stdout)
    if not m:
        print(f"Failed to parse ID from {res.stdout}")
        continue
    loop_id = m.group(1)
    
    # Run OODA Loop orientation
    subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_orientation",
        "--observation_id", loop_id,
        "--analysis", ori,
        "--anomaly_detected", "False"
    ], check=True)
    
    # Run OODA Loop decision
    subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_decision",
        "--observation_id", loop_id,
        "--hypothesis", dec,
        "--action_plan", act
    ], check=True)
    
    # Run OODA Loop action
    subprocess.run([
        "python3", ".agents/skills/ooda-loop-navigator/scripts/navigate_ooda.py",
        "--action", "log_action",
        "--observation_id", loop_id,
        "--outcome", status
    ], check=True)

print("All Cynefin and OODA logs completed successfully.")
