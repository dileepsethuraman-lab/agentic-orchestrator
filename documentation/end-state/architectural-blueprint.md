# End-State Architectural Blueprint — Telecom Agentic Service & Resource Orchestrator

> **Document Version:** 1.0.0 | **Date:** 2026-06-23 | **Status:** Target Architecture (Post-PoC)
> **Standards:** TM Forum Open APIs (TMF622, TMF641, TMF640, TMF638, TMF639), MEF LSO, ETSI NFV MANO, IETF YANG
> **Implementation:** Python 3.13, FastAPI, RabbitMQ, PostgreSQL, Redis, Deepseek v4 Pro, Hermes Agent
> **PoC Baseline:** `poc/server_live.py` (1,848 lines), `poc/static/index.html` (727 lines) — Phase 1 complete

---

## Table of Contents

1. [System Identity & Goals](#1-system-identity--goals)
2. [Architecture Overview](#2-architecture-overview)
3. [End-State Component Diagram](#3-end-state-component-diagram)
4. [Core Class Relationships](#4-core-class-relationships)
5. [Sequence Diagrams](#5-sequence-diagrams)
6. [Data Flow Diagrams](#6-data-flow-diagrams)
7. [Deployment Architecture](#7-deployment-architecture)
8. [Script Call References](#8-script-call-references)
9. [Roadmap: PoC → End-State](#9-roadmap-poc--end-state)

---

## 1. System Identity & Goals

### 1.1 What This System IS (End-State)

| Identity | Description |
|----------|-------------|
| **CRM-Triggerable Orchestration Engine** | Accepts TMF622 Product Orders from Salesforce, Dynamics 365, or custom CRM/ERP systems via an Nginx TLS-terminated API Gateway. Decomposes product orders into TMF641 Service Orders, fulfills them through a multi-stage pipeline, and pushes state changes back to the CRM via signed webhook callbacks. |
| **TMF-Standards-Compliant** | Full implementation of TMF622 (Product Ordering), TMF641 (Service Ordering), TMF640 (Service Activation), TMF638 (Service Inventory), and TMF639 (Resource Inventory) Open APIs. All notification events conform to TMF641 v4.1.0 schemas. |
| **Modular `src/` Architecture** | Decomposed from the current single-file `poc/server_live.py` into a proper Python package with separated concerns: `src/api/`, `src/engine/`, `src/inventory/`, `src/mcp/`, `src/notifications/`, `src/catalog/`, `src/security/`, `src/workers/`. |
| **Multi-Service Orchestrator** | Supports 7 service domains: L3VPN (MPLS), SD-WAN Overlay, Fixed Broadband (FTTH/xDSL), Mobile Voice Core, Cloud Connect (AWS Direct Connect / Azure ExpressRoute), Managed Security (Firewall/DDoS/SASE), and Transport/Wavelength (OTN/DWDM). |
| **Real Device Provisioning via MCP** | Southbound integration through dedicated MCP servers: NetBox MCP (IPAM/DCIM source of truth), Ansible MCP (device configuration playbooks), Cisco NSO MCP (multi-vendor service activation), OSM MCP (NFV orchestration), and Device MCP (SSH/NETCONF/gNMI per-device). |
| **Production Message Queue** | RabbitMQ with 5 priority queues (urgent, standard, bulk, retry, webhook_delivery) replaces the PoC's `ThreadPoolExecutor`. Hermes Agent subprocess workers consume jobs with fair dispatch and `prefetch_count=1`. |
| **PostgreSQL + Redis Data Layer** | PostgreSQL stores the product catalog, service inventory, resource inventory, order history, and audit log. Redis provides the task queue backend, session cache, rate-limit counters, and distributed advisory locks. diskcache is retired entirely. |
| **Multi-Profile / Multi-Tenant** | Each tenant (service provider, enterprise customer, wholesale partner) runs in an isolated Hermes profile with its own skills, memory, cron jobs, and KB subset. Profile boundaries prevent cross-tenant data leakage. |
| **Cron-Driven Assurance** | Scheduled cron jobs (via Hermes Cron Scheduler) perform periodic service health checks, resource discovery sweeps, capacity trend analysis, and pattern-store garbage collection. |
| **Platform Gateways** | Hermes Gateway integration for Telegram (ops alerts), Discord (team notifications), and Slack (channel-based status updates). |
| **Full Test Suite** | `tests/` directory with unit tests (pytest), integration tests (pipeline end-to-end), contract tests (TMF API schemas), and load tests (locust targeting 5 TPS sustained). |
| **CI/CD Pipeline** | GitHub Actions or GitLab CI: lint → test → build Docker image → push to registry → deploy to staging → smoke test → promote to production. |

### 1.2 What This System IS NOT

| Non-Goal | Clarification |
|----------|---------------|
| **NOT a single-file server** | The PoC's `server_live.py` is fully decomposed into `src/` modules with proper separation of concerns. |
| **NOT a diskcache-backed prototype** | diskcache is replaced by PostgreSQL (inventory) + Redis (cache/queue). No SQLite in production. |
| **NOT a single-thread executor** | `ThreadPoolExecutor` is replaced by RabbitMQ + multi-process Hermes workers. |
| **NOT limited to mobile voice** | All 7 service domains are supported with full KB product definitions, workflow templates, and resource models. |
| **NOT stubbed execution** | The EXECUTE stage routes through real MCP servers that provision actual network devices. |
| **NOT a single HTML file UI** | The frontend is a modular React/Next.js application with component library, state management, and API client. |
| **NOT single-tenant** | Multi-profile isolation supports multiple tenants on the same infrastructure. |

### 1.3 Key Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Throughput** | 5 TPS sustained (TMF622 Product Orders) | Load test with locust, 60-second window |
| **Cache-hit latency** | < 5 ms (pattern match → instant fulfillment decision) | Jaccard similarity on Redis hash |
| **Cache-miss latency** | < 30 s (mask → LLM → hydrate → validate) | Deepseek v4 Pro with 90 s timeout, typical 15-30 s |
| **Order decomposition** | < 50 ms (product catalog lookup → service order generation) | PostgreSQL indexed query |
| **Webhook delivery** | < 500 ms (TMF641 event → CRM callback POST) | With 3x exponential backoff retry |
| **Service assurance check** | < 10 s per 100 services | Cron-triggered health sweep |
| **Concurrent orders** | 50 simultaneous without lock contention | Per-subscriber advisory locks, different subscribers non-contending |

### 1.4 Service Domain Coverage

| # | Service Domain | Network Elements | TMF Product ID | Lifecycle States |
|---|---------------|------------------|----------------|------------------|
| 1 | L3VPN / MPLS VPN | PE Router, Route Reflector, VRF Instance, CE Interface, BGP Session, NMS | `prod-l3vpn-01` | DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE |
| 2 | SD-WAN Overlay | vCPE/uCPE, SD-WAN Controller, Orchestrator, IPSec Tunnels, Policy Engine | `prod-sdwan-01` | DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE |
| 3 | Broadband / FTTH | OLT, ONT, BNG/BRAS, RADIUS/AAA, EMS, IP Pool | `prod-broadband-01` | DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE |
| 4 | Mobile Voice Core | HLR/HSS, IMS-Core, PCRF/PCF, SMSC, MSC/MME, SBC | `prod-mobile-01` | DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE |
| 5 | Cloud Connect | Cross-connect, VLAN Handoff, BGP Session, Virtual Gateway | `prod-cloudconnect-01` | DESIGNED → FEASIBILITY_CHECKED → CROSS_CONNECT_PROVISIONED → VLAN_CONFIGURED → BGP_ESTABLISHED → ACTIVE |
| 6 | Managed Security | vFirewall, DDoS Scrubbing Center, BGP Flowspec, SASE PoP | `prod-security-01` | DESIGNED → FEASIBILITY_CHECKED → FIREWALL_DEPLOYED → POLICIES_APPLIED → SCRUBBING_ACTIVE → ACTIVE |
| 7 | Transport / Wavelength | ROADM, Transponder, Muxponder, Fiber Pair, OCH Trail | `prod-transport-01` | DESIGNED → FEASIBILITY_CHECKED → WAVELENGTH_ALLOCATED → CROSS_CONNECT_PROVISIONED → OPTICAL_VERIFIED → ACTIVE |

---

## 2. Architecture Overview

### 2.1 Layer Architecture

```mermaid
graph TB
    subgraph NB["NORTHBOUND — CRM Systems"]
        SF["Salesforce<br/>Communications Cloud"]
        D365["Microsoft Dynamics 365"]
        CUST["Custom CRM/ERP<br/>REST Client"]
    end

    subgraph GW["API GATEWAY LAYER"]
        NGINX["Nginx Reverse Proxy<br/>TLS Termination :443<br/>Rate Limiting · API Key Auth<br/>Request Logging · CORS"]
    end

    subgraph OM["ORDER MANAGER LAYER — FastAPI"]
        TMF622["TMF622 Endpoint<br/>POST /api/tmf622/productOrder<br/>GET /api/tmf622/productOrder/{id}"]
        TMF641["TMF641 Endpoint<br/>POST /api/tmf641/serviceOrder<br/>GET /api/tmf641/serviceOrder/{id}"]
        TMF640["TMF640 Endpoint<br/>POST /api/tmf640/serviceActivation"]
        TMF638["TMF638 Endpoint<br/>GET /api/tmf638/service"]
        TMF639["TMF639 Endpoint<br/>GET /api/tmf639/resource"]
        DECOMP["Order Decomposition Engine<br/>ProductOrder → ServiceOrders"]
    end

    subgraph MQ["MESSAGE QUEUE LAYER — RabbitMQ"]
        Q_URGENT["orders_urgent<br/>Priority: high · 1 worker"]
        Q_STANDARD["orders_standard<br/>Priority: normal · 3 workers"]
        Q_BULK["orders_bulk<br/>Priority: low · 2 workers"]
        Q_RETRY["retry<br/>Priority: normal · 1 worker"]
        Q_WEBHOOK["webhook_delivery<br/>Priority: normal · 2 workers"]
    end

    subgraph WORKERS["WORKER POOL — Hermes Agent Subprocesses"]
        W1["Hermes Worker 1<br/>Profile: tenant-a"]
        W2["Hermes Worker 2<br/>Profile: tenant-a"]
        W3["Hermes Worker 3<br/>Profile: tenant-b"]
        WN["Hermes Worker N<br/>Profile: tenant-n"]
    end

    subgraph PIPE["PIPELINE ENGINE — 14 Stages"]
        direction LR
        S0["0. PARSE<br/>Format Detection"]
        S1["1. DECOMPOSE<br/>TMF622→641"]
        S2["2. MASK<br/>DataMasker"]
        S3["3. CACHE<br/>PatternEngine"]
        S4["4. QUERY<br/>Inventory Lookup"]
        S5["5. RAG<br/>KB Context Load"]
        S6["6. LLM<br/>Deepseek Plan Gen"]
        S7["7. HYDRATE<br/>Token Reversal"]
        S8["8. LOCK<br/>SubscriberLock"]
        S9["9. MERGE<br/>Characteristic Cascade"]
        S10["10. VALIDATE<br/>Security Gateway"]
        S11["11. EXECUTE<br/>MCP Dispatch"]
        S12["12. NOTIFY<br/>TMF641 Lifecycle"]
        S13["13. VERIFY<br/>NE Build + Persist"]
    end

    subgraph MCP["MCP INTEGRATION LAYER"]
        NETBOX["NetBox MCP<br/>IPAM · DCIM<br/>Source of Truth"]
        ANSIBLE["Ansible MCP<br/>Device Config<br/>Playbook Execution"]
        NSO["Cisco NSO MCP<br/>Multi-Vendor<br/>Service Activation"]
        OSM["OSM MCP<br/>ETSI NFV MANO<br/>VNF Lifecycle"]
        DEV_MCP["Device MCP<br/>SSH · NETCONF<br/>gNMI · RESTCONF"]
    end

    subgraph DATA["DATA LAYER"]
        PG["PostgreSQL<br/>━━━━━━━━━━<br/>product_catalog<br/>service_inventory<br/>resource_inventory<br/>product_orders<br/>service_orders<br/>audit_log"]
        REDIS["Redis<br/>━━━━━━━━━━<br/>Task Queue (RQ)<br/>Session Cache<br/>Rate Limit Counters<br/>Distributed Locks<br/>Pattern Store Cache"]
        KB["Knowledge Base<br/>━━━━━━━━━━<br/>ontologies/<br/>products/<br/>workflows/<br/>resources/<br/>services/"]
    end

    subgraph HERMES["HERMES AGENT LAYER"]
        SKILLS["Skills<br/>telecom-provisioning<br/>device-discovery<br/>assurance-check"]
        MEMORY["Memory<br/>Pattern Store<br/>Lessons Learned<br/>Session History"]
        CRON["Cron Scheduler<br/>Assurance · Discovery<br/>Capacity · GC"]
        SESSION["Session Store<br/>Multi-Profile Isolation<br/>Per-Tenant State"]
    end

    subgraph NOTIFY["NOTIFICATION LAYER"]
        WEBHOOK["Webhook Dispatcher<br/>CRM Callbacks<br/>Signed · Retry 3x<br/>Dead-Letter Queue"]
        GATEWAYS["Platform Gateways<br/>Telegram · Discord<br/>Slack"]
    end

    subgraph FE["FRONTEND — React/Next.js"]
        DASH["Modular Dashboard<br/>Order Management<br/>Service Inventory<br/>Resource Topology<br/>Trace Viewer<br/>Pattern Analytics"]
    end

    subgraph CICD["CI/CD PIPELINE"]
        GHA["GitHub Actions<br/>Lint → Test → Build<br/>Push → Deploy → Smoke"]
    end

    %% Connections
    SF -->|"TMF622 JSON"| NGINX
    D365 -->|"TMF622 JSON"| NGINX
    CUST -->|"TMF622 JSON"| NGINX
    NGINX -->|"Forward :8000"| TMF622
    NGINX -->|"Forward :8000"| TMF641
    TMF622 --> DECOMP
    DECOMP -->|"TMF641 ServiceOrders"| TMF641
    TMF641 --> MQ
    TMF640 --> PIPE
    Q_STANDARD --> WORKERS
    Q_URGENT --> WORKERS
    Q_BULK --> WORKERS
    Q_RETRY --> WORKERS
    WORKERS --> PIPE
    PIPE --> MCP
    S11 --> NETBOX
    S11 --> ANSIBLE
    S11 --> NSO
    S11 --> OSM
    S11 --> DEV_MCP
    PIPE --> DATA
    PIPE --> HERMES
    HERMES --> KB
    S12 --> WEBHOOK
    S12 --> GATEWAYS
    WEBHOOK -->|"TMF641 Event POST"| SF
    WEBHOOK -->|"TMF641 Event POST"| D365
    DATA --> FE
    FE -->|"REST API"| TMF622
    CICD -.->|"Deploy"| GW
```

### 2.2 Pipeline Stage Summary (14-Stage End-State)

| # | Stage | Module | Trigger | Description |
|---|-------|--------|---------|-------------|
| **0** | PARSE | `orchestrator_brain.py` | Every request | Auto-detect TMF622 Product Order vs TMF640 Activation vs TMF641 Service Order vs unstructured text |
| **1** | DECOMPOSE | `order_decomposer.py` | TMF622 only | Decompose Product Order into one or more TMF641 Service Orders using product catalog rules |
| **2** | MASK | `data_masker.py` | Every request | Tokenize MSISDN, IMSI, IP, hostname → VAR_* tokens before any cloud call |
| **3** | CACHE | `pattern_engine.py` | Every request | Jaccard similarity match against RDF pattern store; HIT → instant plan; MISS → flag LLM |
| **4** | QUERY | `inventory_queries.py` | Every request | Look up existing service/resource state from PostgreSQL ServiceInventory + ResourceInventory |
| **5** | RAG | `kb_context.py` | Background only | Load domain knowledge from KB (ontology, product template, workflow definitions) |
| **6** | LLM | `deepseek_client.py` | Cache MISS only | Generate orchestration plan via Deepseek v4 Pro with masked data + KB context |
| **7** | HYDRATE | `data_masker.py` | Background only | Reverse VAR_* tokens → real identifiers from local token_map |
| **8** | LOCK | `subscriber_lock.py` | Background only | Acquire Redis-based per-subscriber advisory lock (30 s TTL, 5 s retry budget) |
| **9** | MERGE | `orchestrator_brain.py` | Background only | Cascade request characteristics + previous model attributes into plan parameters |
| **10** | VALIDATE | `validation_gateway.py` | Background only | Scan plan against BLOCKED_KEYWORDS; schema validation against Pydantic models |
| **11** | EXECUTE | `mcp_dispatcher.py` | Background only | Dispatch workflows to MCP servers (NetBox → Ansible → NSO → OSM → Device) with rollback on failure |
| **12** | NOTIFY | `notifier.py` | Background only | Emit TMF641 ServiceOrderMilestoneEvent (intermediate) + ServiceOrderStateChangeEvent (final) |
| **13** | VERIFY | `orchestrator_brain.py` | Background only | Build network element cards, compute subscriber diff, persist to PostgreSQL + Redis, emit final state |

---

## 3. End-State Component Diagram

```mermaid
graph TB
    subgraph EXTERNAL["EXTERNAL SYSTEMS"]
        CRM_SF["Salesforce<br/>Communications Cloud"]
        CRM_D365["Dynamics 365"]
        CRM_CUST["Custom CRM"]
    end

    subgraph EDGE["EDGE — Nginx API Gateway"]
        NGX["Nginx :443<br/>━━━━━━━━━━<br/>TLS Termination<br/>rate_limit: 50 r/s<br/>auth: API Key + OAuth2<br/>CORS: allowed origins"]
        LOG["Access Log<br/>JSON to stdout"]
    end

    subgraph API["API LAYER — FastAPI :8000"]
        ROUTER["FastAPI Router<br/>━━━━━━━━━━<br/>/api/tmf622/productOrder<br/>/api/tmf641/serviceOrder<br/>/api/tmf640/serviceActivation<br/>/api/tmf638/service<br/>/api/tmf639/resource<br/>/health"]
        OM["OrderManager<br/>━━━━━━━━━━<br/>validate_tmf622()<br/>validate_tmf641()<br/>acknowledge_order()"]
        ODE["OrderDecomposer<br/>━━━━━━━━━━<br/>decompose_product_order()<br/>ProductCatalog.lookup()<br/>decomposition_rules"]
    end

    subgraph MQ["RABBITMQ — Message Broker"]
        RMQ_EX["Exchange: orders<br/>type: topic"]
        RMQ_URGENT["Queue: orders.urgent<br/>priority: 10 · ttl: 300s"]
        RMQ_STANDARD["Queue: orders.standard<br/>priority: 5"]
        RMQ_BULK["Queue: orders.bulk<br/>priority: 1"]
        RMQ_RETRY["Queue: orders.retry<br/>dlx: orders.dead"]
        RMQ_WEBHOOK["Queue: webhooks<br/>priority: 5"]
    end

    subgraph WORKERS["WORKER POOL"]
        WD["WorkerDispatcher<br/>━━━━━━━━━━<br/>consume_order()<br/>fair_dispatch()<br/>prefetch_count=1"]
        HW1["HermesWorker-1<br/>profile: tenant-a"]
        HW2["HermesWorker-2<br/>profile: tenant-a"]
        HW3["HermesWorker-3<br/>profile: tenant-b"]
    end

    subgraph BRAIN["ORCHESTRATOR BRAIN"]
        OB["OrchestratorBrain<br/>━━━━━━━━━━<br/>run() — 14-stage pipeline<br/>parse_intent()<br/>build_plan()<br/>cascade_merge()<br/>verify_and_persist()"]
        PE["PatternEngine<br/>━━━━━━━━━━<br/>lookup() — Jaccard match<br/>learn() — auto-pattern<br/>reinforce() — boost confidence<br/>teach() — manual inject"]
        DM["DataMasker<br/>━━━━━━━━━━<br/>mask() — tokenize<br/>hydrate() — reverse<br/>MSISDN_RE · IP_RE"]
        VG["ValidationGateway<br/>━━━━━━━━━━<br/>validate_plan()<br/>BLOCKED_KEYWORDS<br/>schema_enforce()"]
        MD["MCPDispatcher<br/>━━━━━━━━━━<br/>execute_workflow()<br/>dispatch_parallel()<br/>rollback_on_failure()"]
        LN["LifecycleNotifier<br/>━━━━━━━━━━<br/>build_notification_trace()<br/>emit_milestone()<br/>emit_state_change()"]
        WM["WebhookManager<br/>━━━━━━━━━━<br/>dispatch_callback()<br/>retry_exponential()<br/>dead_letter_queue()"]
        DC["DeepseekClient<br/>━━━━━━━━━━<br/>call_deepseek()<br/>timeout: 90s<br/>fallback_plan()"]
        KBCTX["KBContextLoader<br/>━━━━━━━━━━<br/>load_kb_context()<br/>load_product_template()<br/>load_workflow_defs()"]
    end

    subgraph INVENTORY["INVENTORY LAYER"]
        PC["ProductCatalog<br/>━━━━━━━━━━<br/>find_by_id()<br/>find_by_category()<br/>decompose()"]
        SI["ServiceInventory<br/>━━━━━━━━━━<br/>get_service()<br/>create_service()<br/>update_state()"]
        RI["ResourceInventory<br/>━━━━━━━━━━<br/>get_resource()<br/>allocate_resource()<br/>release_resource()"]
        OH["OrderHistory<br/>━━━━━━━━━━<br/>create_order()<br/>update_state()<br/>get_audit_log()"]
        AL["AuditLog<br/>━━━━━━━━━━<br/>log_event()<br/>query_by_order()<br/>export_csv()"]
    end

    subgraph MCP_SERVERS["MCP SERVERS"]
        NB["NetBox MCP<br/>━━━━━━━━━━<br/>find_available_ip()<br/>allocate_prefix()<br/>create_device()<br/>assign_interface()"]
        AN["Ansible MCP<br/>━━━━━━━━━━<br/>run_playbook()<br/>check_mode()<br/>gather_facts()<br/>validate_config()"]
        NS["Cisco NSO MCP<br/>━━━━━━━━━━<br/>create_service()<br/>sync_from_device()<br/>commit_dry_run()"]
        OS["OSM MCP<br/>━━━━━━━━━━<br/>instantiate_ns()<br/>scale_vnf()<br/>terminate_ns()"]
        DV["Device MCP<br/>━━━━━━━━━━<br/>send_config()<br/>get_state()<br/>validate_commit()"]
    end

    subgraph STORES["PERSISTENT STORES"]
        PG_DB[("PostgreSQL 16<br/>━━━━━━━━━━<br/>product_catalog<br/>service_inventory<br/>resource_inventory<br/>product_orders<br/>service_orders<br/>webhook_deliveries<br/>audit_log")]
        REDIS_DB[("Redis 7<br/>━━━━━━━━━━<br/>pattern_store<br/>task_queues<br/>session_cache<br/>rate_limits<br/>subscriber_locks<br/>cache_hot_keys")]
        KB_FS[("Knowledge Base FS<br/>━━━━━━━━━━<br/>ontologies/<br/>products/<br/>workflows/<br/>resources/<br/>services/<br/>lessons/")]
    end

    subgraph CHRON["CRON SCHEDULER"]
        CR_ASSUR["Service Assurance<br/>━━━━━━━━━━<br/>health_check_sweep()<br/>degradation_alert()"]
        CR_DISC["Resource Discovery<br/>━━━━━━━━━━<br/>scan_network()<br/>sync_inventory()"]
        CR_CAP["Capacity Management<br/>━━━━━━━━━━<br/>trend_analysis()<br/>threshold_alert()"]
        CR_GC["Pattern GC<br/>━━━━━━━━━━<br/>purge_stale_patterns()<br/>compact_index()"]
    end

    subgraph NOTIFICATIONS["NOTIFICATION LAYER"]
        NW["WebhookDispatcher<br/>━━━━━━━━━━<br/>dispatch_callback()<br/>retry: 3x backoff<br/>dead_letter_queue"]
        TG["Telegram Gateway<br/>━━━━━━━━━━<br/>ops_alerts()<br/>failure_notify()"]
        DC_GW["Discord Gateway<br/>━━━━━━━━━━<br/>team_notify()<br/>status_update()"]
        SL_GW["Slack Gateway<br/>━━━━━━━━━━<br/>channel_post()<br/>completion_notify()"]
    end

    subgraph FRONTEND["FRONTEND — Next.js :3000"]
        FE_OM["Order Management<br/>━━━━━━━━━━<br/>Product Order List<br/>Service Order Detail"]
        FE_SI["Service Inventory<br/>━━━━━━━━━━<br/>Service Search<br/>Resource Topology"]
        FE_TR["Trace Viewer<br/>━━━━━━━━━━<br/>14-Stage Cards<br/>Diff Highlighting"]
        FE_PA["Pattern Analytics<br/>━━━━━━━━━━<br/>Confidence Gauges<br/>Pattern Explorer"]
    end

    subgraph CICD["CI/CD"]
        GIT["Git Repository<br/>━━━━━━━━━━<br/>src/ · tests/ · docs/<br/>Dockerfile<br/>docker-compose.yml"]
        ACTIONS["GitHub Actions<br/>━━━━━━━━━━<br/>lint → test → build<br/>push image → deploy<br/>smoke test → promote"]
        REG["Container Registry<br/>━━━━━━━━━━<br/>ghcr.io/telecom-orch"]
    end

    %% Edge connections
    CRM_SF -->|"TMF622"| NGX
    CRM_D365 -->|"TMF622"| NGX
    CRM_CUST -->|"TMF622"| NGX
    NGX --> ROUTER
    ROUTER --> OM
    OM --> ODE
    ODE --> RMQ_EX
    RMQ_EX --> RMQ_URGENT
    RMQ_EX --> RMQ_STANDARD
    RMQ_EX --> RMQ_BULK
    RMQ_STANDARD --> WD
    WD --> HW1
    WD --> HW2
    WD --> HW3
    HW1 --> OB
    HW2 --> OB
    HW3 --> OB
    OB --> PE
    OB --> DM
    OB --> VG
    OB --> MD
    OB --> LN
    OB --> DC
    OB --> KBCTX
    PE --> REDIS_DB
    MD --> NB
    MD --> AN
    MD --> NS
    MD --> OS
    MD --> DV
    LN --> WM
    LN --> TG
    LN --> DC_GW
    LN --> SL_GW
    WM --> RMQ_WEBHOOK
    WM -->|"POST callback"| CRM_SF
    WM -->|"POST callback"| CRM_D365
    OB --> PC
    OB --> SI
    OB --> RI
    OB --> OH
    OB --> AL
    PC --> PG_DB
    SI --> PG_DB
    RI --> PG_DB
    OH --> PG_DB
    AL --> PG_DB
    KBCTX --> KB_FS
    HW1 --> REDIS_DB
    CR_ASSUR --> SI
    CR_DISC --> RI
    CR_CAP --> RI
    CR_GC --> PE
    FE_OM --> ROUTER
    FE_SI --> ROUTER
    FE_TR --> ROUTER
    FE_PA --> ROUTER
    GIT --> ACTIONS
    ACTIONS --> REG
    REG -.->|"Deploy"| NGX
```

---

## 4. Core Class Relationships

```mermaid
classDiagram
    class OrchestratorBrain {
        +ProductCatalog catalog
        +ServiceInventory service_inv
        +ResourceInventory resource_inv
        +PatternEngine patterns
        +DataMasker masker
        +ValidationGateway validator
        +MCPDispatcher mcp
        +LifecycleNotifier notifier
        +WebhookManager webhooks
        +DeepseekClient llm_client
        +OrderDecomposer decomposer
        +run(request) OrchestrationResult
        +parse_intent(raw) ParseResult
        +build_plan(parsed, ctx) OrchestrationPlan
        +cascade_merge(plan, chars, prev) dict
        +verify_and_persist(result) FinalState
    }

    class OrderDecomposer {
        +ProductCatalog catalog
        +decompose_product_order(tmf622) list~ServiceOrder~
        +validate_product_order(order) bool
        +generate_child_orders(product, chars) list~ServiceOrder~
        +resolve_dependencies(orders) list~ServiceOrder~
    }

    class ProductCatalog {
        +Session db
        +find_by_id(product_id) Product
        +find_by_category(category) list~Product~
        +get_decomposition_rules(product_id) DecompositionRules
        +get_required_resources(product_id) list~ResourceTemplate~
        +get_service_template(product_id) ServiceTemplate
    }

    class ServiceInventory {
        +Session db
        +get_service(service_id) Service
        +create_service(order, chars) Service
        +update_state(service_id, state, audit) Service
        +find_by_customer(customer_id) list~Service~
        +find_by_product(product_id) list~Service~
    }

    class ResourceInventory {
        +Session db
        +get_resource(resource_id) Resource
        +allocate_resource(type, params) Resource
        +release_resource(resource_id) Resource
        +find_by_device(device_name) list~Resource~
        +update_state(resource_id, state) Resource
    }

    class PatternEngine {
        +Redis redis
        +lookup(svc, chars) PatternNode?
        +learn(svc, chars, plan, all_chars, source) PatternNode
        +reinforce(pattern) PatternNode
        +teach(triples, source) PatternNode
        +list_all() list~dict~
        +get(pid) dict?
        -_match_score(pat_chars, req_chars) float
        -_load(pid) PatternNode?
        -_save(node)
        -_unindex(pid)
        -INSTANCE_ATTRS Set
    }

    class PatternNode {
        +str id
        +str service_type
        +str label
        +dict characteristics
        +list triples
        +list resources
        +float confidence
        +int use_count
        +str source
    }

    class DataMasker {
        -Dict map
        -Dict ctr
        +mask(text) tuple~str, dict~
        +hydrate(text, token_map) str
        +tokenize_batch(items) list
    }

    class ValidationGateway {
        +List BLOCKED_KEYWORDS
        +validate_plan(plan, masked_text) ValidationResult
        +schema_enforce(plan, schema) list~SchemaViolation~
        +check_destructive_commands(text) list~str~
        +validate_device_access(device, user) bool
    }

    class MCPDispatcher {
        +Dict mcp_clients
        +execute_workflow(plan) ExecutionResult
        +dispatch_parallel(workflows) list~ExecutionResult~
        +rollback_on_failure(results) RollbackResult
        +register_mcp(name, client)
        -_mcp_netbox NetBoxClient
        -_mcp_ansible AnsibleClient
        -_mcp_nso NSOClient
        -_mcp_osm OSMClient
        -_mcp_device DeviceClient
    }

    class WebhookManager {
        +Redis redis
        +Queue webhook_queue
        +dispatch_callback(order, event) DeliveryResult
        +retry_exponential(delivery_id) DeliveryResult
        +dead_letter_queue() list~FailedDelivery~
        +register_callback(order_id, url)
        +sign_payload(payload) str
    }

    class NotificationEmitter {
        +LifecycleNotifier notifier
        +WebhookManager webhooks
        +GatewayManager gateways
        +emit_event(order, state_change) NotificationTrace
        +notify_ops(severity, message)
        +notify_team(channel, message)
    }

    class LifecycleManager {
        +ServiceInventory service_inv
        +ResourceInventory resource_inv
        +OrderHistory order_hist
        +transition_state(order, from_state, to_state) StateTransition
        +validate_transition(from_state, to_state) bool
        +get_lifecycle_states(service_type) list~str~
        +get_current_state(entity_id) str
    }

    OrchestratorBrain --> ProductCatalog : uses
    OrchestratorBrain --> ServiceInventory : reads/writes
    OrchestratorBrain --> ResourceInventory : reads/writes
    OrchestratorBrain --> PatternEngine : cache-first
    OrchestratorBrain --> DataMasker : sovereignty
    OrchestratorBrain --> ValidationGateway : security
    OrchestratorBrain --> MCPDispatcher : executes
    OrchestratorBrain --> NotificationEmitter : notifies
    OrchestratorBrain --> LifecycleManager : transitions
    OrchestratorBrain --> OrderDecomposer : TMF622 path

    OrderDecomposer --> ProductCatalog : reads rules
    OrderDecomposer --> ServiceInventory : creates orders

    PatternEngine --> PatternNode : manages
    PatternEngine --> ServiceInventory : reads prev model

    NotificationEmitter --> LifecycleManager : reads states
    NotificationEmitter --> WebhookManager : delivers callbacks

    WebhookManager --> OrderDecomposer : reads order
    MCPDispatcher --> ResourceInventory : updates resources
    ValidationGateway --> OrchestratorBrain : blocks/rejects
```

---

## 5. Sequence Diagrams

### 5.1 TMF622 Product Order → Decomposition → Parallel Service Orders → Fulfillment → CRM Callback

```mermaid
sequenceDiagram
    participant CRM as CRM System
    participant NGX as Nginx Gateway
    participant API as FastAPI Order Manager
    participant ODE as OrderDecomposer
    participant PC as ProductCatalog (PG)
    participant RMQ as RabbitMQ
    participant W1 as Worker-1
    participant W2 as Worker-2
    participant OB as OrchestratorBrain
    participant MCP as MCPDispatcher
    participant WM as WebhookManager

    CRM->>NGX: POST /api/tmf622/productOrder
    NGX->>NGX: TLS termination, rate check, API key validation
    NGX->>API: Forward validated request

    API->>API: validate_tmf622(payload)
    API->>ODE: decompose_product_order(tmf622_order)

    ODE->>PC: find_by_id("prod-l3vpn-01")
    PC-->>ODE: Product {decomposition_rules, required_resources, service_template}

    ODE->>ODE: Apply decomposition rules
    Note over ODE: Product "Enterprise MPLS L3VPN" decomposes into:<br/>SO-1: Allocate IP Resources<br/>SO-2: Provision VRF on PE<br/>SO-3: Configure BGP Peering<br/>SO-4: Configure CE Interface<br/>SO-5: Verify and Activate

    ODE->>ODE: resolve_dependencies(service_orders)
    Note over ODE: DAG: SO-1 → SO-2,SO-3,SO-4 → SO-5

    ODE->>API: [ServiceOrder × 5] with dependencies
    API->>API: Persist product_order + service_orders to PostgreSQL
    API-->>CRM: 202 Accepted {order_id, state: "acknowledged", serviceOrder: [...]}

    API->>RMQ: publish SO-1 to orders.standard
    API->>RMQ: publish SO-2, SO-3, SO-4 to orders.standard (parallel, after SO-1)
    API->>RMQ: publish SO-5 to orders.standard (after SO-2,3,4)

    RMQ->>W1: dispatch SO-1
    W1->>OB: run(SO-1)
    OB->>OB: PARSE → MASK → CACHE → QUERY → RAG → LLM → HYDRATE → LOCK → MERGE → VALIDATE
    OB->>MCP: execute_workflow(plan)
    MCP->>MCP: NetBox: allocate IP subnet → Ansible: configure interface
    MCP-->>OB: SO-1: Allocate IP Resources — DONE
    OB->>WM: dispatch_callback(SO-1, milestone: "RESOURCE_ALLOCATED")
    WM->>CRM: POST callback URL → TMF641 MilestoneEvent

    par Parallel Service Orders
        RMQ->>W1: dispatch SO-2 (VRF on PE)
        W1->>OB: run(SO-2)
        OB->>MCP: NetBox: find device + Ansible: configure VRF
        MCP-->>OB: SO-2 DONE
        OB->>WM: dispatch_callback(SO-2, milestone: "DEVICE_CONFIGURED")
    and
        RMQ->>W2: dispatch SO-3 (BGP Peering)
        W2->>OB: run(SO-3)
        OB->>MCP: Cisco NSO: create BGP service
        MCP-->>OB: SO-3 DONE
        OB->>WM: dispatch_callback(SO-3, milestone: "PEERING_ESTABLISHED")
    and
        RMQ->>W1: dispatch SO-4 (CE Interface)
        W1->>OB: run(SO-4)
        OB->>MCP: Ansible: configure CE port
        MCP-->>OB: SO-4 DONE
    end

    RMQ->>W2: dispatch SO-5 (Verify + Activate)
    W2->>OB: run(SO-5)
    OB->>MCP: Ansible: verify BGP state, ping test
    MCP-->>OB: Verification PASSED
    OB->>OB: VERIFY → build NEs → persist to PG + Redis
    OB->>WM: dispatch_callback(SO-5, state_change: "completed")

    WM->>CRM: POST TMF641 ServiceOrderStateChangeEvent {state: "completed"}
    CRM-->>WM: 200 OK
    Note over CRM: CRM updates order: Status = "Provisioned"

    WM->>WM: If callback fails → retry 3x exponential backoff<br/>If all fail → dead-letter queue for manual replay
```

### 5.2 Cache-Hit Fast Path (Sub-5 ms Pattern Match → Instant Fulfillment)

```mermaid
sequenceDiagram
    participant API as FastAPI
    participant OB as OrchestratorBrain
    participant PE as PatternEngine (Redis)
    participant DM as DataMasker
    participant BG as Background Worker

    API->>OB: run(service_order)
    Note over OB: STAGE 0: PARSE
    OB->>OB: detect_format() → "tmf641"

    Note over OB,DM: STAGE 2: MASK
    OB->>DM: mask(text)
    DM->>DM: MSISDN "447700123456" → VAR_MSISDN_1
    DM-->>OB: masked_text + token_map (local only)

    Note over OB,PE: STAGE 3: CACHE (HIT)
    OB->>OB: extract_chars(exclude INSTANCE_ATTRS)
    OB->>PE: patterns.lookup("mobile", chars)
    PE->>PE: Load candidates from Redis hash
    PE->>PE: Jaccard match: intersection={customerSegment,slaTier,productId}<br/>union={customerSegment,slaTier,productId} → score=1.0
    PE->>PE: patterns.reinforce() → confidence += 0.05
    PE-->>OB: PatternNode (confidence=0.92, 6 resources) ← HIT!

    OB->>OB: Build plan from pattern.resources<br/>Cascade request chars into plan params
    OB-->>API: 202 Accepted {order_id, status: "processing"}

    OB->>BG: Submit to background queue

    Note over BG: STAGE 5: RAG → load KB context (6 NEs)
    Note over BG: STAGE 6: LLM → SKIPPED (cache hit, llm_used=False)
    Note over BG: STAGE 7: HYDRATE → VAR_MSISDN_1 → "447700123456"
    Note over BG: STAGE 8: LOCK → acquire Redis lock (30s TTL)
    Note over BG: STAGE 9: MERGE → cascade all_chars + prev model
    Note over BG: STAGE 10: VALIDATE → keyword scan PASSED
    Note over BG: STAGE 11: EXECUTE → MCP: Ansible playbook (pre-learned workflow)
    Note over BG: STAGE 12: NOTIFY → 6 lifecycle milestones emitted
    Note over BG: STAGE 13: VERIFY → build NEs, persist, compute diff

    Note right of BG: TOTAL TIME: foreground < 5 ms (cache decision)<br/>background: ~15 s (Ansible execution)<br/>vs. ~45 s for LLM path

    API->>OB: GET /api/process/{order_id}
    OB-->>API: {status: "completed", final_state: {...}}
```

### 5.3 Cache-Miss LLM Fallback (Mask → Deepseek → Hydrate → Validate → Execute)

```mermaid
sequenceDiagram
    participant OB as OrchestratorBrain
    participant PE as PatternEngine
    participant KB as KBContextLoader
    participant DS as Deepseek v4 Pro
    participant DM as DataMasker
    participant VG as ValidationGateway
    participant MCP as MCPDispatcher

    OB->>PE: patterns.lookup("l3vpn", chars)
    PE->>PE: No pattern for wholesale+platinum → MISS
    PE-->>OB: None (llm_used = True)

    OB->>KB: load_kb_context("l3vpn")
    KB->>KB: Read core-ontology.md + product template prod-l3vpn-01.yaml<br/>+ segment-overrides.yaml + sla-overrides.yaml
    KB-->>OB: Domain context (4,000 chars):<br/>• Required resources: PE, VRF, BGP, CE, Subnet<br/>• Segment: wholesale → CE customer-managed, VLAN handoff, MTU 9100<br/>• SLA: platinum → dual PE, diverse paths, <50ms failover, BFD

    OB->>DS: call_deepseek(prompt, timeout=90)
    Note over DS: PROMPT STRUCTURE:<br/>1. Domain Knowledge (from KB) — 4,000 chars<br/>2. Request (SENSITIVE DATA MASKED) — 2,000 chars<br/>"Provision L3VPN for VAR_MSISDN_1, site VAR_HOST_1,<br/>bandwidth 1000 Mbps, routing BGP, customer ASN VAR_ASN_1"<br/>3. Instruction: Return ONLY valid JSON {workflows, params, devices}

    Note over DS: Deepseek sees VAR_* tokens only.<br/>NO real IPs, hostnames, ASNs, or phone numbers.<br/>Reasons from KB context + masked request characteristics.

    DS-->>OB: JSON plan:
    Note over OB: {<br/>  "workflows": [<br/>    "ResourceAllocation",<br/>    "DeviceConfiguration",<br/>    "BGPConfiguration",<br/>    "ServiceVerification"<br/>  ],<br/>  "params": {<br/>    "vrf": "CUST-VAR_HOST_1-CORP",<br/>    "rd": "65001:1001",<br/>    "bandwidth": 1000,<br/>    ...<br/>  },<br/>  "devices": [<br/>    {"name": "VAR_HOST_1", "type": "PE", "vendor": "cisco-xr"}<br/>  ]<br/>}

    OB->>DM: hydrate(plan, token_map)
    DM->>DM: VAR_MSISDN_1 → "447700123456"<br/>VAR_HOST_1 → "sfo-pe-01"<br/>VAR_ASN_1 → "65002"
    DM-->>OB: Hydrated plan with real values

    OB->>OB: LOCK → MERGE → cascade all_chars

    OB->>VG: validate_plan(plan)
    VG->>VG: BLOCKED_KEYWORDS scan: "erase","reload","format","shutdown",... → PASS
    VG->>VG: Schema enforcement: check required fields per product template → PASS
    VG-->>OB: ValidationResult(status="PASSED")

    OB->>MCP: execute_workflow(plan)
    MCP->>MCP: NetBox: allocate subnet 10.100.1.0/30 from pool SJC-CE
    MCP->>MCP: Ansible: configure VRF, BGP on sfo-pe-01 (18 config lines)
    MCP->>MCP: Ansible: verify BGP state (Established, 12 prefixes)
    MCP-->>OB: ExecutionResult(status="SUCCESS", resources_created=4)

    OB->>OB: VERIFY: build NE cards, persist to PG, learn pattern
    OB->>PE: patterns.learn("l3vpn", chars, plan, all_chars, source="auto")
    PE->>PE: Build RDF triples from plan<br/>Confidence = 0.30 (auto-learned seed)
    PE-->>OB: PatternNode saved → next request will be cache HIT
```

### 5.4 Security Block (Destructive Keyword → Abort → Alert to Ops)

```mermaid
sequenceDiagram
    participant OB as OrchestratorBrain
    participant DM as DataMasker
    participant PE as PatternEngine
    participant DS as Deepseek
    participant VG as ValidationGateway
    participant WM as WebhookManager
    participant OPS as Ops Channel (Telegram)

    OB->>DM: mask(request)
    DM-->>OB: masked_text, token_map

    OB->>PE: patterns.lookup("transport", chars)
    PE-->>OB: MISS → llm_used = True

    OB->>DS: call_deepseek(masked_text + KB context)
    Note over DS: Malicious/erroneous input includes:<br/>"After configuring the ROADM,<br/>reload the transponder and<br/>format the flash on slot 3"

    DS-->>OB: JSON plan containing:<br/>"workflows": ["TransponderConfig", "MaintenanceReload", "FlashReformat"]<br/>"params": {"reload": "force", "format": "slot3"}

    OB->>DM: hydrate(plan, token_map)
    Note over OB: Hydrated plan now contains real commands

    rect rgb(239, 68, 68, 0.15)
        Note over OB,VG: ⛔ STAGE 10: VALIDATE — SECURITY GATEWAY
        OB->>VG: validate_plan(hydrated_plan, masked_text)

        VG->>VG: Scan plan JSON + masked_text against BLOCKED_KEYWORDS:
        Note over VG: BLOCKED_KEYWORDS = [<br/>  "erase", "reload", "format",<br/>  "shutdown", "no switchport",<br/>  "write erase", "delete startup-config",<br/>  "boot system flash"<br/>]

        VG->>VG: 🔴 MATCH FOUND:<br/>Keyword "reload" in params.reload<br/>Keyword "format" in params.format
        VG-->>OB: ValidationResult(status="BLOCKED",<br/>  blocked_keywords=["reload", "format"],<br/>  reason="Destructive commands detected")

        OB->>OB: Abort pipeline immediately<br/>Set order status = "blocked"<br/>No MCP execution occurs
    end

    OB->>WM: dispatch_callback(order, blocked_event)
    WM->>WM: POST to CRM callback URL → TMF641 StateChangeEvent {state: "rejected"}

    OB->>OPS: CRITICAL ALERT → Telegram ops channel
    Note over OPS: 🚨 SECURITY BLOCK<br/>Order: so-transport-0059<br/>Blocked keywords: reload, format<br/>Source: Deepseek LLM plan generation<br/>Action: Pipeline aborted, no devices touched<br/>Review required before retry
```

### 5.5 CRM Webhook Callback Flow (State Changes Pushed to CRM)

```mermaid
sequenceDiagram
    participant OB as OrchestratorBrain
    participant LN as LifecycleNotifier
    participant SR as SERVICE_RESOURCES (KB)
    participant WM as WebhookManager
    participant RMQ as RabbitMQ (webhook queue)
    participant WW as WebhookWorker
    participant CRM as CRM System
    participant DLQ as Dead-Letter Queue

    Note over OB: Pipeline STAGE 12: NOTIFY
    OB->>LN: build_notification_trace(order_id, "l3vpn", subscriber_id)

    LN->>SR: parse_lifecycle("l3vpn")
    SR-->>LN: ["DESIGNED", "FEASIBILITY_CHECKED", "RESOURCE_ALLOCATED",<br/>"DEVICE_CONFIGURED", "PEERING_ESTABLISHED", "ACTIVE"]

    Note over LN: correlationId = "corr-PO-A1B2C3D4"

    loop For each state (i=0 to 5)
        alt i < 5 (intermediate milestone)
            LN->>LN: emit_milestone(state)
            Note over LN: ServiceOrderMilestoneEvent:<br/>{state: "inProgress", milestone: {name: "DEVICE_CONFIGURED", status: "achieved"}}
        else i == 5 (final state)
            LN->>LN: emit_state_change("completed")
            Note over LN: ServiceOrderStateChangeEvent:<br/>{state: "completed", completionDate: "2026-06-23T..."}
        end

        LN->>WM: enqueue_callback(order, event)
        WM->>RMQ: publish to webhooks queue
    end

    RMQ->>WW: dispatch webhook delivery job

    WW->>CRM: POST https://crm.example.com/api/webhooks/telco-order-status
    Note over WW,CRM: Headers:<br/>X-TMF-Event-Type: ServiceOrderMilestoneEvent<br/>X-Order-Id: so-l3vpn-0042<br/>X-Signature: sha256=abc123...
    Note over WW,CRM: Body: TMF641 ServiceOrderMilestoneEvent JSON

    alt CRM responds 200 OK
        CRM-->>WW: 200 OK
        WW->>WW: Log delivery: success, response_time=120ms
    else CRM responds 4xx/5xx
        CRM-->>WW: 500 Internal Server Error
        WW->>WW: retry_count = 0 → schedule retry in 2^0 × 5s = 5s

        Note over WW: Wait 5 seconds...
        WW->>CRM: POST (Retry 1/3)
        CRM-->>WW: 500 Internal Server Error
        WW->>WW: retry_count = 1 → schedule retry in 2^1 × 5s = 10s

        Note over WW: Wait 10 seconds...
        WW->>CRM: POST (Retry 2/3)
        CRM-->>WW: 503 Service Unavailable
        WW->>WW: retry_count = 2 → schedule retry in 2^2 × 5s = 20s

        Note over WW: Wait 20 seconds...
        WW->>CRM: POST (Retry 3/3 — final attempt)
        alt CRM recovers
            CRM-->>WW: 200 OK
            WW->>WW: Log delivery: success after 3 retries
        else CRM still down
            CRM-->>WW: 503 Service Unavailable
            WW->>DLQ: Move to dead-letter queue
            Note over DLQ: Dead-letter entry:<br/>{order_id, event_type, callback_url, payload,<br/>failed_attempts: 3, last_error: "503",<br/>dead_lettered_at: "2026-06-23T..."}
            WW->>WW: Alert ops: "Webhook delivery FAILED for so-l3vpn-0042 after 3 retries"
        end
    end
```

### 5.6 Cron-Driven Service Assurance (Periodic Health Checks → Alert on Degradation)

```mermaid
sequenceDiagram
    participant CRON as Cron Scheduler
    participant OB as OrchestratorBrain
    participant SI as ServiceInventory (PG)
    participant RI as ResourceInventory (PG)
    participant MCP as MCPDispatcher
    participant NB as NetBox MCP
    participant AN as Ansible MCP
    participant DEV as Device MCP
    participant ALERT as Alert Manager

    Note over CRON: Cron trigger: every 15 minutes<br/>Job: assurance_health_sweep()

    CRON->>OB: run_assurance_sweep()

    OB->>SI: find_active_services()
    SI-->>OB: 247 active services across all domains

    loop For each service (batched, 10 concurrent)
        OB->>SI: get_service(svc_id)
        SI-->>OB: Service {id, type: "l3vpn", state: "active", resources: [...]}

        OB->>RI: get_resources_for_service(svc_id)
        RI-->>OB: [VRF, BGP_Session, IP_Subnet, Interface]

        par Health Check — Multiple MCPs
            OB->>MCP: check_resource_health(resource)
            MCP->>NB: verify IP allocation still valid
            NB-->>MCP: IP 10.100.1.0/30 still assigned to VRF CUST-SJC-CORP
        and
            MCP->>AN: check_mode playbook → verify VRF config
            AN-->>MCP: VRF config matches expected state
        and
            MCP->>DEV: get_bgp_state(device="sfo-pe-01", vrf="CUST-SJC-CORP")
            DEV-->>MCP: BGP state: Established, 12 prefixes received
        end

        MCP-->>OB: HealthReport {resource: "BGP_Session", state: "HEALTHY"}
        OB->>OB: Update last_checked timestamp in Redis

        alt Resource DEGRADED
            MCP->>DEV: get_bgp_state(device="lax-pe-02", vrf="CUST-LAX-CORP")
            DEV-->>MCP: BGP state: Idle (Admin) — 0 prefixes

            MCP-->>OB: HealthReport {resource: "BGP_Session", state: "DEGRADED",<br/>  detail: "BGP session down. Last flap: 5 minutes ago. 0 prefixes."}

            OB->>ALERT: raise_alert(
            Note over ALERT: severity: "warning"<br/>resource: "BGP_Session CUST-LAX-CORP"<br/>device: "lax-pe-02"<br/>state: DEGRADED<br/>detail: "BGP session Idle (Admin). 0 prefixes received."
            )

            ALERT->>ALERT: Check alert threshold
            Note over ALERT: Same resource degraded 3+ consecutive checks → escalate to CRITICAL

            ALERT->>ALERT: Dispatch notifications
            Note over ALERT: 1. Slack: #telco-orchestrator → "⚠️ BGP Session CUST-LAX-CORP DEGRADED"<br/>2. Telegram: ops channel → full detail<br/>3. CRM webhook: ServiceOrderJeopardyEvent if SLA at risk

            OB->>SI: update_service_health(svc_id, "DEGRADED")
        end
    end

    OB->>OB: Generate assurance report
    Note over OB: Summary:<br/>Total checked: 247<br/>Healthy: 243<br/>Degraded: 4<br/>Critical: 0<br/>New alerts: 2<br/>Escalated: 0

    OB->>ALERT: POST assurance report to Slack #daily-reports
```

---

## 6. Data Flow Diagrams

### 6.1 End-to-End Data Flow: CRM → Decomposition → Fulfillment → Callback

```mermaid
flowchart LR
    subgraph INPUT["1. INGRESS"]
        A["CRM POST<br/>TMF622 ProductOrder<br/>JSON"]
    end

    subgraph DECOMP["2. DECOMPOSITION"]
        B["OrderManager<br/>validate_tmf622()"]
        C["OrderDecomposer<br/>decompose_product_order()"]
        D["ProductCatalog<br/>find_by_id()"]
    end

    subgraph QUEUE["3. QUEUING"]
        E["PostgreSQL<br/>INSERT product_orders,<br/>service_orders"]
        F["RabbitMQ<br/>publish to<br/>orders.standard"]
    end

    subgraph PIPELINE["4. PIPELINE (14 STAGES)"]
        G["PARSE → MASK<br/>→ CACHE → QUERY"]
        H["RAG → LLM<br/>→ HYDRATE → LOCK"]
        I["MERGE → VALIDATE<br/>→ EXECUTE → NOTIFY<br/>→ VERIFY"]
    end

    subgraph MCP_EXEC["5. MCP EXECUTION"]
        J["NetBox MCP<br/>IP/subnet allocation"]
        K["Ansible MCP<br/>Device config push"]
        L["Cisco NSO MCP<br/>Service activation"]
        M["Device MCP<br/>Verification"]
    end

    subgraph PERSIST["6. PERSISTENCE"]
        N["PostgreSQL<br/>UPDATE service_inventory,<br/>resource_inventory,<br/>audit_log"]
        O["Redis<br/>SET pattern:<br/>confidence, use_count"]
        P["KB FS<br/>Lessons learned"]
    end

    subgraph OUTPUT["7. OUTPUT"]
        Q["WebhookManager<br/>POST TMF641 event<br/>→ CRM callback URL"]
        R["Platform Gateways<br/>Telegram, Discord, Slack"]
        S["Frontend Dashboard<br/>Next.js → REST API"]
    end

    A --> B
    B --> C
    C --> D
    D --> C
    C --> E
    E --> F
    F --> G
    G --> H
    H --> I
    I --> J
    I --> K
    I --> L
    I --> M
    I --> N
    I --> O
    I --> P
    N --> Q
    O --> S
    Q --> A
    Q --> R
```

### 6.2 Data Sovereignty Boundary: What Leaves vs. Stays Local

```mermaid
flowchart TB
    subgraph LOCAL["🔒 LOCAL PERIMETER — Never Leaves"]
        direction TB
        L1["Real Identifiers<br/>━━━━━━━━━━<br/>MSISDN: 447700123456<br/>IMSI: 234151234567890<br/>IP: 10.100.1.1<br/>Hostname: sfo-pe-01<br/>Customer ASN: 65002"]
        L2["Token Map<br/>━━━━━━━━━━<br/>VAR_MSISDN_1 → 447700123456<br/>VAR_IP_1 → 10.100.1.1<br/>VAR_HOST_1 → sfo-pe-01<br/>Wiped when request completes"]
        L3["Hydrated Plan<br/>━━━━━━━━━━<br/>Full device configs<br/>Real IPs, ASNs, hostnames<br/>Workflow parameters"]
        L4["KB (read-only)<br/>━━━━━━━━━━<br/>ontologies/<br/>products/<br/>workflows/"]
        L5["PostgreSQL<br/>━━━━━━━━━━<br/>product_catalog<br/>service_inventory<br/>resource_inventory"]
        L6["Redis<br/>━━━━━━━━━━<br/>pattern_store<br/>subscriber_locks"]
    end

    subgraph CLOUD["☁️ CLOUD PERIMETER — Crosses Boundary"]
        direction TB
        C1["Masked Request<br/>━━━━━━━━━━<br/>'Provision L3VPN for VAR_MSISDN_1<br/>site VAR_HOST_1, bandwidth 1000 Mbps,<br/>routing BGP, customer ASN VAR_ASN_1'"]
        C2["KB Context (non-sensitive)<br/>━━━━━━━━━━<br/>Domain knowledge:<br/>• Required NEs for L3VPN<br/>• Segment/SLA attribute overrides<br/>• Workflow templates<br/>NO real values"]
        C3["LLM Response<br/>━━━━━━━━━━<br/>JSON plan with VAR_* tokens<br/>Workflow names, device types<br/>Attribute schemas (no real values)"]
        C4["Deepseek v4 Pro<br/>━━━━━━━━━━<br/>Cloud AI reasoning<br/>Operates on masked data only"]
    end

    L1 -->|"DataMasker.mask()<br/>tokenizes identifiers"| C1
    L4 -->|"KBContextLoader<br/>injects domain knowledge"| C2
    C1 -->|"call_deepseek()<br/>via hermes chat"| C4
    C2 -->|"Prompt injection<br/>attribute names only"| C4
    C4 -->|"JSON response<br/>VAR_* tokens"| C3
    C3 -->|"DataMasker.hydrate()<br/>restores real values"| L3
    L2 -->|"NEVER serialized<br/>NEVER leaves process"| LOCAL

    style LOCAL fill:rgba(34,197,94,0.08),stroke:rgba(34,197,94,0.4),stroke-width:2px
    style CLOUD fill:rgba(239,68,68,0.08),stroke:rgba(239,68,68,0.3),stroke-width:2px
```

### 6.3 PostgreSQL Schema Data Flow

```mermaid
flowchart LR
    subgraph CRM_EVENT["CRM → Order"]
        PO["product_orders<br/>━━━━━━━━━━<br/>id, external_id, state,<br/>customer_id, callback_url,<br/>order_data (JSONB)"]
    end

    subgraph DECOMP["Decomposition"]
        SO["service_orders<br/>━━━━━━━━━━<br/>id, product_order_id,<br/>parent_order_id, state,<br/>action, product_id,<br/>characteristics (JSONB),<br/>audit_log (JSONB)"]
    end

    subgraph FULFILL["Fulfillment"]
        SI["service_inventory<br/>━━━━━━━━━━<br/>id, service_order_id,<br/>customer_id, product_id,<br/>state, service_characteristics"]
        RI["resource_inventory<br/>━━━━━━━━━━<br/>id, service_id,<br/>resource_type, device_name,<br/>config (JSONB), state"]
    end

    subgraph AUDIT["Audit & Webhooks"]
        AL["audit_log<br/>━━━━━━━━━━<br/>order_id, event_type,<br/>old_state, new_state,<br/>message, timestamp"]
        WD["webhook_deliveries<br/>━━━━━━━━━━<br/>order_id, event_type,<br/>callback_url, payload (JSONB),<br/>response_code, retry_count"]
    end

    subgraph CATALOG["Product Catalog"]
        PC["product_catalog<br/>━━━━━━━━━━<br/>id, name, category,<br/>service_template,<br/>decomposition_rules (JSONB),<br/>required_resources (JSONB)"]
    end

    PO -->|"1:N"| SO
    PC -->|"lookup"| SO
    SO -->|"1:1"| SI
    SI -->|"1:N"| RI
    SO -->|"1:N"| AL
    SO -->|"1:N"| WD
    PO -->|"1:N"| WD
    PO -->|"1:N"| AL
```

---

## 7. Deployment Architecture

### 7.1 VPS Topology (Production Target)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HOST: VPS / Bare-Metal Server                     │
│                        OS: Ubuntu 24.04 LTS                              │
│                        CPU: 8 vCPUs | RAM: 32 GB | SSD: 200 GB          │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     Docker Compose Stack                            │ │
│  │                                                                     │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │ │
│  │  │  Nginx    │  │ FastAPI   │  │ FastAPI   │  │ FastAPI   │       │ │
│  │  │  :443     │  │ App :8001 │  │ App :8002 │  │ App :8003 │       │ │
│  │  │  TLS      │  │ (Gunicorn │  │ (Gunicorn │  │ (Gunicorn │       │ │
│  │  │  Reverse  │  │  +Uvicorn)│  │  +Uvicorn)│  │  +Uvicorn)│       │ │
│  │  │  Proxy    │  │           │  │           │  │           │       │ │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘       │ │
│  │        │              │              │              │              │ │
│  │        └──────────────┼──────────────┼──────────────┘              │ │
│  │                       │              │                              │ │
│  │  ┌────────────────────┼──────────────┼──────────────────────────┐  │ │
│  │  │           RabbitMQ :5672  :15672 (management)                │  │ │
│  │  │           ┌────────┴──────┴───────┐                          │  │ │
│  │  │           │  Exchange: orders      │                          │  │ │
│  │  │           │  ├─ orders.urgent      │                          │  │ │
│  │  │           │  ├─ orders.standard    │                          │  │ │
│  │  │           │  ├─ orders.bulk        │                          │  │ │
│  │  │           │  ├─ orders.retry       │                          │  │ │
│  │  │           │  └─ webhooks           │                          │  │ │
│  │  │           └────────────────────────┘                          │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  │                                                                     │ │
│  │  ┌──────────────────────────┐  ┌──────────────────────────────┐   │ │
│  │  │  PostgreSQL 16 :5432     │  │  Redis 7 :6379               │   │ │
│  │  │  ┌────────────────────┐  │  │  ┌────────────────────────┐  │   │ │
│  │  │  │ product_catalog    │  │  │  │ Task Queue (RQ)        │  │   │ │
│  │  │  │ service_inventory  │  │  │  │ Session Cache          │  │   │ │
│  │  │  │ resource_inventory │  │  │  │ Rate Limit Counters    │  │   │ │
│  │  │  │ product_orders     │  │  │  │ Subscriber Locks       │  │   │ │
│  │  │  │ service_orders     │  │  │  │ Pattern Store Cache    │  │   │ │
│  │  │  │ webhook_deliveries │  │  │  │ Pub/Sub Notifications  │  │   │ │
│  │  │  │ audit_log          │  │  │  └────────────────────────┘  │   │ │
│  │  │  └────────────────────┘  │  │                              │   │ │
│  │  └──────────────────────────┘  └──────────────────────────────┘   │ │
│  │                                                                     │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │  Worker Pool (Hermes Agent Subprocesses)                     │  │ │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │  │ │
│  │  │  │Worker-1  │ │Worker-2  │ │Worker-3  │ │Worker-N  │        │  │ │
│  │  │  │Profile:A │ │Profile:A │ │Profile:B │ │Profile:N │        │  │ │
│  │  │  │Skills:   │ │Skills:   │ │Skills:   │ │Skills:   │        │  │ │
│  │  │  │telecom-  │ │telecom-  │ │telecom-  │ │telecom-  │        │  │ │
│  │  │  │prov      │ │prov      │ │prov      │ │prov      │        │  │ │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  │                                                                     │ │
│  │  ┌──────────────────────────┐  ┌──────────────────────────────┐   │ │
│  │  │  MCP Servers             │  │  Frontend (Next.js) :3000    │   │ │
│  │  │  ├─ NetBox :8080         │  │  Production build served     │   │ │
│  │  │  ├─ Ansible Runner       │  │  by Nginx or Node server     │   │ │
│  │  │  ├─ Cisco NSO :8080      │  │                              │   │ │
│  │  │  └─ OSM :9999            │  │                              │   │ │
│  │  └──────────────────────────┘  └──────────────────────────────┘   │ │
│  │                                                                     │ │
│  │  ┌──────────────────────────────────────────────────────────────┐  │ │
│  │  │  Knowledge Base Volume (:ro mount)                           │  │ │
│  │  │  /opt/data/telecom-orchestrator/knowledge-base/              │  │ │
│  │  │  ├── ontologies/  ├── products/  ├── workflows/              │  │ │
│  │  │  ├── resources/   ├── services/  └── lessons/                │  │ │
│  │  └──────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Docker Compose Configuration (Key Services)

```yaml
# docker-compose.yml — Production Stack
version: "3.9"

services:
  nginx:
    image: nginx:1.27-alpine
    ports: ["443:443"]
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    depends_on: [api]
    restart: unless-stopped

  api:
    build: .
    command: gunicorn src.api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
    expose: ["8000"]
    environment:
      - DATABASE_URL=postgresql://orch:${DB_PASS}@postgres:5432/orchestrator
      - REDIS_URL=redis://redis:6379/0
      - RABBITMQ_URL=amqp://orch:${MQ_PASS}@rabbitmq:5672/
      - HERMES_PROFILE=tenant-a
    depends_on: [postgres, redis, rabbitmq]
    restart: unless-stopped

  worker:
    build: .
    command: python -m src.workers.hermes_worker
    environment:
      - DATABASE_URL=postgresql://orch:${DB_PASS}@postgres:5432/orchestrator
      - REDIS_URL=redis://redis:6379/0
      - RABBITMQ_URL=amqp://orch:${MQ_PASS}@rabbitmq:5672/
      - HERMES_PROFILE=tenant-a
      - WORKER_CONCURRENCY=4
    depends_on: [postgres, redis, rabbitmq]
    deploy:
      replicas: 3
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: orch
      POSTGRES_PASSWORD: ${DB_PASS}
      POSTGRES_DB: orchestrator
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./db/migrations:/docker-entrypoint-initdb.d:ro
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: unless-stopped

  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    environment:
      RABBITMQ_DEFAULT_USER: orch
      RABBITMQ_DEFAULT_PASS: ${MQ_PASS}
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=https://api.example.com
    depends_on: [api]
    restart: unless-stopped

  netbox:
    image: netboxcommunity/netbox:v4.1
    ports: ["8080:8080"]
    environment:
      DB_NAME: netbox
      DB_USER: netbox
      DB_PASSWORD: ${NB_DB_PASS}
    depends_on: [postgres, redis]

volumes:
  pg_data:
  redis_data:
  rabbitmq_data:
```

### 7.3 Startup Sequence

1. **PostgreSQL** starts → runs migrations from `db/migrations/` → creates tables
2. **Redis** starts → loads AOF file if present → ready for connections
3. **RabbitMQ** starts → declares exchanges: `orders` (topic), `webhooks` (topic) → declares 5 queues with bindings
4. **NetBox** starts → connects to PostgreSQL → exposes REST API on :8080
5. **FastAPI App** (×3 replicas) starts → connects to PG + Redis + RMQ → begins accepting requests
6. **Nginx** starts → loads TLS certs → begins proxying :443 → :8000
7. **Worker Pool** (×3 replicas) starts → connects to RMQ → begins consuming `orders.standard`
8. **Cron Scheduler** starts → registers jobs: assurance (every 15m), discovery (every 6h), capacity (every 24h), pattern GC (every 1h)
9. **Frontend** starts → Next.js production build → serves dashboard on :3000
10. **Health Check** → `GET /health` returns `{"status":"ok","pg":"connected","redis":"connected","rmq":"connected"}`

---

## 8. Script Call References

Every pipeline stage references a specific module and method. This defines the contract for the `src/` modular architecture.

### 8.1 Core Orchestrator

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/engine/orchestrator_brain.py` | `OrchestratorBrain.run(request)` | Entry point for all pipeline stages; orchestrates the 14-stage flow | ALL (0–13) |
| `src/engine/orchestrator_brain.py` | `OrchestratorBrain.parse_intent(raw)` | Classify TMF622 vs TMF640 vs TMF641 vs unstructured text | STAGE 0 |
| `src/engine/orchestrator_brain.py` | `OrchestratorBrain.cascade_merge(plan, chars, prev_model)` | Merge request characteristics + previous model into plan params | STAGE 9 |
| `src/engine/orchestrator_brain.py` | `OrchestratorBrain.verify_and_persist(result)` | Build NE cards, compute diff, persist to PG + Redis | STAGE 13 |

### 8.2 Order Decomposition

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/engine/order_decomposer.py` | `OrderDecomposer.decompose_product_order(tmf622_order)` | Decompose TMF622 ProductOrder → list of TMF641 ServiceOrders | STAGE 1 |
| `src/engine/order_decomposer.py` | `OrderDecomposer.generate_child_orders(product, chars)` | Generate child ServiceOrders from product decomposition rules | STAGE 1 |
| `src/engine/order_decomposer.py` | `OrderDecomposer.resolve_dependencies(orders)` | Build DAG of ServiceOrder dependencies for parallel dispatch | STAGE 1 |

### 8.3 Pattern Engine & Cache

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/engine/pattern_engine.py` | `PatternEngine.lookup(svc, chars)` | Jaccard similarity match against RDF pattern store in Redis | STAGE 3 |
| `src/engine/pattern_engine.py` | `PatternEngine.learn(svc, chars, plan, all_chars, source)` | Create new PatternNode from LLM-generated plan (auto-learned) | STAGE 13 |
| `src/engine/pattern_engine.py` | `PatternEngine.reinforce(pattern)` | Boost confidence on cache hit (+0.05 per HIT, cap 0.95) | STAGE 3 |
| `src/engine/pattern_engine.py` | `PatternEngine.teach(triples, source)` | Manual knowledge injection (confidence=0.90) | Admin API |
| `src/engine/pattern_engine.py` | `PatternEngine._match_score(pat_chars, req_chars)` | Jaccard similarity: intersection/union on service-defining chars | STAGE 3 |

### 8.4 Data Sovereignty

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/security/data_masker.py` | `DataMasker.mask(text)` | Tokenize MSISDN, IMSI, IP, hostname → VAR_* tokens; return (masked_text, token_map) | STAGE 2 |
| `src/security/data_masker.py` | `DataMasker.hydrate(text, token_map)` | Reverse VAR_* tokens → real values from local token_map | STAGE 7 |
| `src/security/data_masker.py` | `DataMasker.tokenize_batch(items)` | Batch tokenization for array fields in plan params | STAGE 2 |

### 8.5 LLM Integration

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/engine/deepseek_client.py` | `DeepseekClient.call_deepseek(prompt, timeout=90)` | Invoke Deepseek v4 Pro via `hermes chat` CLI; returns JSON plan or "" on failure | STAGE 6 |
| `src/engine/deepseek_client.py` | `DeepseekClient.fallback_plan(svc)` | Generate KB-derived plan when Deepseek unavailable | STAGE 6 (fallback) |
| `src/engine/kb_context.py` | `KBContextLoader.load_kb_context(svc)` | Load domain knowledge from KB files + PostgreSQL product template | STAGE 5 |
| `src/engine/kb_context.py` | `KBContextLoader.load_product_template(product_id)` | Load TOSCA/YAML product template from KB | STAGE 5 |
| `src/engine/kb_context.py` | `KBContextLoader.load_workflow_defs(svc)` | Load workflow definitions for service type | STAGE 5 |

### 8.6 Validation & Security

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/security/validation_gateway.py` | `ValidationGateway.validate_plan(plan, masked_text)` | Scan plan + masked text against BLOCKED_KEYWORDS; return ValidationResult | STAGE 10 |
| `src/security/validation_gateway.py` | `ValidationGateway.schema_enforce(plan, schema)` | Validate plan against Pydantic schema per product type | STAGE 10 |
| `src/security/validation_gateway.py` | `ValidationGateway.check_destructive_commands(text)` | Deep scan for destructive patterns (reload, erase, format, shutdown, etc.) | STAGE 10 |
| `src/security/subscriber_lock.py` | `SubscriberLock.acquire(subscriber_id, worker_id)` | Redis-based per-subscriber advisory lock (30s TTL, 5s retry) | STAGE 8 |

### 8.7 MCP Execution

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/mcp/mcp_dispatcher.py` | `MCPDispatcher.execute_workflow(plan)` | Dispatch orchestration plan to MCP servers for execution | STAGE 11 |
| `src/mcp/mcp_dispatcher.py` | `MCPDispatcher.dispatch_parallel(workflows)` | Execute independent workflows in parallel across MCP servers | STAGE 11 |
| `src/mcp/mcp_dispatcher.py` | `MCPDispatcher.rollback_on_failure(results)` | Execute rollback workflows if any step fails | STAGE 11 |
| `src/mcp/netbox_client.py` | `NetBoxClient.find_available_ip()` / `allocate_prefix()` / `create_device()` | IPAM/DCIM operations via NetBox REST API | STAGE 11 |
| `src/mcp/ansible_client.py` | `AnsibleClient.run_playbook()` / `check_mode()` / `gather_facts()` | Device configuration via Ansible playbooks | STAGE 11 |
| `src/mcp/nso_client.py` | `NSOClient.create_service()` / `sync_from_device()` / `commit_dry_run()` | Multi-vendor service activation via Cisco NSO | STAGE 11 |
| `src/mcp/osm_client.py` | `OSMClient.instantiate_ns()` / `scale_vnf()` / `terminate_ns()` | NFV orchestration via OSM | STAGE 11 |
| `src/mcp/device_client.py` | `DeviceClient.send_config()` / `get_state()` / `validate_commit()` | Direct device CLI/NETCONF/gNMI access | STAGE 11 |

### 8.8 Notifications & Webhooks

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/notifications/notifier.py` | `LifecycleNotifier.build_notification_trace(order_id, svc, subscriber_id, t0)` | Walk KB lifecycle states, emit milestones + state change events | STAGE 12 |
| `src/notifications/notifier.py` | `LifecycleNotifier.emit_milestone(state, svc, order_id)` | Build TMF641 ServiceOrderMilestoneEvent | STAGE 12 |
| `src/notifications/notifier.py` | `LifecycleNotifier.emit_state_change(to_state, svc, order_id)` | Build TMF641 ServiceOrderStateChangeEvent | STAGE 12 |
| `src/notifications/webhook_manager.py` | `WebhookManager.dispatch_callback(order, event)` | POST TMF641 event to CRM-registered callback URL with HMAC signature | STAGE 12 |
| `src/notifications/webhook_manager.py` | `WebhookManager.retry_exponential(delivery_id)` | Retry failed webhook with exponential backoff: 5s, 10s, 20s (3 total) | STAGE 12 |
| `src/notifications/webhook_manager.py` | `WebhookManager.dead_letter_queue()` | Re-queue failed deliveries for manual replay | Cron |

### 8.9 Inventory Layer

| Module | Class/Function | Role | Pipeline Stage |
|--------|---------------|------|----------------|
| `src/inventory/product_catalog.py` | `ProductCatalog.find_by_id(product_id)` | Look up product definition + decomposition rules from PG | STAGE 1 |
| `src/inventory/product_catalog.py` | `ProductCatalog.get_decomposition_rules(product_id)` | Get JSONB decomposition rules for order splitting | STAGE 1 |
| `src/inventory/service_inventory.py` | `ServiceInventory.get_service(service_id)` | Load service instance with full characteristic + resource graph | STAGE 4 |
| `src/inventory/service_inventory.py` | `ServiceInventory.create_service(order, chars)` | Create new service instance record in PG | STAGE 13 |
| `src/inventory/service_inventory.py` | `ServiceInventory.update_state(service_id, state, audit)` | Transition service state + append audit log entry | STAGE 13 |
| `src/inventory/resource_inventory.py` | `ResourceInventory.allocate_resource(type, params)` | Allocate a logical resource (VRF, IP, VLAN, BGP session) | STAGE 11 |
| `src/inventory/resource_inventory.py` | `ResourceInventory.update_state(resource_id, state)` | Update resource lifecycle state | STAGE 11 |
| `src/inventory/order_history.py` | `OrderHistory.create_order(tmf_data)` | Insert product_order or service_order row | STAGE 1 |
| `src/inventory/order_history.py` | `OrderHistory.update_state(order_id, state, audit)` | Update order state + append to JSONB audit_log | STAGE 12 |
| `src/inventory/audit_log.py` | `AuditLog.log_event(order_id, event_type, old_state, new_state, message)` | Append structured audit event | ALL stages |

### 8.10 Cron Jobs

| Module | Class/Function | Role | Schedule |
|--------|---------------|------|----------|
| `src/cron/assurance.py` | `assurance_health_sweep()` | Query all active services, check resource health via MCP, alert on degradation | Every 15 min |
| `src/cron/discovery.py` | `resource_discovery_sweep()` | Scan network via NetBox/Device MCP, sync new/changed resources to inventory | Every 6 hours |
| `src/cron/capacity.py` | `capacity_trend_analysis()` | Analyze resource utilization trends, predict exhaustion, raise threshold alerts | Every 24 hours |
| `src/cron/maintenance.py` | `pattern_garbage_collection()` | Purge stale patterns (unused > 90 days, confidence < 0.1), compact Redis hashes | Every 1 hour |
| `src/cron/maintenance.py` | `webhook_dead_letter_replay()` | Replay dead-lettered webhook deliveries (max 3 attempts/day per entry) | Every 30 min |

---

## 9. Roadmap: PoC → End-State

### 9.1 Phase Summary

| Phase | Name | Status | Key Deliverables | Est. Effort |
|-------|------|--------|-----------------|-------------|
| **1** | PoC: Single-File Server + Web UI | ✅ **DONE** | `poc/server_live.py` (1,848 lines), `poc/static/index.html` (727 lines), 10-stage pipeline, diskcache, ThreadPoolExecutor | Complete |
| **2** | Modular `src/` Architecture + Tests | ⬜ Not Started | Decompose into `src/api/`, `src/engine/`, `src/inventory/`, `src/mcp/`, `src/notifications/`, `src/security/`, `src/catalog/`, `src/workers/`, `src/cron/`; `tests/` with pytest; CI pipeline | 3–4 weeks |
| **3** | MCP Server Integration | ⬜ Not Started | NetBox MCP (IPAM/DCIM), Ansible MCP (device config), Cisco NSO MCP (service activation), OSM MCP (NFV), Device MCP (SSH/NETCONF); real EXECUTE stage | 4–6 weeks |
| **4** | Product Catalog + Resource Inventory | ⬜ Not Started | PostgreSQL schema creation + migrations; product catalog population (7 products); service/resource inventory CRUD; order history; audit log | 2–3 weeks |
| **5** | TMF622 Decomposition + CRM Webhooks | ⬜ Not Started | OrderDecomposer engine (ProductOrder → ServiceOrder DAG); RabbitMQ queues + Hermes workers; WebhookManager (CRM callback with HMAC, retry, dead-letter); Gateway integration (Telegram, Discord, Slack) | 3–4 weeks |
| **6** | Cron Jobs + Multi-Profile | ⬜ Not Started | Service assurance sweeps, resource discovery, capacity analysis, pattern GC; multi-profile isolation; Knowledge Base population (products/, workflows/, resources/, services/, lessons/) | 2–3 weeks |
| **7** | Frontend + Docs + Production Hardening | ⬜ Not Started | React/Next.js dashboard (Order Management, Service Inventory, Resource Topology, Trace Viewer, Pattern Analytics); Docker Compose production stack; load testing (5 TPS target); comprehensive documentation | 3–4 weeks |

### 9.2 Detailed Phase Breakdown

#### Phase 1: PoC (DONE) ✅

- Single-file FastAPI server with 10-stage async pipeline
- Single-file HTML/JS web UI with trace viewer, NE cards, notification timeline
- diskcache (SQLite) for pattern store + subscriber models
- ThreadPoolExecutor (4 workers) for background processing
- Deepseek v4 Pro via `hermes chat` subprocess
- 4 KB-seeded patterns (mobile, l3vpn, sdwan, broadband)
- Service domain: Mobile Voice (6 NEs) operational; others defined but not tested

#### Phase 2: Modular src/ + Tests

- **src/api/** — FastAPI routers: `tmf622.py`, `tmf641.py`, `tmf640.py`, `tmf638.py`, `tmf639.py`
- **src/api/gateway.py** — API key auth middleware, rate limiter, request logger
- **src/engine/orchestrator_brain.py** — Refactored 14-stage pipeline from `_run_background_inner`
- **src/engine/order_decomposer.py** — TMF622 decomposition engine (stubbed until Phase 5)
- **src/engine/pattern_engine.py** — Extracted from `PatternEngine`, Redis-backed
- **src/engine/deepseek_client.py** — Extracted `call_deepseek()` with Pydantic response models
- **src/engine/kb_context.py** — Extracted `load_kb_context()` with PostgreSQL integration
- **src/security/data_masker.py** — Extracted `DataMasker` with added `hydrate()` method
- **src/security/validation_gateway.py** — Extracted BLOCKED_KEYWORDS scan + Pydantic schema validation
- **src/security/subscriber_lock.py** — Extracted `SubscriberLock`, Redis-backed
- **src/inventory/** — SQLAlchemy models for PG tables (read-only stubs until Phase 4)
- **src/notifications/notifier.py** — Extracted `LifecycleNotifier`
- **src/notifications/webhook_manager.py** — Webhook dispatch skeleton (active in Phase 5)
- **src/mcp/** — MCP client abstractions (stubs until Phase 3)
- **src/workers/** — Hermes worker consuming from RMQ
- **tests/unit/** — pytest: `test_data_masker.py`, `test_validation_gateway.py`, `test_pattern_engine.py`, `test_order_decomposer.py`
- **tests/integration/** — `test_pipeline_cache_hit.py`, `test_pipeline_cache_miss.py`, `test_pipeline_security_block.py`
- **tests/contract/** — TMF622/TMF641 schema validation tests
- **tests/load/** — locust: `locustfile.py` targeting 5 TPS

#### Phase 3: MCP Server Integration

- **NetBox MCP** — Python client wrapping NetBox REST API: IP prefix allocation, device lookups, interface assignment
- **Ansible MCP** — Subprocess runner for `ansible-playbook` with JSON output parsing, check mode support
- **Cisco NSO MCP** — RESTCONF client for NSO service creation, sync-from, commit dry-run
- **OSM MCP** — REST client for ETSI OSM NS instantiation, VNF scaling, termination
- **Device MCP** — netmiko/napalm-based SSH/NETCONF/gNMI client with config push + validation
- **MCPDispatcher** — Parallel dispatch, dependency ordering, rollback on failure
- **EXECUTE stage** — Wired to real MCP execution; stubbed path removed

#### Phase 4: Product Catalog + Resource Inventory

- **PostgreSQL schema** — Run `db/migrations/001_initial_schema.sql`
- **Product catalog population** — 7 products with decomposition rules, required resources, service templates
- **Service inventory** — SQLAlchemy CRUD: create service, update state, find by customer
- **Resource inventory** — SQLAlchemy CRUD: allocate resource, release, find by device
- **Order history** — Create/update product orders and service orders
- **Audit log** — Structured logging for every state transition
- **Redis migration** — Pattern store, subscriber locks, session cache moved from diskcache to Redis
- **diskcache retirement** — Remove `poc/cache_store/` entirely

#### Phase 5: TMF622 Decomposition + CRM Webhooks

- **OrderDecomposer** — Product catalog lookup → decomposition rules → generate ServiceOrder DAG
- **RabbitMQ** — Docker container, 5 queues, topic exchange, dead-letter exchange
- **Hermes Workers** — Multi-process workers consuming from RMQ, invoking OrchestratorBrain.run()
- **WebhookManager** — HMAC-SHA256 signing, POST to CRM callback URL, 3× exponential backoff (5s, 10s, 20s)
- **Dead-letter queue** — Failed webhook deliveries queued for manual replay via admin API
- **Gateway integration** — Telegram bot for ops alerts; Discord/Slack webhooks for team notifications
- **Pipeline stages** — STAGE 1 (DECOMPOSE) active; STAGE 12 (NOTIFY) wired to WebhookManager

#### Phase 6: Cron Jobs + Multi-Profile

- **Cron Scheduler** — Hermes Cron: 4 jobs registered
- **Assurance sweep** — Query all active services → MCP health check → alert on degradation
- **Resource discovery** — NetBox MCP scan → sync new resources to inventory
- **Capacity analysis** — Trend IP pool exhaustion, VLAN depletion, device port utilization
- **Pattern GC** — Purge stale patterns, compact Redis indexes
- **Multi-profile** — Create `tenant-a`, `tenant-b`, `tenant-c` Hermes profiles; each with isolated skills, memory, cron
- **KB population** — Fill `products/`, `workflows/`, `resources/`, `services/`, `lessons/` directories

#### Phase 7: Frontend + Docs + Production Hardening

- **React/Next.js frontend** — Component library, API client, state management (Zustand/React Query)
- **Dashboard modules** — Order Management, Service Inventory, Resource Topology, Trace Viewer, Pattern Analytics
- **Docker Compose** — Production stack with Nginx, FastAPI ×3, Worker ×3, PG, Redis, RMQ, NetBox
- **CI/CD** — GitHub Actions: lint → test → build image → push → deploy → smoke
- **Load testing** — locust: 5 TPS sustained, 50 concurrent orders, cache-hit < 5ms
- **Documentation** — API reference (OpenAPI), operator guide, developer guide, troubleshooting runbook
- **Security hardening** — TLS everywhere, API key rotation, secret management, network policies

### 9.3 Migration Path: Running PoC in Parallel

During Phases 2–7, the PoC server (`poc/server_live.py` on port 8090) continues running alongside the new `src/` architecture on port 8000 (behind Nginx on 443). This allows:

1. **A/B comparison** — Compare PoC pipeline output vs. new pipeline output for the same requests
2. **Gradual cutover** — Route 10% → 50% → 100% of traffic to new architecture via Nginx `split_clients`
3. **Rollback safety** — If new architecture has issues, revert to PoC with an Nginx config change
4. **Data migration** — diskcache patterns can be exported/imported to Redis during cutover

```nginx
# Gradual cutover example
split_clients "${remote_addr}AAA" $backend {
    10%  new_backend;   # Phase 2-3: 10% to new
    *    poc_backend;   # Rest to PoC
}
```

---

## Appendix A: Directory Structure (End-State)

```
/opt/data/telecom-orchestrator/
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app factory
│   │   ├── gateway.py               # Auth middleware, rate limiter
│   │   ├── routers/
│   │   │   ├── tmf622.py            # POST /api/tmf622/productOrder
│   │   │   ├── tmf641.py            # POST/GET /api/tmf641/serviceOrder
│   │   │   ├── tmf640.py            # POST /api/tmf640/serviceActivation
│   │   │   ├── tmf638.py            # GET /api/tmf638/service
│   │   │   ├── tmf639.py            # GET /api/tmf639/resource
│   │   │   ├── patterns.py          # GET/POST /api/patterns
│   │   │   ├── admin.py             # Locks, dead-letter, health
│   │   │   └── webhooks.py          # Webhook delivery status
│   │   └── schemas/
│   │       ├── tmf622.py            # Pydantic: ProductOrder, ProductOrderItem
│   │       ├── tmf641.py            # Pydantic: ServiceOrder, ServiceOrderItem
│   │       └── notifications.py     # Pydantic: StateChangeEvent, MilestoneEvent
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── orchestrator_brain.py    # OrchestratorBrain: 14-stage pipeline
│   │   ├── order_decomposer.py      # OrderDecomposer: TMF622 → [TMF641]
│   │   ├── pattern_engine.py        # PatternEngine: RDF pattern store
│   │   ├── deepseek_client.py       # DeepseekClient: LLM integration
│   │   └── kb_context.py            # KBContextLoader: domain knowledge
│   ├── inventory/
│   │   ├── __init__.py
│   │   ├── models.py                # SQLAlchemy ORM models
│   │   ├── product_catalog.py       # ProductCatalog CRUD
│   │   ├── service_inventory.py     # ServiceInventory CRUD
│   │   ├── resource_inventory.py    # ResourceInventory CRUD
│   │   ├── order_history.py         # OrderHistory CRUD
│   │   └── audit_log.py             # AuditLog writer
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── mcp_dispatcher.py        # MCPDispatcher: parallel execution
│   │   ├── base_client.py           # Abstract MCP client
│   │   ├── netbox_client.py         # NetBox REST API client
│   │   ├── ansible_client.py        # Ansible playbook runner
│   │   ├── nso_client.py            # Cisco NSO RESTCONF client
│   │   ├── osm_client.py            # OSM REST client
│   │   └── device_client.py         # SSH/NETCONF/gNMI client
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── notifier.py              # LifecycleNotifier: TMF641 events
│   │   ├── webhook_manager.py       # WebhookManager: CRM callbacks
│   │   └── gateways.py              # Telegram, Discord, Slack
│   ├── security/
│   │   ├── __init__.py
│   │   ├── data_masker.py           # DataMasker: tokenize/hydrate
│   │   ├── validation_gateway.py    # ValidationGateway: security scan
│   │   └── subscriber_lock.py       # SubscriberLock: Redis advisory lock
│   ├── workers/
│   │   ├── __init__.py
│   │   └── hermes_worker.py         # RQ worker: consume RMQ → OrchestratorBrain
│   ├── cron/
│   │   ├── __init__.py
│   │   ├── assurance.py             # Health sweep cron
│   │   ├── discovery.py             # Resource discovery cron
│   │   ├── capacity.py              # Capacity analysis cron
│   │   └── maintenance.py           # Pattern GC, dead-letter replay
│   └── config.py                    # Settings: DB URL, Redis URL, RMQ URL
├── tests/
│   ├── unit/
│   │   ├── test_data_masker.py
│   │   ├── test_validation_gateway.py
│   │   ├── test_pattern_engine.py
│   │   └── test_order_decomposer.py
│   ├── integration/
│   │   ├── test_pipeline_cache_hit.py
│   │   ├── test_pipeline_cache_miss.py
│   │   └── test_pipeline_security_block.py
│   ├── contract/
│   │   ├── test_tmf622_schema.py
│   │   └── test_tmf641_schema.py
│   └── load/
│       └── locustfile.py
├── db/
│   └── migrations/
│       ├── 001_initial_schema.sql
│       └── 002_seed_product_catalog.sql
├── nginx/
│   ├── nginx.conf
│   └── certs/
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── lib/
│   └── public/
├── knowledge-base/
│   ├── ontologies/
│   │   └── core-ontology.md
│   ├── products/
│   │   ├── prod-l3vpn-01.yaml
│   │   ├── prod-sdwan-01.yaml
│   │   ├── prod-broadband-01.yaml
│   │   ├── prod-mobile-01.yaml
│   │   ├── prod-cloudconnect-01.yaml
│   │   ├── prod-security-01.yaml
│   │   └── prod-transport-01.yaml
│   ├── workflows/
│   │   ├── resource-allocation.md
│   │   ├── device-configuration.md
│   │   ├── bgp-peering.md
│   │   └── service-verification.md
│   ├── resources/
│   │   ├── vrf-template.yaml
│   │   ├── ip-subnet-template.yaml
│   │   └── bgp-session-template.yaml
│   ├── services/
│   ├── lessons/
│   └── reference/
│       ├── standards-index.md
│       ├── tmf-notification-schemas.md
│       ├── implementation-guide.md
│       ├── orchestration-brain-design.md
│       └── solution-design-crm-integration.md
├── documentation/
│   ├── end-state-architectural-blueprint.md   # ← THIS DOCUMENT
│   ├── api-reference.md
│   ├── operator-guide.md
│   └── developer-guide.md
├── docker-compose.yml
├── Dockerfile
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── poc/                                   # Preserved for reference/migration
│   ├── server_live.py
│   ├── static/
│   │   └── index.html
│   └── cache_store/
├── Makefile
├── pyproject.toml
└── README.md
```

---

## Appendix B: Environment Variables

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://orch:pass@localhost:5432/orchestrator` | Yes |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` | Yes |
| `RABBITMQ_URL` | RabbitMQ connection string | `amqp://orch:pass@localhost:5672/` | Yes |
| `HERMES_PROFILE` | Hermes profile name for multi-tenancy | `default` | Yes |
| `WORKER_CONCURRENCY` | Number of Hermes workers per process | `4` | No |
| `DEEPSEEK_TIMEOUT` | LLM call timeout in seconds | `90` | No |
| `WEBHOOK_RETRY_MAX` | Max retry attempts for webhook delivery | `3` | No |
| `WEBHOOK_RETRY_BASE_S` | Base retry delay in seconds | `5` | No |
| `LOCK_TTL` | Subscriber lock TTL in seconds | `30` | No |
| `LOG_LEVEL` | Python logging level | `INFO` | No |
| `API_KEY_HEADER` | Header name for API key auth | `X-API-Key` | No |
| `NEXT_PUBLIC_API_URL` | Frontend API base URL | `http://localhost:8000` | Frontend |

---

## Appendix C: TMF API Coverage Matrix

| TMF API | Standard | Endpoint(s) | Status | Notes |
|---------|----------|-------------|--------|-------|
| **TMF622** | Product Ordering | `POST /api/tmf622/productOrder`, `GET /api/tmf622/productOrder/{id}` | Phase 5 | CRM-triggered product orders |
| **TMF641** | Service Ordering | `POST /api/tmf641/serviceOrder`, `GET /api/tmf641/serviceOrder/{id}`, `POST /api/tmf641/serviceOrder/{id}/cancel` | Phase 2 (refactor) | Internal + external service orders |
| **TMF640** | Service Activation | `POST /api/tmf640/serviceActivation` | Phase 2 (refactor) | Activation configuration |
| **TMF638** | Service Inventory | `GET /api/tmf638/service`, `GET /api/tmf638/service/{id}` | Phase 4 | Read-only service queries |
| **TMF639** | Resource Inventory | `GET /api/tmf639/resource`, `GET /api/tmf639/resource/{id}` | Phase 4 | Read-only resource queries |
| **TMF641 Events** | Notifications | `ServiceOrderStateChangeEvent`, `ServiceOrderMilestoneEvent`, `ServiceOrderJeopardyEvent` | Phase 2 (refactor) | CRM webhook payloads |
| **TMF630** | REST Design Guidelines | Pagination, filtering, HATEOAS links | Phase 7 | Production hardening |

---

> **Document Maintainer:** Orchestration Team
> **Next Review:** After each phase completion
> **Source of Truth:** This document supersedes all PoC-level architecture docs. The PoC documentation at `knowledge-base/system-docs/architecture/blueprint.md` describes the Phase 1 implementation only.
