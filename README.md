# Telecom Agentic Orchestration Engine

> **Cache-First · Data-Sovereign · Cloud-Reasoned · TMF-Standards Compliant**

A multi-stage asynchronous orchestration engine for telecom service provisioning. Accepts TMF640/TMF641 JSON payloads and unstructured natural language — masking sensitive identifiers before cloud AI, caching successful orchestrations for sub-5ms future hits, and emitting TMF641-compliant lifecycle notifications.

---

## Quick Reference

| What | Where | Port |
|------|-------|------|
| **Python PoC** (running) | `poc/server_live.py` | `172.16.1.2:8090` |
| **Java PoC** (running) | `java-poc/` (Spring Boot) | `172.16.1.2:8091` |
| Web UI (both) | `/` on each server | Trace viewer with 6 color themes |
| Health check | `GET /health` | `{"status":"ok"}` |

---

## Directory Structure

```
agentic-orchestrator/
│
├── README.md                              ← THIS FILE
├── STATUS.md                              ← Current project status snapshot
├── architecture-diagram.html              ← Standalone SVG architecture diagram
│
├── poc/                                   ← ★ PYTHON PoC (Production) — PORT 8090
│   ├── server_live.py                     # Main server — 1,848 lines
│   ├── server.py                          # Original stub server (reference)
│   ├── static/index.html                  # Single-file Web UI — 727 lines
│   ├── DESIGN.md                          # PoC design document
│   ├── SYSTEM_ARCHITECTURE.md             # PoC architecture document
│   ├── BUILD_PROMPT.md                    # Original build instructions
│   ├── SOLUTION_PUBLIC_ACCESS.md          # Public access / tunnel config
│   ├── demo.html                          # Client-side browser demo (offline)
│   ├── nginx-poc.conf                     # Nginx reverse proxy config
│   ├── test_activate.py                   # Test harness
│   └── cache_store/                       # diskcache SQLite data (runtime)
│
├── java-poc/                              ← ★ JAVA PoC (Independent) — PORT 8091
│   ├── README.md                          # Java PoC readme
│   ├── pom.xml                            # Maven build (Spring Boot 3.3, Java 21)
│   └── src/main/java/com/telecom/orchestrator/
│       ├── Application.java               # Entry point
│       ├── api/OrchestratorController     # 8 REST endpoints
│       ├── config/OrchestratorConfig      # Spring bean wiring
│       ├── models/                        # ProcessRequest, Response, TraceStep, PatternNode
│       ├── pipeline/PipelineEngine        # 12-stage async pipeline
│       ├── security/DataMasker            # MSISDN/IP regex tokenization
│       ├── store/                         # KnowledgeBase, PatternStore, ServiceModelStore, SubscriberLock
│       ├── notification/LifecycleNotifier # TMF641 milestone + state change events
│       └── pipeline/TraceStepEmitter      # Callback interface for decoupled step emission
│
├── knowledge-base/                        ← DOMAIN KNOWLEDGE (Single Source of Truth)
│   ├── ontologies/core-ontology.md        # Entity hierarchy, lifecycles, service/resource taxonomy
│   ├── reference/
│   │   ├── standards-index.md             # TM Forum, MEF, ETSI, IETF, 3GPP pointers
│   │   ├── tmf-notification-schemas.md    # TMF641 v4.1.0 event schemas
│   │   ├── implementation-guide.md        # 7-phase build plan for VPS deployment
│   │   ├── orchestration-brain-design.md  # 6-stage brain: PARSE→MATCH→REASON→PLAN→DELEGATE→VERIFY
│   │   └── solution-design-crm-integration.md  # CRM architecture, PostgreSQL schema
│   └── system-docs/                       # System documentation
│       ├── architecture/blueprint.md      # Component diagrams, sequence diagrams, data flow
│       ├── api/api-spec.md                # API reference
│       ├── components/
│       │   ├── backend-components.md      # Detailed backend component specification
│       │   └── frontend-components.md     # Detailed frontend component specification
│       └── solution-design/solution-design.md  # Solution design document
│
├── documentation/                         ← PROJECT DOCUMENTATION
│   ├── README.md                          # Documentation index
│   ├── pattern-store-examples.md          # Live examples of learned patterns
│   ├── build-prompts/                     # Agent build instructions
│   │   ├── PoC-prescriptive-build-prompt.md   # Exact code, paths, CSS — reproduces PoC line-for-line
│   │   └── PoC-behavioral-specification.md    # Generic behavioral spec — implementation-agnostic
│   ├── end-state/                         # Target PRODUCTION architecture (NOT built yet)
│   │   ├── architectural-blueprint.md     # Full topology, 6 sequence diagrams, deployment arch
│   │   ├── api-specification.md           # 30+ endpoints (TMF622/641/640/638/639)
│   │   ├── component-specification.md     # 47-file modular src/ tree, 35+ component specs
│   │   ├── solution-design.md             # Design philosophy, segment×SLA reasoning, trade-offs
│   │   └── component-diagram.md           # Standalone ~70-node Mermaid diagram
│   └── diagrams/
│       └── architecture-component-diagram.html  # Browser-renderable SVG diagram
│
├── requirements/
│   └── systemReqs.md                      # 5 TPS throughput, Phase A-D lifecycle, security reqs
│
└── .hermes/
    └── plans/2026-06-22_160000-telecom-orchestrator-build.md  # 18-task build plan
```

---

## PoC vs. End-State: What's the Difference?

### Proof of Concept (PoC) — BUILT & RUNNING

The PoC demonstrates the core pipeline concept with real AI reasoning and caching. It is two independent implementations (Python and Java) of the same architecture.

| Aspect | PoC Implementation |
|--------|-------------------|
| **Scope** | Mobile voice, L3VPN, SD-WAN, broadband (4 service types) |
| **Pipeline** | 12-stage async (foreground + background) |
| **Storage** | diskcache SQLite (Python) / H2 embedded (Java) |
| **Queue** | ThreadPoolExecutor (in-process) |
| **LLM** | Deepseek v4 via `hermes chat` CLI |
| **MCP/Devices** | Stubbed — logs dispatch, no real provisioning |
| **CRM** | TMF640/TMF641 only — no TMF622 decomposition |
| **Frontend** | Single-file HTML + vanilla JS (727 lines) |
| **Security** | Data masking + blocked keyword validation |
| **Patterns** | RDF-inspired triples, Jaccard matching, confidence lifecycle |

### End-State — DESIGNED, NOT BUILT

The end-state documentation in `documentation/end-state/` describes the full production architecture. Nothing in that folder has been implemented yet.

| Aspect | End-State Target |
|--------|-----------------|
| **Scope** | 7 service domains including Cloud Connect, Security, Transport |
| **Pipeline** | Full 14-stage with CRM callback |
| **Storage** | PostgreSQL 16 + Redis 7 |
| **Queue** | RabbitMQ (prefetch=1, fair dispatch) |
| **MCP/Devices** | Real provisioning via NetBox, Ansible, Cisco NSO, OSM |
| **CRM** | Full TMF622 → TMF641 decomposition + webhook callbacks |
| **Frontend** | React/Next.js dashboard with WebSocket |
| **Operations** | Cron jobs, platform gateways (Telegram/Discord/Slack), CI/CD |
| **Architecture** | Modular `src/` tree (47 files), test suite, multi-tenant |

---

## Key Documents — What to Read

| If you want to... | Read this |
|------------------|-----------|
| Understand what's running right now | `STATUS.md` |
| See the PoC architecture and sequence diagrams | `knowledge-base/system-docs/architecture/blueprint.md` |
| Understand every backend component in detail | `knowledge-base/system-docs/components/backend-components.md` |
| See the pipeline trace UI layout | `knowledge-base/system-docs/components/frontend-components.md` |
| Rebuild the PoC exactly (prescriptive) | `documentation/build-prompts/PoC-prescriptive-build-prompt.md` |
| Rebuild a functionally identical PoC independently | `documentation/build-prompts/PoC-behavioral-specification.md` |
| Understand how patterns are learned and used | `documentation/pattern-store-examples.md` |
| See the production target architecture | `documentation/end-state/architectural-blueprint.md` |
| Understand design decisions and trade-offs | `documentation/end-state/solution-design.md` |
| See the full API for the end-state system | `documentation/end-state/api-specification.md` |
| See the modular component tree for production | `documentation/end-state/component-specification.md` |
| View a visual architecture diagram | `documentation/diagrams/architecture-component-diagram.html` |

---

## Pipeline Overview

Every request flows through a **12-stage async pipeline**:

```
FOREGROUND (API thread, returns immediately):
  DETECT → MASK → CACHE ──→ dispatch background ──→ return "processing"

BACKGROUND (worker thread):
  RAG → LLM → HYDRATE → LOCK → MERGE → VALIDATE → EXECUTE → NOTIFY → VERIFY
```

| Stage | What Happens |
|-------|-------------|
| **DETECT** | Classify as TMF640 JSON, TMF641 JSON, or unstructured text |
| **MASK** | Replace MSISDNs, IPs with `VAR_*` tokens (cloud AI never sees real IDs) |
| **CACHE** | Jaccard match against RDF pattern store — HIT or MISS |
| **RAG** | Load KB context (core ontology + standards) |
| **LLM** | On MISS: call Deepseek with masked data. On HIT: skip entirely |
| **HYDRATE** | Restore real identifiers from local token map |
| **LOCK** | Acquire per-subscriber advisory lock (30s TTL) |
| **MERGE** | Cascade request characteristics + previous model attrs into plan |
| **VALIDATE** | Blocked keyword scan — abort if destructive commands detected |
| **EXECUTE** | Dispatch workflows to MCP (stubbed in PoC) |
| **NOTIFY** | Emit TMF641 lifecycle milestones + state change events |
| **VERIFY** | Build network elements, save service model, compute diff |

---

## Running the Servers

### Python PoC (Port 8090)
```bash
cd /opt/data/telecom-orchestrator
source .venv/bin/activate
python3 poc/server_live.py
```

### Java PoC (Port 8091)
```bash
cd /opt/data/telecom-orchestrator-java   # or java-poc/
export JAVA_HOME=/tmp/jdk-21.0.4+7
export PATH=/tmp/apache-maven-3.9.6/bin:$JAVA_HOME/bin:$PATH
mvn spring-boot:run
```

Both servers serve the same Web UI at their root (`/`).

---

> **Repository:** [github.com/dileepsethuraman-lab/agentic-orchestrator](https://github.com/dileepsethuraman-lab/agentic-orchestrator)
