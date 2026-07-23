# Minimum Viable Product (MVP) Scope

This document outlines the Minimum Viable Product (MVP) scope derived from the Long Term Vision (LTV) document, focusing on foundational prerequisites and Q1/Q2 2026 deliverables. It is split into two tiers: **Essential (Must-Have)** and **MVP (Fast-Follow)**.

## Core Vision
**Intent Driven Swarm Commander (MVP Version)**
Build an MCP-enabled Command Agent that translates high-level military intents (SMEAC orders) into coordinated drone swarm actions using coarse-grained operators. Showcases cross-domain fusion.

# Tier 1: Essential (Must-Have Prerequisites)
These components are foundational blockings required before any MVP components can be safely deployed.

## MCP_Integration_Standard
### MCP_Gateway_Architecture
- **Description:** Deploying a centralized MCP Gateway as the governed control plane for all agent-to-tool interactions. Acts as a chokepoint for policy enforcement, audit logging, and RBAC/ABAC access control. Required prerequisite before MCP_Integration_Standard can be called production-grade.
- **Timeline:** Q1-Q2 2026

### OAuth21_NHI_Identity
- **Description:** Implementing OAuth 2.1 with Dynamic Client Registration (DCR) and Resource Indicators (RFC 8707) specifically for Non-Human Identities (AI agents). Every agent must have a cryptographically verified identity with per-action runtime authorization. Pre-requisite for secure MCP in enterprise.
- **Timeline:** Q1 2026

### EU_AI_Act_Compliance_Gate
- **Description:** Establishing mandatory Human-in-the-Loop (HITL) approval gates and automated observability/audit logging for all agentic actions, driven by EU AI Act full enforcement (August 2026). Non-compliance blocks production MCP deployment in EU regulatory scope.
- **Timeline:** Q2-Q3 2026

### MCP_Gateway_Auth_Gateway
- **Description:** The critical gateway where MCP infrastructure is secured with OAuth 2.1 + NHI identity, RBAC/ABAC policy enforcement, and the MCP Registry is operational. Production MCP cannot proceed without this auth gateway being established. Discovered prerequisite to MCP_Integration_Standard.
- **Timeline:** Prerequisite/Foundational

## Verification_1_Constraint_Graph
### SORA25_Ontology_Formalization
- **Description:** Encoding SORA 2.5 (EASA/JARUS Specific Operations Risk Assessment, ED Decision 2025/018/R) UAS operational safety objectives into machine-readable ontologies for runtime constraint enforcement. Foundational prerequisite for the Constraint Graph node. Enables automated risk determination and constraint-based planning.
- **Timeline:** Q4 2026

### SORA25_Machine_Readable_Encoding
- **Description:** The milestone where SORA 2.5 UAS operational safety rules (EASA ED Decision 2025/018/R) are fully encoded as machine-readable ontologies. Prerequisite to building the Constraint Graph. Required before any semantic runtime verification of drone operations can occur.
- **Timeline:** Prerequisite/Foundational

## MCP_Gateway_Auth_Gateway
### Enterprise_Managed_Authorization_EMA
- **Description:** Implementing Enterprise-Managed Authorization (EMA) with Identity Assertion JWTs (ID-JAG) that bypass per-server OAuth prompts. Central IdP issues authorizations for all MCP agents, eliminating per-server consent friction while maintaining audit trails. Critical gateway prerequisite for MCP_Gateway_Auth_Gateway.
- **Timeline:** Q1-Q2 2026

## IdP_EMA_JIT_Operational
### HITL_Elicitation_API_Critical_Actions
- **Description:** Implementing mandatory Human-in-the-Loop (HITL) elicitation API for high-impact or irreversible swarm actions (mass abort, ROE changes, swarm redirect). MCP elicitation API routes these decisions to human commander confirmation UI before execution. EU AI Act compliance requirement.
- **Timeline:** Q1-Q2 2026

## GRC_Auto_Calculation_Live
### Remote_ID_UTM_Integration
- **Description:** Mandatory Remote ID broadcasting integration with UTM systems for real-time airspace deconfliction. Regulatory prerequisite for BVLOS swarm operations. Establishes the digital airspace identity layer required before autonomous swarm missions can be authorized by NAAs.
- **Timeline:** Q3-Q4 2026

## Neuro_Symbolic_Verification
### NSVIF_CSP_Solver_Deployment
- **Description:** The milestone where NSVIF constraint satisfaction solvers are deployed in the production pipeline as a formal verification layer for all LLM-generated outputs. Gateway between probabilistic generation and deterministic safety enforcement. Discovered prerequisite to Neuro_Symbolic_Verification.
- **Timeline:** Prerequisite/Foundational

## Verification_3_MINT_Integration
### MINT_UAV_Simulation_Validation
- **Description:** The milestone where MINT neuro-symbolic tree planning is validated in high-fidelity UAV simulations (NVIDIA Isaac Sim) and field deployments before integration with the SMEAC Intent Commander. Discovered prerequisite to Verification_3_MINT_Integration.
- **Timeline:** Prerequisite/Foundational

# Tier 2: MVP Scope (Fast-Follow)
These components complete the end-to-end MVP functionality, building upon the Essential tier.

## MCP_Integration_Standard
### MCP_Registry_Discovery
- **Description:** Adopting MCP Server Cards and the MCP Registry ecosystem for capability discovery without active connections. Enables modular, reusable microservice discovery and supply chain security via cryptographic server signatures. Required for eliminating brittle custom integrations.
- **Timeline:** Q2-Q3 2026

## MCP_Gateway_Auth_Gateway
### JIT_Ephemeral_Agent_Identity
- **Description:** Deploying Just-in-Time (JIT) ephemeral agent identity lifecycle management. Agents receive short-lived signed credentials for each task session; identity is automatically retired post-completion. Prevents credential sprawl in multi-swarm environments where hundreds of drone control agents coexist.
- **Timeline:** Q1 2026

## EMA_JIT_Identity_Infrastructure
### Okta_Entra_IdP_MCP_Integration
- **Description:** Integrating enterprise IdPs (Okta, Microsoft Entra) with MCP EMA flow using ID-JAG JWT grants. Establishes the identity governance backbone for all drone swarm agents. Centralized policy management eliminates per-server OAuth sprawl and provides automated revocation upon task completion.
- **Timeline:** Q1 2026

### Britive_JIT_Access_Elevation
- **Description:** Deploying JIT access elevation pattern (Britive/Akeyless pattern) where drone swarm agents receive task-scoped, time-bound tokens that auto-expire. Eliminates credential sprawl in multi-swarm environments. Required before EMA_JIT_Identity_Infrastructure can be considered production-safe.
- **Timeline:** Q1 2026

## IdP_EMA_JIT_Operational
### Scope_Based_Tool_Loading_RBAC
- **Description:** Implementing scope-based tool loading so AI swarm agents only receive MCP tool access strictly aligned with authenticated user privileges. Follows least-privilege principle at tool granularity. Prevents unauthorized access to destructive operations (e.g., mass abort, swarm redirect) by lower-privilege agents.
- **Timeline:** Q1 2026

## HITL_Elicitation_Operational
### Policy_as_Code_HITL_Enforcement
- **Description:** Implementing Policy-as-Code to enforce that specific swarm tool calls (ROE changes, mass abort, swarm redirect) always trigger HITL approval checks via MCP elicitation configureElicitationHandlers(). Ensures governance-by-design rather than relying on agent discretion for safety-critical decisions.
- **Timeline:** Q2 2026

### Durable_Approval_Gates_Long_Missions
- **Description:** Implementing durable workflow gates (waitForApproval() primitives on persistent task state) for long-running or multi-day swarm mission plans. Agent state persists without active connection; human commander can approve/reject days later. Critical for strategic-level SMEAC operations with extended planning cycles.
- **Timeline:** Q2 2026
