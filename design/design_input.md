# Intent Swarm Commander (ISC) - MVP Design & Architecture Input

## 1. Overview and Core Vision
**Project:** Intent Driven Swarm Commander (MVP Version)
**Goal:** Build an MCP-enabled Command Agent that translates high-level military intents (SMEAC orders) into coordinated drone swarm actions using coarse-grained operators, showcasing cross-domain fusion.

This document serves as the updated design and architecture blueprint, bridging the gap between initial conceptual drafts and the mandatory Minimum Viable Product (MVP) compliance requirements (EU AI Act, SORA 2.5, MCP standards).

---

## 2. Updated Architectural Flow (Remediating Draft 2)

The initial architecture (`Worker -> Swarm Pool -> Drone`) bypassed critical security, verification, and identity layers. The revised architecture must visually and technically represent the Model Context Protocol (MCP) as the central nervous system.

### 2.1 The Compliant Pipeline
The new system diagram must reflect the following mandatory flow:
1. **GUI / Elicitation API** (Commander Interface)
2. **Worker (Agent)**
3. **MCP Auth Gateway** (OAuth 2.1 / NHI / EMA / JIT Identity)
4. **MCP Tool Execution Gateway** (Scope-based RBAC enforcement)
5. **Safety Verification Layer** (NSVIF Constraint Solvers + SORA 2.5 Constraint Graph)
6. **Swarm Pool** (Task orchestration)
7. **Drone Layer** (Includes mandatory Remote ID & UTM Integration)

### 2.2 Key Architectural Components to Model
* **Hierarchical Planning:** Maintain the design where the central pool issues coarse commands and drones handle local autonomy (e.g., obstacle avoidance).
* **MCP Control Plane:** Model a centralized chokepoint for policy enforcement and audit logging.
* **Identity Node:** Show Enterprise-Managed Authorization (EMA) with Just-In-Time (JIT) ephemeral identity for agents to prevent credential sprawl.
* **Verification Node:** Explicitly map the NSVIF constraint satisfaction solvers and SORA 2.5 ontology checks before execution.
* **Airspace Integration:** Show Remote ID broadcasting connecting to external UTM systems at the Drone layer.

---

## 3. UI/UX Design Requirements (Remediating Draft 1)

The initial UI sketch (Tactical Map, Unit Roster, SMEAC Order Panel, History/State) is a strong foundation. However, to meet EU AI Act and MVP compliance, specific UI components must be added.

### 3.1 Components to Retain and Polish
* **SMEAC Order Ingestion Panel:** Text/form input where the commander inputs the high-level intent.
* **Cross-Domain Tactical Map:** Central visualization showing multiple unit types, military symbols, and movement vectors.
* **Unit Roster & History State:** Side panels for monitoring live unit status and action history.

### 3.2 Mandatory New UI Components
* **HITL (Human-in-the-Loop) Confirmation Gateway (Modal/Overlay):**
  * **Trigger:** High-impact/irreversible agent actions (e.g., Mass Abort, ROE (Rules of Engagement) changes, Swarm Redirect).
  * **Design:** A highly visible confirmation overlay requiring explicit human authorization before the elicitation API releases the command.
* **Durable Approval Workflow Dashboard (Pending Actions Panel):**
  * **Purpose:** For long-running missions where agents create plans that might need approval days later.
  * **Design:** A dedicated queue/inbox showing pending authorizations, plan summaries, and "Approve/Reject" workflow gates.
* **Agent Identity & Scope Indicators:**
  * **Purpose:** Visual confirmation of agent permissions.
  * **Design:** Badges or indicators showing the active agent's JIT identity status and current RBAC scope (e.g., "Agent Auth: Valid (2h remaining) - Scope: Recon Only").
* **Verification & Safety Status Module:**
  * **Purpose:** Visibility into the automated safety checks.
  * **Design:** A status indicator (traffic light or checklist) showing real-time feedback from the NSVIF solvers and SORA 2.5 constraint graph (e.g., "Airspace Deconflicted", "Safety Objectives Met").

---

## 4. Next Steps for Design Team
1. **Wireframes:** Update the UI wireframes to include the HITL Modal and Durable Approval Queue.
2. **System Diagram:** Draft a new technical architecture diagram matching the 7-step pipeline detailed in section 2.1.
3. **Component States:** Design the "Pending", "Verified", and "Blocked by Policy" states for drone swarm tasks.