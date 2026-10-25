# Architectural Integration & Deep Analysis: Intent-Swarm-Commander & Poor-Man's Artemis.IA

**Document ID:** `DOC-ANALYSIS-ISC-PMA-001`  
**Date:** October 2026  
**Status:** Approved for Design Integration  
**Target Repository:** `Intent-Swarm-Commander` (v0.2.0)  
**Partner Repository:** `Poor-Man-s-Artemis.IA` (v0.2.0)  

---

## 1. Executive Summary

**Intent-Swarm-Commander (ISC)** is a tactical multi-drone swarm command-and-control (C2) system designed to decompose high-level military intents (**SMEAC**: Situation, Mission, Execution, Administration/Logistics, Command/Signal) into synchronized drone flight trajectories, automated computer-vision target recognition (YOLO-E), and durable Temporal workflows.

**Poor-Man's Artemis.IA (PMA)** is an ultra-lean, sovereign big data lakehouse and AI infostructure inspired by the French Ministry of Armed Forces' ARTEMIS.IA program. Engineered to run completely on a single commodity Linux VM (16–32 GB RAM, CPU-only) with **zero JVM overhead**, PMA provides high-throughput MQTT telemetry ingestion (Eclipse Mosquitto), columnar Parquet object storage (MinIO), sub-second vectorized SQL analytics (DuckDB), in-memory graph knowledge discovery (Memgraph), and autonomous multi-agent reasoning (Google ADK 2.0 / Gemini).

### The Strategic Value Proposition
Currently, **Intent-Swarm-Commander** operates with ephemeral in-memory state for drone telemetry, a polling-based HTTP interface for edge drones, static JSON configuration for restricted airspaces, and no capability for long-term telemetry retention or historical fleet analytics.

Integrating **Poor-Man's Artemis.IA** into **Intent-Swarm-Commander** transforms ISC from a local drone flight dispatcher into a full-scale **C4ISR (Command, Control, Communications, Computers, Intelligence, Surveillance, and Reconnaissance)** platform. This integration unlocks:
1. **High-Throughput Swarm Telemetry Ingestion**: Scalable MQTT ingestion bus handling hundreds of simultaneous UAV telemetry streams without HTTP polling bottlenecks.
2. **Columnar Lakehouse & After-Action Review (AAR)**: Persistent Parquet storage on MinIO with sub-second DuckDB SQL queries over historical flight paths, battery degradation, and mission logs.
3. **Dynamic Battlefield Knowledge Graph**: Memgraph-powered tactical situational awareness, replacing static geofence files with dynamic threat envelopes (SAMs, radars, jammer ranges, and OSINT targets).
4. **Sensor Fusion & Target Identification Lineage**: Logging and cross-referencing YOLO-E edge computer vision detections with adversary intelligence entities.
5. **Intelligence-Driven SMEAC Drafting**: Autonomous agentic reasoning leveraging DuckDB and Memgraph tools to answer complex commander queries and draft SMEAC orders automatically.

---

## 2. Architectural Comparison & Synergy Matrix

Both systems were built following identical software engineering principles from the [`uservice-template`](https://github.com/dotness/uservice-template) standard: Domain-Driven Design (DDD), Clean/Hexagonal Architecture (`api`, `facade`, `operations`, `models`), asynchronous Temporal workflow orchestration, Pydantic type safety, and JWT Bearer security.

### 2.1 Component Comparison

| Functional Tier | Intent-Swarm-Commander (Current) | Poor-Man's Artemis.IA (PMA) | Synergy & Target Integrated State |
| :--- | :--- | :--- | :--- |
| **Telemetry Ingress** | Ephemeral HTTP polling (`GET :8090/telemetry`) | Eclipse Mosquitto MQTT (`:1883`, C-native, 1,000+ evt/s) | **MQTT Telemetry Bus**: Edge drones stream MAVLink telemetry directly to Mosquitto. |
| **Long-Term Storage** | PostgreSQL 15 (transactional tables only) | MinIO (S3-compatible, partitioned Parquet) | **S3 Lakehouse**: Mission history and high-frequency sensor readings stored in Parquet objects. |
| **Analytical Query Engine** | None (PostgreSQL basic queries) | DuckDB (Embedded C++, vectorized columnar engine) | **Vectorized AAR**: Fleet-wide analytics, heatmaps, and telemetry anomaly detection in < 1 second. |
| **Tactical Context / Graph** | Static JSON (`config/restricted_zones.json`) | Memgraph (`:7687`, C++ property graph, openCypher) + KDG | **Tactical Knowledge Graph**: Dynamic threat zones, target tracking, electronic warfare envelopes. |
| **Orchestration** | Temporal Server (`:7233`) | Temporal Server (`:7233`) + Ephemeral Docker Runner | **Unified Workflow Engine**: Shared or federated Temporal orchestrator for orders and data pipelines. |
| **Multi-Agent AI** | Pydantic-AI (SMEAC Parser & Critic) | Google ADK 2.0 (`DynamicAgentLoop` with 6 dynamic DB tools) | **Dynamic Tool Loop**: Agents can inspect live telemetry and knowledge graphs to suggest SMEAC orders. |
| **Edge Compute** | Raspberry Pi 5 (FastAPI, YOLO-E, MAVSDK, PX4) | MQTT client publishers (`paho-mqtt`) | **Edge Telemetry Publisher**: Pi 5 publishes state and YOLO detections directly to the message bus. |
| **Access Control & Proxy** | Custom JWT Middleware & Proxy | Traefik v3 + Project Membership RBAC | **Unified Tactical Gateway**: Authenticated ingress and reverse proxy across all services. |

---

## 3. End-to-End Integrated Architecture

The combined system bridges tactical edge operations with deep intelligence analytics. The diagram below illustrates how components from both projects interact:

```mermaid
graph TD
    %% Node Declarations
    Commander["Tactical Commander / Analyst"]
    TraefikGate["Traefik v3 Ingress & Reverse Proxy (Ports 80/443/8080)"]
    WebDashboard["ISC Tactical Web Dashboard (Port 8080)"]
    ISCBackend["ISC Backend API (FastAPI :8000)"]
    PMAIngestion["PMA Ingestion Facade (FastAPI :8000)"]
    TemporalCore["Temporal Workflow Engine (Port 7233)"]
    MosquittoBus["Mosquitto MQTT Broker (Port 1883)"]
    DiskBuffer["Crash-Resilient Buffer (/tmp/artemis/buffer)"]
    MinIOLake["MinIO S3 Parquet Lakehouse (Port 9000)"]
    DuckDBEngine["DuckDB Vectorized Analytics Engine"]
    MemgraphDB["Memgraph Tactical Knowledge Graph (Port 7687)"]
    PostgresStore["PostgreSQL 16 Operational & Audit Store"]
    AgentCore["Google ADK Multi-Agent Core (SMEAC & Dynamic Tools)"]
    DronePi5["Swarm Drone Edge Node (Raspberry Pi 5 :8090)"]
    PX4Mav["PX4 Autopilot & MAVSDK"]
    YoloPerception["YOLO-E Computer Vision"]

    %% Connections
    Commander --> TraefikGate
    TraefikGate --> WebDashboard
    TraefikGate --> ISCBackend
    TraefikGate --> PMAIngestion

    WebDashboard --> ISCBackend
    ISCBackend --> TemporalCore
    TemporalCore --> PostgresStore
    TemporalCore --> AgentCore

    AgentCore --> DuckDBEngine
    AgentCore --> MemgraphDB

    DronePi5 --> PX4Mav
    DronePi5 --> YoloPerception
    DronePi5 -->|"Telemetry & Detections (MQTT)"| MosquittoBus

    MosquittoBus --> DiskBuffer
    DiskBuffer -->|"Micro-Batch Flush"| MinIOLake
    DuckDBEngine -->|"Direct S3 Columnar SQL"| MinIOLake

    ISCBackend -->|"Dynamic Geofence & Threat Checks"| MemgraphDB
    PMAIngestion -->|"Target Ingestion & Correlation"| MemgraphDB
    ISCBackend -->|"Dispatch Validated Orders"| DronePi5
```

---

## 4. Key Integration Capabilities & Technical Blueprints

### 4.1 High-Frequency Swarm Telemetry Ingestion (MQTT Bus)

#### Current State in ISC
In `src/edge/api/server.py`, drone telemetry (latitude, longitude, altitude, battery percentage, heading) is maintained in a local Python dictionary `_telemetry_state` and exposed via `GET /telemetry`. The dashboard or backend must periodically poll each drone over HTTP. In a swarm of 20 to 100 drones operating over lossy tactical radios, polling creates severe latency, bandwidth saturation, and connection dropouts.

#### Integrated Blueprint with PMA
Replace edge HTTP polling with push-based MQTT streaming over PMA's **Eclipse Mosquitto** broker:
1. **Topic Hierarchy**:
   ```
   telemetry/swarms/<swarm_id>/<drone_id>/navigation
   telemetry/swarms/<swarm_id>/<drone_id>/battery
   telemetry/swarms/<swarm_id>/<drone_id>/detections
   telemetry/swarms/<swarm_id>/<drone_id>/health
   ```
2. **QoS Protocol**:
   - Navigation and high-frequency IMU telemetry use **QoS 0** (At most once) to prevent edge message queue saturation.
   - High-priority state changes (battery low alert, safety geofence breach, target identification) use **QoS 1** (At least once).
3. **Payload Data Contract**:
   ```json
   {
     "timestamp": "2026-10-24T09:15:30.120Z",
     "swarm_id": "alpha_squadron",
     "drone_id": "uav_04",
     "metric": "navigation",
     "value": {
       "lat": 48.8584,
       "lon": 2.2945,
       "alt_m": 120.5,
       "heading_deg": 184.2,
       "groundspeed_ms": 14.8
     },
     "metadata": {
       "flight_mode": "mission",
       "firmware": "px4_v1.14"
     }
   }
   ```

### 4.2 Edge Computer Vision Sensor Fusion & Target Intelligence

#### Current State in ISC
In `src/edge/vision/inference.py`, the `YoloEInference` engine processes camera frames on the Raspberry Pi 5 to detect target classes (e.g. `vehicle`, `person`, `tank`). Detections are consumed locally by `FlightController` for tracking, but are not persisted or correlated with battlefield command intelligence.

#### Integrated Blueprint with PMA
1. **Detection Stream to MQTT**:
   When YOLO-E detects an object matching the SMEAC target profile with confidence above threshold:
   ```json
   {
     "timestamp": "2026-10-24T09:16:02.450Z",
     "swarm_id": "alpha_squadron",
     "drone_id": "uav_04",
     "metric": "detection",
     "value": {
       "target_class": "armored_vehicle",
       "confidence": 0.89,
       "bbox": [320, 180, 480, 310],
       "estimated_gps": {
         "lat": 48.8591,
         "lon": 2.2960
       }
     },
     "metadata": {
       "mission_id": "smeac_recon_089",
       "snapshot_uri": "s3://telemetry/snapshots/2026/10/24/uav_04_det_1042.jpg"
     }
   }
   ```
2. **Snapshot Storage in MinIO**:
   Low-resolution cropped bounding boxes (target thumbnails) are asynchronously uploaded to MinIO S3 bucket `tactical-snapshots`, providing visual ground-truth evidence for HITL commander validation.
3. **Memgraph Entity Creation**:
   PMA's ingestion pipeline extracts the detection event and creates a `:TargetObservation` node in Memgraph linked to `:UAV` and `:SMEAC_Mission`.

### 4.3 Vectorized After-Action Review (AAR) via DuckDB

#### Capability Overview
Modern military drone doctrine requires comprehensive After-Action Reviews: analyzing drone performance, tracking detection density, assessing airspace deconfliction, and inspecting battery consumption curves.

PMA's native **DuckDB client** queries MinIO Parquet files directly using vectorized SIMD execution without requiring Spark or Trino clusters:
```sql
-- Query: Average battery depletion rate and flight time per drone in mission
SELECT 
    drone_id,
    MIN(CAST(value->>'alt_m' AS DOUBLE)) AS min_altitude,
    MAX(CAST(value->>'alt_m' AS DOUBLE)) AS max_altitude,
    AVG(CAST(value->>'groundspeed_ms' AS DOUBLE)) AS avg_speed,
    MAX(timestamp) - MIN(timestamp) AS mission_duration,
    (MAX(CAST(value->>'battery' AS DOUBLE)) - MIN(CAST(value->>'battery' AS DOUBLE))) AS battery_consumed
FROM 's3://telemetry/swarms/alpha_squadron/**/*.parquet'
WHERE timestamp >= '2026-10-24T08:00:00Z'
GROUP BY drone_id
ORDER BY battery_consumed DESC;
```
This enables the ISC Tactical Dashboard to render instant post-flight analytics, flight playback histograms, and predictive maintenance warnings for UAV motors and batteries.

### 4.4 Dynamic Battlefield Knowledge Graph & Threat-Aware Safety Critic

#### Current State in ISC
In `src/uservice/swarm/operations/swarm_agents.py`, the `GuardianCriticAgent` enforces safety rules using a static JSON file:
```python
# src/uservice/swarm/operations/swarm_agents.py
config_path = os.path.join(base_dir, "config", "restricted_zones.json")
```
This static approach cannot handle dynamic battlefield conditions: mobile enemy air defense units (SAMs), active radar detection domes, changing friendly artillery corridors, or civilian gathering zones.

#### Integrated Blueprint with Memgraph
PMA provides **Memgraph** with high-speed Cypher graph queries and geospatial index support.
1. **Tactical Graph Schema**:
   - Nodes:
     - `(:Swarm {id, callsign, status})`
     - `(:Drone {id, serial_number, battery_level, payload_type})`
     - `(:SMEAC_Order {id, commander_id, status, objective})`
     - `(:ThreatZone {id, type, min_alt, max_alt, threat_level, radius_m, polygon})`
     - `(:RadarStation {id, frequency_band, detection_range_km, azimuth})`
     - `(:ObservedEntity {id, class_name, confidence, first_seen, last_seen})`
   - Relationships:
     - `(:Drone)-[:ASSIGNED_TO]->(:Swarm)`
     - `(:Swarm)-[:EXECUTING]->(:SMEAC_Order)`
     - `(:ThreatZone)-[:OVERLAPS]->(:RestrictedAirspace)`
     - `(:Drone)-[:DETECTED {timestamp, confidence}]->(:ObservedEntity)`
2. **Dynamic Threat Gating in Guardian Critic**:
   Instead of checking a static file, the Guardian Critic executes an openCypher query via PMA's `GraphFacade`:
   ```cypher
   MATCH (t:ThreatZone)
   WHERE t.active = true 
     AND point.distance(point({latitude: $lat, longitude: $lon}), point({latitude: t.lat, longitude: t.lon})) < t.radius_m
   RETURN t.id AS threat_id, t.type AS threat_type, t.threat_level AS threat_level
   ```
   If any threat intersects the proposed flight path, the Guardian Critic immediately flags a violation with exact threat intelligence data.

### 4.5 Intelligence-Driven SMEAC Synthesis (PMA DynamicAgentLoop)

PMA's `DynamicAgentLoop` (`src/domains/ai/operations/dynamic_loop.py`) equips LLM agents with 6 autonomous database tools:
- `execute_project_query`: Runs arbitrary read-only SQL on DuckDB over Parquet telemetry.
- `query_knowledge_graph`: Runs read-only Cypher on Memgraph.
- `discover_workspace_schema`: Inspects available datasets and metadata.
- `find_cross_project_entities`: Correlates entities across projects using fuzzy matching.
- `get_data_lineage`: Inspects source-to-target data dependencies.
- `describe_entity`: Retrieves 1-hop subgraphs for tactical targets.

#### Tactical Workflow
A commander on the ISC Tactical Dashboard can prompt the assistant:
> *"Plan a reconnaissance mission over Sector Delta. Avoid areas where hostile mobile radar was detected in the last 24 hours, and deploy drones with at least 80% battery capacity."*

1. **Step 1 (Graph Query)**: The agent queries Memgraph for active hostile radar locations and their detection cones in Sector Delta.
2. **Step 2 (Lakehouse Query)**: The agent runs DuckDB SQL over the latest telemetry to identify UAVs in the fleet currently sitting at $\ge 80\%$ battery.
3. **Step 3 (Plan Synthesis)**: The agent constructs a draft SMEAC order with a deconflicted flight path around the radar domes.
4. **Step 4 (HITL Approval Gate)**: The drafted order is submitted directly to ISC's HITL approval screen for human confirmation before launch.

---

## 5. Comprehensive Pros & Cons Analysis of Integration

Evaluating the integration of **Poor-Man's Artemis.IA** into **Intent-Swarm-Commander** requires weighing the significant operational and architectural advantages against the added infrastructure and tactical networking complexities.

### 5.1 The Pros (Strategic & Technical Advantages)

#### 1. Architectural Alignment & Zero Cognitive Friction
* **Shared `uservice-template` DNA**: Both projects follow identical Domain-Driven Design (DDD) subpackage structures (`api/`, `facade/`, `models/`, `operations/`), clean architecture boundaries, Pydantic type validation, and asynchronous Temporal workflows.
* **Unified Development Velocity**: Engineers familiar with ISC can inspect, maintain, and extend PMA domains (`ingestion`, `analytics`, `graph`, `discovery`, `ai`) without learning new idioms or conventions.

#### 2. Resolving the Swarm Telemetry Scalability Bottleneck
* **Elimination of HTTP Polling**: Replacing ISC's current `GET :8090/telemetry` polling pattern with **Eclipse Mosquitto MQTT** (`:1883`) allows a single command node to ingest 1,000+ telemetry packets per second with sub-5ms latency and under 20 MB of broker RAM.
* **Decoupled Crash-Resilient Ingestion**: Edge drones stream events to Mosquitto, which appends to a local POSIX disk buffer before micro-batch compaction into Apache Arrow / Parquet. The central database is protected against write spikes and connection flooding.

#### 3. Sovereign, Low-Footprint Lakehouse (Zero JVM Overhead)
* **Under 12 GB RAM Footprint**: Unlike traditional big data stacks (Apache Kafka, Hadoop HDFS, Spark, Neo4j, Trino) that require 32–64+ GB of RAM just for JVM runtimes, PMA relies entirely on native C/C++ (Mosquitto, DuckDB, Memgraph, Redis, Postgres) and Go (MinIO, Traefik).
* **Forward-Deployable**: The integrated stack can operate on a single ruggedized edge server, tactical vehicle computer, or expeditionary Command Post (FOB) without dedicated cloud infrastructure.

#### 4. Instant Vectorized After-Action Review (AAR) & Fleet Analytics
* **Sub-Second Columnar SQL with DuckDB**: Flight controllers and commanders can query months of fleet telemetry directly from MinIO Parquet files (`s3://telemetry/**/*.parquet`) without importing data into a relational database.
* **Predictive Fleet Maintenance**: Enables automated detection of battery degradation, motor vibration anomalies, radio signal dead zones, and formation drift across dozens of UAVs simultaneously.

#### 5. Dynamic Tactical Situational Awareness (Memgraph Graph Engine)
* **From Static JSON to Dynamic Threat Graph**: Replaces ISC's hardcoded `config/restricted_zones.json` with a live property graph in Memgraph.
* **Multi-Hop Threat Interception**: The `GuardianCriticAgent` can compute real-time spatial intercepts against dynamic enemy radar cones, mobile surface-to-air missile (SAM) envelopes, electronic warfare jammer bubbles, and friendly artillery corridors via openCypher.

#### 6. End-to-End Target Lineage & Sensor Fusion
* **YOLO-E Detection Archival**: Edge vision detections (bounding boxes, confidence, class, estimated GPS) are ingested, cataloged, and paired with thumbnail image snapshots stored in MinIO.
* **Knowledge Discovery Graph (KDG) Correlation**: Detections are linked to known adversary assets using entity resolution (`Rapidfuzz` + DSU), providing historical tracking of enemy equipment across multiple missions.

#### 7. Intelligence-Driven SMEAC Synthesis
* **Dynamic Multi-Tool AI Agent**: Leverages PMA's `DynamicAgentLoop` (with 6 read-only database tools) to answer high-level commander tactical queries and autonomously generate drafted SMEAC mission orders grounded in real operational data.

---

### 5.2 The Cons (Technical Challenges & Trade-offs)

#### 1. Increased Infrastructure & Container Footprint
* **Container Expansion**: Adds 7 infrastructure services (Traefik, Mosquitto, MinIO, Memgraph, Redis, Temporal-UI, and the Docker pipeline runner) to ISC's existing 6 containers.
* **Volume & Credential Management**: Requires managing multiple persistent storage volumes (`minio_data`, `memgraph_data`, `mosquitto_data`, `redis_data`) and securing service-to-service secrets across containers.

#### 2. Tactical Network & Comms Vulnerability (DDIL / EW Environments)
* **Reliance on Ingress Connectivity**: MQTT connections assume continuous or intermittent IP reachability between drones and the command post. In Contested / Denied / Degraded / Intermittent / Limited (DDIL) or active Electronic Warfare (EW) jamming environments, drones cannot stream live telemetry.
* **Requirement for Edge Buffering**: Edge drones (Raspberry Pi 5) must implement local persistent SQLite or disk-spool buffering to cache telemetry during radio blackouts and replay it upon reconnect.

#### 3. Cloud API Dependency for Complex AI Reasoning
* **Google AI Studio Reliance**: PMA offloads multi-agent token generation to `gemini-2.5-flash-lite` via Google AI Studio to preserve local CPU/RAM.
* **Sovereignty & Air-Gap Constraint**: In fully air-gapped or classified operations without internet/satellite backhaul, cloud LLM calls will fail fast (`ServiceUnavailableError`). To operate air-gapped, ISC must either fall back to deterministic planning or host a local quantized model (e.g. Llama-3 / Gemma via Ollama or vLLM), which will increase RAM consumption by 8–16 GB.

#### 4. Cross-Repository Schema Governance
* **Coupling of Data Contracts**: Changes to ISC edge telemetry formats, YOLO-E classes, or SMEAC command parameters require synchronized updates to PMA's Arrow schemas, DuckDB SQL views, and Memgraph graph models.
* **Version Drift**: Without unified CI/CD integration, version drift between ISC and PMA could lead to silent ingestion failures or unparsed telemetry attributes.

#### 5. Local Development Resource Competition
* **Simultaneous Simulation Load**: Running PX4 Autopilot, ROS 2 bridge, Gazebo 3D simulation with GUI rendering alongside the full PMA big data stack on a standard developer laptop will compete heavily for CPU cores, disk I/O, and RAM. Developers must run Gazebo in headless mode or utilize a dedicated workstation/VM.

---

### 5.3 Comparative Decision Matrix

| Dimension | Standalone ISC (Current MVP) | Integrated ISC + Poor-Man's Artemis.IA |
| :--- | :--- | :--- |
| **Telemetry Scalability** | Low (HTTP polling breaks at > 5 drones) | **Very High** (MQTT handles 1,000+ evt/s, 100+ drones) |
| **Data Retention** | Ephemeral (in-memory state, lost on restart) | **Permanent** (Columnar Parquet Lakehouse in MinIO) |
| **After-Action Analytics**| None (basic Postgres queries only) | **Instant Vectorized SQL** (DuckDB direct Parquet queries) |
| **Airspace Safety Model** | Static JSON (`restricted_zones.json`) | **Dynamic Threat Graph** (Memgraph openCypher spatial queries) |
| **Edge Vision Detections**| Discarded after local tracking | **Persisted & Correlated** (MinIO snapshots + KDG entity linking) |
| **Operational Planning** | Manual text entry of SMEAC orders | **AI-Assisted** (DynamicAgentLoop synthesizes drafted orders) |
| **Idle Memory Footprint**| Low (~1.5 GB RAM) | **Medium (~3.5–4.5 GB RAM, zero JVM)** |
| **Container Count** | 6 containers | 13 containers |
| **Air-Gap Readiness** | High (fully local) | Medium (requires local LLM fallback for AI queries) |
| **Engineering Effort** | Baseline | Moderate (MQTT client on edge + Memgraph client in critic) |

---

## 6. Round-Trip Time (RTT) Analysis & Physical Placement Strategy

To guarantee operational flight safety, deterministic mission orchestration, and responsive command-and-control, the communication links and Round-Trip Times (RTT) between components must be rigorously partitioned.

### 6.1 Inter-Component Communication & Latency Budget Matrix

The following table details the protocol, payload characteristics, maximum tolerable latency (SLA), and expected real-world RTT across different network environments:

| Path / Inter-Component Link | Protocol | Typical Payload | Max Allowable SLA | Local LAN / Host RTT | Tactical MANET RTT | Satcom / Cloud WAN RTT | Quality Impact of High Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PX4 Autopilot $\leftrightarrow$ MAVSDK / FlightController** | MAVLink (UART / UDP loopback) | 28–256 B @ 10–50 Hz | **< 10 ms** (Hard Real-Time) | `< 2 ms` | *Not Allowed* | *Not Allowed* | **Critical**: High latency triggers autopilot failsafe (RTL or Emergency Land). Must remain on-drone. |
| **YOLO-E $\leftrightarrow$ Local FlightController** | In-Process Python / IPC | Tensor Bounding Boxes @ 30 FPS | **< 35 ms** (Real-Time) | `10–25 ms` | *Not Allowed* | *Not Allowed* | **High**: Loss of visual target tracking lock; missed target intercepts. Must remain on-drone. |
| **Edge Drone (Pi 5) $\rightarrow$ Mosquitto MQTT** | MQTT QoS 0 / 1 (TCP port 1883) | 500 B JSON telemetry @ 5–20 Hz | **< 100 ms** (Soft Real-Time) | `2–5 ms` | `10–25 ms` | `250–800 ms` (+ packet loss) | **High**: Dashboard telemetry lag; jumpy map icons; delayed target alerts. Requires local MANET. |
| **ISC Backend $\leftrightarrow$ Temporal Engine** | gRPC (HTTP/2 port 7233) | 2–15 KB workflow states & activities | **< 20 ms** (Low Latency) | `< 2 ms` | `15–40 ms` | `120–450 ms` | **Severe**: High RTT causes activity heartbeat timeouts, false workflow retries, and task queue starvation. |
| **Guardian Critic $\leftrightarrow$ Memgraph Bolt** | openCypher over Bolt (TCP port 7687) | 1–5 KB Cypher spatial queries | **< 50 ms** (Interactive) | `1–4 ms` | `12–30 ms` | `150–500 ms` | **Moderate**: Slows down SMEAC validation and order approval gating; frustrates commander. |
| **Dashboard $\leftrightarrow$ ISC Backend** | HTTP REST & WebSocket (port 8000/8080) | 1–20 KB map telemetry & HITL state | **< 100 ms** (Interactive UI) | `< 5 ms` | `15–30 ms` | `120–350 ms` | **Low-Medium**: UI responsiveness and map marker fluidity. |
| **DuckDB Engine $\leftrightarrow$ MinIO Parquet** | S3 API (HTTP port 9000) | Multi-MB columnar chunk reads | **< 2,000 ms** (Batch OLAP) | `5–25 ms` (300+ MB/s) | `200–1,500 ms` | `3,000–15,000 ms` | **High for AAR**: Remote S3 reads over tactical radio throttle vectorized query performance by 95%. |
| **DynamicAgentLoop $\leftrightarrow$ Google AI Studio** | HTTPS REST (Cloud API) | 5–50 KB prompt / function calling | **< 3,000 ms** (Cognitive Planning)| `800–1,500 ms` | `1,200–2,500 ms` | `1,500–4,000 ms` | **Low**: Planning is an asynchronous pre-mission task. Acceptable over satellite backhaul. |

---

### 6.2 The Three Physical Deployment Tiers

Physical placement must align with computational limits, RF constraints, and environmental hazards:

```
+-----------------------------------------------------------------------------------------+
| TIER 1: AERIAL SWARM EDGE (Onboard UAV - Raspberry Pi 5 & PX4)                          |
| - Execution: PX4 Autopilot, MAVSDK, Camera, YOLO-E Inference, Local SQLite Disk Spool   |
| - Constraints: Battery power (15-40 min), strict SWaP-C, high RF jamming risk           |
+-----------------------------------------------------------------------------------------+
                                         |
                       Tactical MANET / Mesh RF Link
                       (Silvus / TrellisWare / Wi-Fi 6)
                       Latency: 5-20 ms | Throughput: 5-30 Mbps
                                         v
+-----------------------------------------------------------------------------------------+
| TIER 2: TACTICAL EDGE / FORWARD OPERATING BASE (Rugged Vehicle Server / TOC Laptop)     |
| - Execution: Mosquitto Broker, ISC Backend, Temporal Engine, Local Memgraph Threat DB,  |
|              Postgres DB, Tactical Web Dashboard (:8080)                                |
| - Constraints: 16-32 GB RAM, 8 vCPUs, generator/battery powered, intermittent internet |
+-----------------------------------------------------------------------------------------+
                                         |
                       Long-Haul Backhaul / Satellite Link
                       (Starlink / SATCOM / 5G / Fiber)
                       Latency: 80-600 ms | Throughput: 2-50 Mbps (Degraded/DDIL)
                                         v
+-----------------------------------------------------------------------------------------+
| TIER 3: STRATEGIC HEADQUARTERS / CENTRAL CLOUD (Regional Command Data Center)           |
| - Execution: Global MinIO Parquet Lakehouse, Fleet-Wide DuckDB AAR Analytics,           |
|              Universal KDG Knowledge Graph, Google AI Studio / Gemini API Link          |
| - Constraints: Enterprise datacenter, high availability, cross-theater aggregation      |
+-----------------------------------------------------------------------------------------+
```

---

## 7. Deployment Topologies for Maximum Operational Quality

To achieve the best balance of **sub-millisecond flight control**, **low-latency telemetry**, and **deep strategic analytics**, three deployment topologies are evaluated.

### 7.1 Option A: Monolithic Tactical Edge ("TOC All-in-One")
* **Concept**: The entire integrated stack (ISC + all 8 PMA services) is deployed as Docker containers directly onto a single ruggedized server (e.g. 32 GB RAM, 8–16 core CPU) located inside the mobile Command Vehicle or Tactical Operations Center (TOC).
* **Communication Geometry**:
  - Drones stream directly to the TOC server over line-of-sight (LOS) tactical MANET (Silvus / TrellisWare).
  - RTT between Drones and Mosquitto: **5–15 ms**.
  - RTT between ISC Backend, Temporal, Memgraph, and DuckDB: **< 2 ms** (IPC/local loopback).
* **Quality Profile**:
  - **Flight Safety & Control**: **10/10** (Zero external network dependencies).
  - **Telemetry Resolution**: **10/10** (Full 20 Hz telemetry streaming without data drops).
  - **AAR Query Speed**: **10/10** (Local disk NVMe S3 access executes in < 0.2s).
  - **DDIL / Jamming Resilience**: **10/10** (Functions 100% offline).
  - **AI Reasoning**: **6/10** (Requires satellite backhaul for Google AI Studio; if jammed, must fall back to local rule-based planning).
* **Best Suited For**: Expeditionary, highly contested operations where cloud access is strictly forbidden or permanently jammed.

---

### 7.2 Option B: Tiered Split Edge-Cloud ("Tactical C2 Edge + Strategic Cloud Lakehouse") — RECOMMENDED FOR BEST OVERALL QUALITY

```mermaid
flowchart TD
    %% Node Declarations
    subgraph Tier1 ["Tier 1: Aerial Swarm Edge (Onboard UAVs)"]
        UAV1["UAV Alpha-1 (Pi 5: PX4 + YOLO-E + Spool Buffer)"]
        UAV2["UAV Alpha-2 (Pi 5: PX4 + YOLO-E + Spool Buffer)"]
    end

    subgraph Tier2 ["Tier 2: Tactical Edge / TOC Vehicle (Sub-15ms RTT)"]
        TOC_Mosquitto["TOC Mosquitto MQTT Broker (:1883)"]
        TOC_Buffer["Local Ingestion Disk Buffer"]
        TOC_ISC["ISC Backend & Safety Critic (:8000)"]
        TOC_Temporal["Temporal Workflow Engine (:7233)"]
        TOC_Memgraph["Local Memgraph (Active Threats & Airspace)"]
        TOC_Dashboard["Tactical Dashboard UI (:8080)"]
    end

    subgraph Tier3 ["Tier 3: Strategic Cloud / HQ (High-Power Compute)"]
        HQ_MinIO["Global MinIO S3 Parquet Lakehouse"]
        HQ_DuckDB["DuckDB Multi-Fleet AAR Engine"]
        HQ_KDG["Universal Knowledge Discovery Graph (KDG)"]
        HQ_ADK["Google ADK Multi-Agent Loop (Gemini API)"]
    end

    %% Connections
    UAV1 -->|"Telemetry & Targets (5-15ms MANET)"| TOC_Mosquitto
    UAV2 -->|"Telemetry & Targets (5-15ms MANET)"| TOC_Mosquitto
    TOC_Mosquitto --> TOC_Buffer
    TOC_Buffer --> TOC_ISC
    TOC_ISC <-->|"Fast State (< 2ms)"| TOC_Temporal
    TOC_ISC <-->|"Threat Gating (< 3ms)"| TOC_Memgraph
    TOC_Dashboard <--> TOC_ISC

    %% Asynchronous Replication to HQ
    TOC_Buffer -.->|"Asynchronous Micro-Batch Sync (When Link Active)"| HQ_MinIO
    TOC_Memgraph -.->|"Threat Intelligence Replication"| HQ_KDG
    HQ_MinIO --> HQ_DuckDB
    HQ_ADK <--> HQ_DuckDB
    HQ_ADK <--> HQ_KDG
    HQ_ADK -.->|"Drafted SMEAC Orders (Satcom)"| TOC_ISC
```

#### Why Option B Delivers the Highest Quality:
1. **Low-Latency Isolation**: The mission-critical loop (UAV flight commands $\leftrightarrow$ MAVSDK, live telemetry $\leftrightarrow$ Mosquitto, safety gating $\leftrightarrow$ Memgraph) runs exclusively on the Tactical Edge at **sub-15ms latency**. Tactical safety is never degraded by cloud latency or satellite dropout.
2. **Bandwidth-Efficient Asynchronous Sync**: High-frequency raw sensor data is ingested and buffered locally at the TOC. When satellite or LTE backhaul is available, compacted Apache Arrow/Parquet batches sync to the Central Cloud MinIO lakehouse asynchronously in the background.
3. **Cross-Fleet Strategic Intelligence**: Strategic commanders at HQ use DuckDB and Memgraph KDG to query historical flight logs across all squadrons worldwide, discovering recurring electronic warfare zones, vehicle patterns, and fleet health degradation.
4. **Resilient AI Planning**: Complex SMEAC order synthesis using the 6-tool `DynamicAgentLoop` and Google AI Studio is computed in the Cloud where bandwidth is plentiful, and the resulting structured SMEAC plan is pushed down to the TOC for HITL confirmation.

---

### 7.3 Option C: Airborne Relay / Hierarchical Swarm Gateway
* **Concept**: A high-end endurance UAV (e.g. fixed-wing relay drone equipped with an NVIDIA Jetson Orin or dual-radio Pi 5) acts as an airborne edge gateway flying above the swarm.
* **Communication Geometry**:
  - Recon drones stream to the Relay Drone over 5 GHz short-range Wi-Fi mesh (**2–5 ms RTT**).
  - The Relay Drone aggregates telemetry, applies local target filtering, and relays compressed data to the ground TOC over a long-range directional radio (C-Band / COFDM).
* **Quality Profile**:
  - **Operating Range**: Triples the operational radius of low-power multirotor drones.
  - **Complexity**: High (requires maintaining an airborne relay node and aerial link routing).
* **Best Suited For**: Beyond Visual Line of Sight (BVLOS) operations, urban terrain with severe building shadowing, or mountainous valleys.

---

### 7.4 Topology Evaluation & Recommendation Matrix

| Architectural Metric | Option A: Monolithic Tactical Edge | Option B: Tiered Split Edge-Cloud (Recommended) | Option C: Airborne Relay Gateway |
| :--- | :--- | :--- | :--- |
| **Flight Control RTT** | **< 2 ms** (Direct local) | **< 2 ms** (Direct local) | **< 2 ms** (Direct local) |
| **Telemetry Ingestion RTT** | **5–15 ms** (Tactical MANET) | **5–15 ms** (Tactical MANET) | **2–5 ms** (In-flight mesh) |
| **Dynamic Threat Gating RTT** | **< 5 ms** (Local Memgraph) | **< 5 ms** (Local Memgraph) | **15–30 ms** (Relayed to ground) |
| **After-Action Review Speed** | Fast (< 0.5s local DuckDB) | **Fastest** (HQ Cloud multi-core DuckDB) | Moderate (Dependent on ground sync) |
| **Tolerance to Comms Jamming** | **100% Survivable** (Fully local) | **100% Operational** (Queues sync for later) | High (Mesh survives LOS ground drops) |
| **Strategic Cross-Mission Intel**| Low (Isolated to local vehicle) | **Maximum** (Centralized KDG & Lakehouse) | Moderate |
| **Hardware Footprint at Frontline**| 1 Rugged Server (32 GB RAM) | 1 Rugged Laptop/Server (16 GB RAM) | 1 Rugged Server + 1 Relay UAV |
| **Deployment Complexity** | Low (Single Docker Compose) | Moderate (Split sync + secure tunnel) | High (Airborne mesh management) |

---

## 8. Concrete Configuration for Option B (Recommended Deployment)

To configure **Option B** using Docker Compose across the Tactical Edge and Central Cloud:

### 8.1 Tactical Edge (`docker-compose.tactical.yml`)
Runs at the Forward Operating Base / Command Vehicle:
```yaml
services:
  # 1. High-throughput edge ingestion
  mosquitto:
    image: eclipse-mosquitto:2
    ports: ["1883:1883"]
    volumes: ["./config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro"]

  # 2. Tactical threat awareness
  memgraph:
    image: memgraph/memgraph:latest
    ports: ["7687:7687"]

  # 3. Mission state machine
  temporal:
    image: temporalio/auto-setup:1.24
    ports: ["7233:7233"]
    environment:
      - POSTGRES_SEEDS=postgres
    depends_on: [postgres]

  # 4. Relational & operational metadata
  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      - POSTGRES_USER=isc_user
      - POSTGRES_PASSWORD=isc_pass
      - POSTGRES_DB=isc_db

  # 5. Intent-Swarm-Commander Backend & Safety Critic
  isc_backend:
    build: { context: ., dockerfile: Dockerfile.backend }
    ports: ["8000:8000"]
    environment:
      - MQTT_HOST=mosquitto
      - MEMGRAPH_URI=bolt://memgraph:7687
      - TEMPORAL_URL=temporal:7233
      - DATABASE_URL=postgresql+asyncpg://isc_user:isc_pass@postgres:5432/isc_db

  # 6. Tactical Map & HITL Dashboard
  dashboard:
    image: python:3.11-alpine
    command: python3 -m http.server 8080 -d /app/src/dashboard
    ports: ["8080:8080"]
```

### 8.2 Strategic HQ Cloud (`docker-compose.hq.yml`)
Runs in the Regional Command Datacenter / Cloud:
```yaml
services:
  # 1. Centralized S3 Lakehouse
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]

  # 2. Universal Knowledge Discovery Graph (KDG)
  memgraph_hq:
    image: memgraph/memgraph:latest
    ports: ["7688:7687"]

  # 3. Redis Semantic Cache for AI Agents
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  # 4. PMA AI & Strategic Analytics Service
  artemis_api:
    image: artemis-platform:latest
    ports: ["8001:8000"]
    environment:
      - GOOGLE_AI_STUDIO_API_KEY=${GOOGLE_AI_STUDIO_API_KEY}
      - MINIO_ENDPOINT=minio:9000
      - MEMGRAPH_PORT=7688
```

---

## 9. Infrastructure Coexistence & Docker Port Mapping

Both systems use Docker Compose for local execution. Running both simultaneously on a single host requires clean network bridging and non-conflicting port allocation.

### 9.1 Port Allocation Matrix

| Service | ISC Standalone Port | PMA Standalone Port | Coexistence Strategy |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | `5432` | `5433` (mapped from 5432) | Keep separated: ISC uses `5432`, PMA uses `5433` to prevent database schema contamination. |
| **Temporal gRPC** | `7233` | `7233` | **Option A (Recommended)**: ISC points to PMA's Temporal service with separate task queues (`ISC_TASK_QUEUE` vs `PMA_TASK_QUEUE`).<br>**Option B**: Map PMA Temporal to `7234`. |
| **Temporal UI** | None | `8233` (host) | Accessible to monitor both ISC and PMA workflows simultaneously on `http://localhost:8233`. |
| **MQTT Broker** | None | `1883` | Dedicated to PMA; ISC edge drones publish to `localhost:1883`. |
| **MinIO S3 API** | None | `9000` | S3 API accessible by ISC backend and DuckDB. |
| **MinIO Web Console**| None | `9001` | S3 lakehouse browser accessible on `http://localhost:9001`. |
| **Memgraph Bolt** | None | `7687` | Memgraph Bolt port accessible by ISC Guardian Critic via `neo4j` or `gqlalchemy`. |
| **Redis Cache** | None | `6379` | Dedicated to PMA semantic caching and rate limiting. |
| **Traefik Gateway** | None | `80`, `443`, `8088` | Traefik proxies ISC dashboard (`:8080`), ISC backend (`:8000`), and PMA APIs. |
| **ISC Edge Node** | `8090` | None | Dedicated to ISC edge drone server. |
| **Dashboard UI** | `8080` | None | Host on `8080` or route via Traefik host routing (`c2.artemis.local`). |

### 9.2 Network Bridge Configuration

To allow ISC backend and edge containers to reach PMA services without host networking hacks, create a shared Docker bridge network in `docker-compose.yml`:

```yaml
networks:
  c2-shared-net:
    name: c2-shared-net
    driver: bridge
```

In `Intent-Swarm-Commander/docker-compose.yml`:
```yaml
services:
  backend:
    networks:
      - c2-shared-net
    environment:
      - MQTT_HOST=artemis-mosquitto
      - MQTT_PORT=1883
      - MEMGRAPH_URI=bolt://artemis-memgraph:7687
      - MINIO_ENDPOINT=artemis-minio:9000
```

---

## 10. Implementation Roadmap

The integration can be executed incrementally across four modular phases without breaking any existing ISC MVP features:

### Phase 1: Swarm Telemetry Streamer & Lakehouse Archival
* **Objective**: Stream live drone telemetry to Mosquitto and persist it into MinIO Parquet partitions.
* **Tasks**:
  1. Add `paho-mqtt` dependency to `src/edge/` and `src/uservice/`.
  2. Implement an asynchronous MQTT publisher inside `src/edge/api/server.py` in the `telemetry_loop()` function.
  3. Configure PMA's ingestion pipeline to route `telemetry/swarms/#` topics into partitioned S3 Parquet tables.
  4. Verify data arrival in MinIO using DuckDB CLI.

### Phase 2: Dynamic Threat Intelligence & Memgraph Safety Gating
* **Objective**: Replace static geofencing in `GuardianCriticAgent` with dynamic openCypher queries against Memgraph.
* **Tasks**:
  1. Add `neo4j` driver to `src/uservice/swarm/operations/swarm_agents.py`.
  2. Implement `query_threat_zones(lat, lon, radius)` calling Memgraph.
  3. Build an initial seed script to populate battlefield threats (SAM batteries, radar zones, temporary flight restrictions) into Memgraph.
  4. Update `check_geofencing()` to perform spatial distance queries against Memgraph threat nodes.

### Phase 3: Sensor Fusion & Perception Logging
* **Objective**: Ingest YOLO-E detections and snapshots into the Big Data Lakehouse and Knowledge Discovery Graph.
* **Tasks**:
  1. In `src/edge/vision/inference.py`, dispatch detection payloads to `telemetry/swarms/<swarm_id>/<drone_id>/detections`.
  2. Implement image thumbnail upload to MinIO bucket `tactical-snapshots`.
  3. In PMA, configure entity linking to associate target observations with active SMEAC missions in Memgraph.

### Phase 4: Tactical AI Copilot & After-Action Analytics
* **Objective**: Expose DuckDB analytics and PMA's multi-agent dynamic tools to the Tactical Dashboard.
* **Tasks**:
  1. Add an AAR Analytics tab in `src/dashboard/index.html` querying DuckDB via PMA's `/api/v1/analytics/query`.
  2. Connect the SMEAC order generator to PMA's `DynamicAgentLoop` for automated reconnaissance mission drafting.
  3. Integrate Temporal UI (`:8233`) into the Commander dashboard for end-to-end mission workflow tracing.

---

## 11. Risk Analysis & Mitigation

| Identified Risk | Severity | Technical Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Tactical Link Disconnection (DDIL / Jamming)** | High | Edge drones cannot reach central Mosquitto broker during EW interference. | Drones utilize local SQLite/disk buffering (`/tmp/edge_buffer.jsonl`) on the Pi 5; automatically flush queued telemetry via bulk replay once MQTT connection is restored. |
| **Port Conflicts on Host Machine** | Medium | Docker compose fail on startup if both projects use port 5432 or 7233. | Use non-overlapping port mappings (`5433` for PMA Postgres, `8233` for Temporal UI) and use Docker internal DNS names across a shared bridge network (`c2-shared-net`). |
| **Resource Contention on Local VM** | Low | Simultaneous Gazebo simulation, ROS 2, and Big Data stack exceeding VM memory. | PMA's Zero-JVM architecture consumes < 12 GB RAM idle. If running Gazebo on the same host, allocate swap or offload Gazebo rendering to headless mode (`PX4_GZ_STANDALONE=1`). |
| **Data Leaks Across Mission Boundaries** | Medium | Multi-swarm telemetry mixed together in shared storage. | Enforce PMA's Project RBAC and Medallion architecture: each swarm or operational theater is assigned an isolated `project_id` with strict S3 prefix confinement. |

---

## 12. Strategic Recommendation & Decision Summary

The combination of **Intent-Swarm-Commander** and **Poor-Man's Artemis.IA** creates a synergistic military-grade drone C2 and tactical intelligence platform. 

- **ISC** provides the physical actuation, ROS 2 / PX4 flight control, SMEAC intent parsing, and edge perception.
- **PMA** provides the enterprise data backbone: resilient high-throughput telemetry buses, zero-JVM lakehouse storage, sub-second columnar fleet analytics, and dynamic graph-based threat awareness.

It is recommended to proceed with **Phase 1 (MQTT Telemetry Streaming)** and **Phase 2 (Memgraph Dynamic Geofencing)** as the immediate next steps to replace ISC's mock and polling bottlenecks with production-grade data pipelines.
