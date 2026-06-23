# End-State Component Diagram — Telecom Agentic Orchestration Engine

> **Standalone diagram document.** Renders as an interactive Mermaid diagram.
> View in any Mermaid-compatible renderer (GitHub, mermaid.live, VS Code, etc.)

---

## End-State Production Architecture

```mermaid
graph TB
    subgraph ExternalSystems["EXTERNAL SYSTEMS"]
        SF[Salesforce<br/>Communications Cloud]
        DYN[Dynamics 365]
        CRM_CUSTOM[Custom CRM/ERP]
        DEEPSEEK[Deepseek v4 Pro<br/>Cloud AI]
    end

    subgraph Edge["EDGE -- Nginx Reverse Proxy"]
        NGINX[Nginx<br/>TLS 1.3 Termination<br/>Rate Limiting<br/>API Key Validation<br/>Port 443]
    end

    subgraph API["API LAYER -- FastAPI"]
        GW[FastAPI Gateway<br/>CORS Middleware<br/>Request Logging<br/>Auth Middleware]
        TMF622["POST /tmf622/productOrder<br/>GET /tmf622/productOrder/{id}<br/>POST .../{id}/cancel"]
        TMF641["POST /tmf641/serviceOrder<br/>GET /tmf641/serviceOrder/{id}"]
        TMF640["POST /tmf640/service<br/>GET /tmf640/service/{id}"]
        TMF638["GET /tmf638/service<br/>GET /tmf638/service/{id}"]
        TMF639["GET /tmf639/resource<br/>GET /tmf639/resource/{id}"]
        INTERNAL[Internal APIs<br/>patterns, subscribers<br/>locks, notifications<br/>health, metrics]
    end

    subgraph OrderMgr["ORDER MANAGER"]
        DECOMP[OrderDecomposer<br/>TMF622 to TMF641<br/>reads Product Catalog<br/>validates prerequisites<br/>creates child ServiceOrders]
        PRODCAT[ProductCatalog<br/>PostgreSQL<br/>product_catalog table]
    end

    subgraph Queue["MESSAGE QUEUE -- RabbitMQ"]
        RMQ_ORDERS["queue: orders<br/>prefetch=1<br/>fair dispatch"]
        RMQ_RETRY["queue: retry<br/>exponential backoff"]
        RMQ_DEAD["queue: dead-letter<br/>manual intervention"]
        RMQ_ASSUR["queue: assurance<br/>cron-triggered<br/>health checks"]
    end

    subgraph Workers["WORKER POOL -- Hermes Subprocesses"]
        W1["Worker 1<br/>hermes agent<br/>skills loaded"]
        W2["Worker 2<br/>hermes agent<br/>skills loaded"]
        W3["Worker N<br/>hermes agent<br/>skills loaded"]
    end

    subgraph Brain["ORCHESTRATOR BRAIN -- 14-Stage Pipeline"]
        direction TB
        S00[DETECT<br/>format detection<br/>JSON vs text]
        S01[MASK<br/>DataMasker<br/>MSISDN/IP to VAR_*]
        S02["CACHE<br/>PatternEngine.lookup()<br/>Jaccard match"]
        S03[RAG<br/>KBLoader<br/>domain context]
        S04[LLM<br/>DeepseekClient<br/>cache-miss only]
        S05[HYDRATE<br/>Token reversal<br/>VAR_* to real]
        S06[LOCK<br/>SubscriberLock<br/>30s TTL advisory]
        S07[MERGE<br/>Cascade chars<br/>plus prev model attrs]
        S08[VALIDATE<br/>ValidationGateway<br/>blocked keywords]
        S09[EXECUTE<br/>MCPDispatcher<br/>workflow dispatch]
        S10[NOTIFY<br/>LifecycleNotifier<br/>TMF641 events]
        S11[VERIFY<br/>Build NEs plus diff<br/>ServiceModelStore]
        S12[STORE<br/>Release lock<br/>finalize job]
        S13[WEBHOOK<br/>WebhookManager<br/>CRM callback]

        S00 --> S01 --> S02
        S02 -->|HIT| S05
        S02 -->|MISS| S03 --> S04 --> S05
        S05 --> S06 --> S07 --> S08
        S08 -->|PASS| S09 --> S10 --> S11 --> S12 --> S13
        S08 -->|BLOCK| ABORT["ABORT<br/>Alert Ops"]
    end

    subgraph MCP["MCP INTEGRATION LAYER"]
        NETBOX[NetBox MCP<br/>IPAM, DCIM<br/>inventory source of truth]
        ANSIBLE[Ansible MCP<br/>device configuration<br/>playbook execution]
        NSO[Cisco NSO MCP<br/>multi-vendor<br/>service activation]
        OSM[OSM MCP<br/>NFV orchestration<br/>VNF lifecycle]
        DEVICE[Device MCP<br/>SSH CLI, NETCONF<br/>per-device drivers]
    end

    subgraph Network["NETWORK DEVICES"]
        PE[PE Routers<br/>VRF termination<br/>BGP peering]
        HLR[HLR/HSS<br/>subscriber registry]
        OLT_DEV[OLT, BNG<br/>broadband access]
        CPE[vCPE/uCPE<br/>SD-WAN edge]
    end

    subgraph Storage["PERSISTENT STORES"]
        PG[PostgreSQL 16<br/>product_catalog<br/>service_inventory<br/>resource_inventory<br/>order_history<br/>audit_log<br/>webhook_deliveries]
        REDIS[Redis 7<br/>task queues<br/>session cache<br/>rate limiting<br/>subscriber locks<br/>pattern hot cache]
        HERMES_DB[Hermes SQLite<br/>memory, sessions<br/>skills, state.db]
        KB[Knowledge Base<br/>ontologies/, products/<br/>workflows/, standards/<br/>services/, resources/]
    end

    subgraph Cron["CRON SCHEDULER"]
        CRON_ASSUR[Service Assurance<br/>health checks<br/>degradation alerting]
        CRON_DISC[Resource Discovery<br/>network scan<br/>inventory sync]
        CRON_CAP[Capacity Mgmt<br/>threshold monitoring<br/>forecast alerts]
    end

    subgraph Notify["NOTIFICATION LAYER"]
        WEBHOOK[WebhookManager<br/>CRM callbacks<br/>HMAC-SHA256 signed<br/>exponential backoff<br/>dead-letter queue]
        GW_NOTIFY[Gateway Notifier<br/>Telegram to ops channel<br/>Discord to telco-orch<br/>Slack to provisioning]
    end

    subgraph Frontend["FRONTEND -- React/Next.js"]
        DASH[Dashboard<br/>order management<br/>service browser<br/>resource browser]
        TRACE[Trace Viewer<br/>real-time pipeline<br/>WebSocket upgrade<br/>color-coded cards]
        NE_CARDS[NE Cards<br/>diff-highlighted<br/>attribute display]
        PATTERN_PANEL[Pattern Analysis<br/>confidence bars<br/>suggestion engine]
        NOTIF_TIMELINE[Notification Timeline<br/>lifecycle milestones<br/>TMF641 events]
    end

    subgraph CICD["CI/CD PIPELINE"]
        GIT[GitHub/GitLab<br/>source control]
        TEST["Test Suite<br/>unit, integration<br/>E2E, load (5TPS)"]
        DOCKER[Docker Build<br/>container images]
        DEPLOY[Deploy<br/>Docker Compose<br/>rolling updates]
    end

    %% ===== CONNECTIONS =====

    %% Inbound
    SF --> NGINX
    DYN --> NGINX
    CRM_CUSTOM --> NGINX
    NGINX --> GW

    %% API to Order Manager
    GW --> TMF622
    GW --> TMF641
    GW --> TMF640
    GW --> TMF638
    GW --> TMF639
    GW --> INTERNAL
    TMF622 --> DECOMP
    DECOMP <--> PRODCAT
    DECOMP --> RMQ_ORDERS

    %% Queue to Workers
    RMQ_ORDERS --> W1
    RMQ_ORDERS --> W2
    RMQ_ORDERS --> W3
    RMQ_RETRY --> W1
    W1 --> RMQ_RETRY
    W2 --> RMQ_RETRY
    W3 --> RMQ_RETRY
    RMQ_RETRY --> RMQ_DEAD

    %% Worker to Brain
    W1 --> S00
    W2 --> S00
    W3 --> S00

    %% Brain to external
    S04 -.-> DEEPSEEK

    %% Brain to MCP
    S09 --> NETBOX
    S09 --> ANSIBLE
    S09 --> NSO
    S09 --> OSM
    NETBOX --> DEVICE
    ANSIBLE --> PE
    NSO --> HLR
    DEVICE --> OLT_DEV
    DEVICE --> CPE

    %% Brain to Storage
    S02 <--> REDIS
    S06 <--> REDIS
    S11 --> PG
    S11 --> REDIS
    S03 --> KB
    DECOMP <--> PG
    PRODCAT --> KB

    %% Cron
    CRON_ASSUR --> RMQ_ASSUR
    RMQ_ASSUR --> W1
    CRON_DISC --> DEVICE
    CRON_DISC --> PG
    CRON_CAP --> PG
    CRON_CAP --> GW_NOTIFY

    %% Notifications
    S10 --> WEBHOOK
    S13 --> WEBHOOK
    S08 --> GW_NOTIFY
    WEBHOOK -.-> SF
    WEBHOOK -.-> DYN
    WEBHOOK -.-> CRM_CUSTOM
    GW_NOTIFY --> TG["Telegram Ops"]
    GW_NOTIFY --> DC["Discord telco"]
    GW_NOTIFY --> SL["Slack provision"]

    %% Frontend
    GW --> DASH
    GW --> TRACE
    DASH --> TRACE
    DASH --> NE_CARDS
    DASH --> PATTERN_PANEL
    DASH --> NOTIF_TIMELINE
    DASH --> PG

    %% CI/CD
    GIT --> TEST
    TEST --> DOCKER
    DOCKER --> DEPLOY

    %% Styling
    classDef external fill:#c7d2fe,stroke:#6366f1
    classDef edge fill:#bbf7d0,stroke:#22c55e
    classDef api fill:#bfdbfe,stroke:#3b82f6
    classDef pipeline fill:#e2e8f0,stroke:#64748b
    classDef mcp fill:#e9d5ff,stroke:#a855f7
    classDef storage fill:#fecaca,stroke:#ef4444
    classDef notify fill:#a5f3fc,stroke:#06b6d4
    classDef frontend fill:#a7f3d0,stroke:#10b981
    classDef cicd fill:#fed7aa,stroke:#f97316
    classDef workers fill:#ecfccb,stroke:#84cc16

    class SF,DYN,CRM_CUSTOM,DEEPSEEK external
    class NGINX edge
    class GW,TMF622,TMF641,TMF640,TMF638,TMF639,INTERNAL api
    class S00,S01,S02,S03,S04,S05,S06,S07,S08,S09,S10,S11,S12,S13,ABORT pipeline
    class NETBOX,ANSIBLE,NSO,OSM,DEVICE mcp
    class PG,REDIS,HERMES_DB,KB storage
    class WEBHOOK,GW_NOTIFY,TG,DC,SL notify
    class DASH,TRACE,NE_CARDS,PATTERN_PANEL,NOTIF_TIMELINE frontend
    class GIT,TEST,DOCKER,DEPLOY cicd
    class W1,W2,W3 workers
```

---

## Legend

| Color Zone | Layer | Description |
|------------|-------|-------------|
| **Purple** (external) | External Systems | CRM platforms, cloud AI -- outside the VPS perimeter |
| **Green** (edge) | Edge/Nginx | TLS termination, rate limiting, API key validation |
| **Blue** (api) | API Layer | FastAPI gateway, TMF-standard endpoints, internal APIs |
| **Gray** (pipeline) | Pipeline Engine | 14-stage orchestration pipeline |
| **Deep Purple** (mcp) | MCP Integration | Protocol servers bridging to network devices |
| **Red** (storage) | Persistent Stores | PostgreSQL, Redis, Hermes SQLite, KB files |
| **Cyan** (notify) | Notification | CRM webhooks, platform gateways (Telegram/Discord/Slack) |
| **Emerald** (frontend) | Frontend | React/Next.js dashboard with trace viewer |
| **Orange** (cicd) | CI/CD | Test suite, Docker build, deployment |
| **Lime** (workers) | Worker Pool | Hermes agent subprocesses pulling from RabbitMQ |

---

## Component Count

| Layer | Components |
|-------|-----------|
| External Systems | 4 (Salesforce, Dynamics, Custom CRM, Deepseek) |
| Edge | 1 (Nginx) |
| API Layer | 7 (Gateway + 5 TMF + Internal) |
| Order Manager | 2 (Decomposer + ProductCatalog) |
| Message Queue | 4 (orders, retry, dead-letter, assurance) |
| Worker Pool | 3 (W1, W2, WN) |
| Pipeline Engine | 14 stages |
| MCP Integration | 5 servers |
| Network Devices | 4 groups |
| Persistent Stores | 4 systems |
| Cron Scheduler | 3 jobs |
| Notification | 2 dispatchers + 3 platforms |
| Frontend | 5 components |
| CI/CD | 4 stages |
| **TOTAL** | **~70 connected nodes** |

---

> **Source:** Derived from `documentation/end-state-architectural-blueprint.md` and `end-state-component-specification.md`.
> **PoC Reference:** Current implementation at `poc/server_live.py` (1,848 lines) implements 7 of these 14 stages with stubbed MCP/EXECUTE.
