# Solution Design: CRM-Integrated Service & Resource Orchestrator

> Author: Solution Designer | Version: 1.0 | Standards: TM Forum Open APIs, MEF LSO, ETSI NFV MANO

## 1. Executive Summary

A CRM-triggerable service orchestration platform that accepts product orders from any CRM system (Salesforce, Dynamics 365, custom), decomposes them into service orders, fulfills them asynchronously down to the network device level, and reports status back to the CRM. Built on Hermes Agent for reasoning/planning with standards-aligned northbound APIs and MCP-bridged southbound integration.

---

## 2. System Architecture

```
═══════════════════════════════════════════════════════════════════════════
                          NORTHBOUND (CRM-FACING)
═══════════════════════════════════════════════════════════════════════════

   ┌──────────┐    ┌──────────┐    ┌──────────────┐
   │Salesforce│    │ Dynamics │    │Custom CRM/ERP│
   │Comms Cld │    │   365    │    │  (REST client)│
   └────┬─────┘    └────┬─────┘    └──────┬───────┘
        │               │                 │
        │  TMF622       │   TMF622        │  TMF622
        │  Product      │   Product       │  Product
        │  Order        │   Order         │  Order
        │               │                 │
        └───────────────┼─────────────────┘
                        │
              ┌─────────▼──────────┐
              │   API GATEWAY      │  Nginx reverse proxy
              │   (port 443)       │  TLS termination
              │   Rate limiting    │  Auth (API Key / OAuth2)
              │   Request logging  │  CORS
              └─────────┬──────────┘
                        │
═══════════════════════════════════════════════════════════════════════════
                       ORCHESTRATION ENGINE
═══════════════════════════════════════════════════════════════════════════

              ┌─────────▼──────────────────────────────────┐
              │         ORDER MANAGER (FastAPI)            │
              │                                            │
              │  POST /tmf622/productOrder                 │
              │  POST /tmf641/serviceOrder                 │
              │  GET  /tmf641/serviceOrder/{id}            │
              │  POST /tmf641/serviceOrder/{id}/cancel     │
              │  GET  /tmf638/service/{id}                 │
              │  GET  /tmf639/resource/{id}                │
              │                                            │
              │  ┌──────────────────────────────────┐     │
              │  │  ORDER DECOMPOSITION ENGINE       │     │
              │  │  ProductOrder → [ServiceOrder]    │     │
              │  │  Reads product → service mapping   │     │
              │  │  from Product Catalog              │     │
              │  └──────────────┬───────────────────┘     │
              │                 │                          │
              │  ┌──────────────▼───────────────────┐     │
              │  │  TASK QUEUE (Redis + RQ / Celery) │     │
              │  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐     │     │
              │  │  │Job1│ │Job2│ │Job3│ │Job4│     │     │
              │  │  └──┬─┘ └──┬─┘ └──┬─┘ └──┬─┘     │     │
              │  └─────┼──────┼──────┼──────┼───────┘     │
              │        │      │      │      │              │
              └────────┼──────┼──────┼──────┼──────────────┘
                       │      │      │      │
═══════════════════════════════════════════════════════════════════════════
                    FULFILLMENT ENGINE (Hermes Agents)
═══════════════════════════════════════════════════════════════════════════

         ┌─────────────▼──────────────────────────────┐
         │         HERMES AGENT DISPATCHER             │
         │                                             │
         │  Picks up ServiceOrder from queue           │
         │  Loads: telecom-service-provisioning skill  │
         │  7-step agentic loop:                       │
         │    1. Parse intent (from ServiceOrder JSON) │
         │    2. Recall patterns (session_search + mem)│
         │    3. Research KB (product/workflow docs)   │
         │    4. Feasibility check                     │
         │    5. Generate orchestration plan           │
         │    6. Execute via MCP                       │
         │    7. Verify, activate, persist             │
         │                                             │
         │  Reports status back via callback/webhook   │
         └─────────────────┬───────────────────────────┘
                           │
         ┌─────────────────▼───────────────────────────┐
         │           MCP INTEGRATION LAYER              │
         │                                             │
         │  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
         │  │NetBox MCP│ │Ansible   │ │Device MCP   │ │
         │  │(IPAM/DCIM│ │MCP       │ │(CLI/NETCONF │ │
         │  │inventory)│ │(config)  │ │ per-device) │ │
         │  └──────────┘ └──────────┘ └─────────────┘ │
         │                                             │
         │  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
         │  │NSO MCP   │ │OSM MCP   │ │Custom       │ │
         │  │(Cisco    │ │(NFV      │ │vendor MCPs  │ │
         │  │service)  │ │orchest.) │ │             │ │
         │  └──────────┘ └──────────┘ └─────────────┘ │
         └─────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
                        DATA & KNOWLEDGE LAYER
═══════════════════════════════════════════════════════════════════════════

  ┌───────────────────────┐  ┌──────────────────────────┐
  │  PostgreSQL (primary) │  │  Redis                    │
  │  ┌──────────────────┐ │  │  ┌─────────────────────┐  │
  │  │ Product Catalog  │ │  │  │ Task Queue (RQ)     │  │
  │  │ Service Inventory│ │  │  │ Session Cache       │  │
  │  │ Resource Inv.    │ │  │  │ Rate Limit Counters │  │
  │  │ Order History    │ │  │  │ Feasibility Locks   │  │
  │  │ Audit Log        │ │  │  └─────────────────────┘  │
  │  └──────────────────┘ │  │                           │
  └───────────────────────┘  └──────────────────────────┘

  ┌──────────────────────────────────────────────────────┐
  │  Hermes Memory (SQLite via state.db)                 │
  │  ┌────────────────────────────────────────────────┐  │
  │  │ Ontology (service/resource types, patterns)     │  │
  │  │ Provisioning patterns (device configs, BGP, etc)│  │
  │  │ Lessons learned (pitfalls, corrections)         │  │
  │  └────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────┐
  │  Knowledge Base (Markdown files)                     │
  │  ┌────────────────────────────────────────────────┐  │
  │  │ /opt/data/telecom-orchestrator/knowledge-base/  │  │
  │  │   ontologies/  standards/  products/            │  │
  │  │   services/    resources/  workflows/            │  │
  │  └────────────────────────────────────────────────┘  │
  └──────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
                    NOTIFICATION & CALLBACK LAYER
═══════════════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────┐
  │         WEBHOOK DISPATCHER                          │
  │                                                     │
  │  For each state change on ServiceOrder:             │
  │    acknowledged → inProgress → pending               │
  │    → held → cancelled → completed → failed          │
  │                                                     │
  │  1. Looks up registered callback URL from order     │
  │  2. POSTs TMF641 ServiceOrderStateChangeEvent       │
  │  3. Retries with exponential backoff (3x)           │
  │  4. Dead-letter queue for failed deliveries         │
  │                                                     │
  │  Also emits: Hermes Gateway messages (optional)     │
  │    → Telegram to ops channel on failures             │
  │    → Slack to #telco-orchestrator on completions     │
  └─────────────────────────────────────────────────────┘
```

---

## 3. API Design (CRM-Facing)

### 3.1 TMF622 Product Ordering — CRM places an order

```
POST /api/tmf622/productOrder
Authorization: Bearer <crm-api-token>
Content-Type: application/json

{
  "externalId": "CRM-ORDER-12345",
  "priority": "standard",
  "category": "VPN",
  "channel": { "name": "Salesforce" },
  "relatedParty": [
    { "role": "customer", "name": "Acme Corporation", "id": "CUST-0042" }
  ],
  "productOrderItem": [
    {
      "id": "1",
      "action": "add",
      "product": {
        "id": "prod-l3vpn-01",
        "name": "Enterprise MPLS L3VPN"
      },
      "productOffering": {
        "id": "offering-l3vpn-100mbps",
        "name": "MPLS L3VPN 100 Mbps"
      },
      "itemTerm": [
        { "name": "contractDuration", "value": "36" }
      ],
      "characteristic": [
        { "name": "siteName",        "value": "San Jose HQ" },
        { "name": "siteCode",        "value": "SJC" },
        { "name": "bandwidth",       "value": "100" },
        { "name": "bandwidthUnit",   "value": "Mbps" },
        { "name": "targetDevice",    "value": "sfo-pe-01" },
        { "name": "ceDeviceModel",   "value": "cisco-isr-4461" },
        { "name": "routingProtocol", "value": "BGP" },
        { "name": "customerASN",     "value": "65002" },
        { "name": "wanIPSubnet",     "value": "auto-allocate" },
        { "name": "callbackUrl",     "value": "https://crm.acme-corp.com/api/webhooks/telco-order-status" }
      ]
    }
  ]
}
```

Response (202 Accepted):

```json
{
  "id": "ord-20260621-0001",
  "href": "/api/tmf622/productOrder/ord-20260621-0001",
  "state": "acknowledged",
  "externalId": "CRM-ORDER-12345",
  "orderDate": "2026-06-21T14:30:00Z",
  "expectedCompletionDate": "2026-06-21T14:35:00Z",
  "serviceOrder": [
    { "id": "so-l3vpn-0001", "href": "/api/tmf641/serviceOrder/so-l3vpn-0001" }
  ]
}
```

### 3.2 TMF641 Service Ordering — CRM queries status

```
GET /api/tmf641/serviceOrder/so-l3vpn-0001

Response:
{
  "id": "so-l3vpn-0001",
  "state": "completed",
  "externalId": "CRM-ORDER-12345",
  "orderItem": [
    {
      "id": "1",
      "action": "add",
      "state": "completed",
      "service": {
        "id": "svc-acme-sjc-l3vpn",
        "href": "/api/tmf638/service/svc-acme-sjc-l3vpn",
        "state": "active"
      }
    }
  ],
  "serviceOrderRelationship": [
    { "type": "composedOf", "serviceOrder": {
      "id": "so-l3vpn-0001-resource",
      "description": "Resource allocation sub-order",
      "state": "completed"
    }}
  ],
  "auditLog": [
    { "date": "2026-06-21T14:30:01Z", "state": "acknowledged", "message": "Order received, queued for fulfillment" },
    { "date": "2026-06-21T14:30:05Z", "state": "inProgress", "message": "Feasibility check on sfo-pe-01: PASS" },
    { "date": "2026-06-21T14:30:12Z", "state": "inProgress", "message": "Resources allocated: VRF=CUST-SJC-CORP, RD=65001:1001" },
    { "date": "2026-06-21T14:30:45Z", "state": "inProgress", "message": "Configuration pushed to sfo-pe-01 (18 lines)" },
    { "date": "2026-06-21T14:31:02Z", "state": "inProgress", "message": "Verification: BGP Established, 12 prefixes received, ping OK" },
    { "date": "2026-06-21T14:31:05Z", "state": "completed", "message": "Service ACTIVE. Resources: VRF x1, BGP x1, Subnet x1, IF x1" }
  ]
}
```

### 3.3 Webhook Callback — the system pushes to CRM

When state changes, the orchestrator POSTs to the CRM-registered callback URL:

```
POST https://crm.acme-corp.com/api/webhooks/telco-order-status
Content-Type: application/json
X-TMF-Event-Type: ServiceOrderStateChangeEvent
X-Order-Id: so-l3vpn-0001
X-Signature: sha256=abc123...

{
  "eventId": "evt-20260621-00042",
  "eventTime": "2026-06-21T14:31:05Z",
  "eventType": "ServiceOrderStateChangeEvent",
  "event": {
    "serviceOrder": {
      "id": "so-l3vpn-0001",
      "href": "/api/tmf641/serviceOrder/so-l3vpn-0001",
      "externalId": "CRM-ORDER-12345",
      "state": "completed"
    }
  }
}
```

CRM updates its order: Status = "Provisioned", and stores the service ID for future reference.

---

## 4. Internal Component Design

### 4.1 Order Decomposition Engine

```
ProductOrder (TMF622)
  │
  ▼
Product Catalog Lookup (PostgreSQL)
  │  SELECT service_templates FROM product_catalog WHERE product_id = 'prod-l3vpn-01'
  │
  ▼
Decomposition Rules Engine
  │
  │  For each productOrderItem:
  │    1. Look up product → service mapping
  │    2. Generate one or more ServiceOrders (TMF641)
  │    3. Each ServiceOrderItem = one atomic service action
  │    4. Determine dependencies between ServiceOrders
  │    5. Create parent-child ServiceOrder hierarchy
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  Product "Enterprise MPLS L3VPN" decomposes into:          │
│                                                             │
│  ServiceOrder-1 (parent): "Create L3VPN service"            │
│    ├── ServiceOrder-1.1 (child): "Allocate IP resources"    │
│    ├── ServiceOrder-1.2 (child): "Provision VRF on PE"      │
│    ├── ServiceOrder-1.3 (child): "Configure BGP peering"    │
│    ├── ServiceOrder-1.4 (child): "Configure CE interface"   │
│    └── ServiceOrder-1.5 (child): "Verify and activate"      │
│                                                             │
│  Each child → enqueued in order, dependencies respected     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Task Queue Design

```
Redis Queue (RQ) — 5 queues by priority:

  ┌──────────────────────────────────────────────────┐
  │  Queue                 │  Priority │ Concurrency │
  ├────────────────────────┼───────────┼─────────────┤
  │  orders_urgent         │  high     │  1 worker   │
  │  orders_standard       │  normal   │  3 workers  │
  │  orders_bulk           │  low      │  2 workers  │
  │  retry                 │  normal   │  1 worker   │
  │  webhook_delivery      │  normal   │  2 workers  │
  └──────────────────────────────────────────────────┘

Job structure:
{
  "order_id": "so-l3vpn-0001",
  "order_type": "provision_resource",
  "params": {
    "resource_type": "VRF",
    "target_device": "sfo-pe-01",
    "config": { "name": "CUST-SJC-CORP", "rd": "65001:1001", ... }
  },
  "callback_url": "https://crm.acme-corp.com/api/webhooks/...",
  "retry_count": 0,
  "max_retries": 3
}
```

### 4.3 Hermes Agent as Worker

Each RQ worker is a Hermes agent session. The worker:

```python
# Simplified worker loop
from redis import Redis
from rq import Worker, Queue, Connection
import subprocess

redis_conn = Redis(host='localhost', port=6379)
queue = Queue('orders_standard', connection=redis_conn)

class HermesFulfillmentWorker(Worker):
    def execute_job(self, job, queue):
        order = job.args[0]

        # 1. Update state to inProgress
        update_order_state(order['order_id'], 'inProgress')

        # 2. Invoke Hermes as subprocess with the order as context
        result = subprocess.run([
            'hermes', 'chat', '-q',
            f"Fulfill service order {order['order_id']}: "
            f"provision {order['params']['resource_type']} "
            f"on {order['params']['target_device']} "
            f"with config: {order['params']['config']}",
            '-s', 'telecom-service-provisioning',
            '-s', 'telecom-orchestrator-bootstrap',
            '--yolo'
        ], capture_output=True, text=True, timeout=300)

        # 3. Parse result, update state
        if result.returncode == 0:
            update_order_state(order['order_id'], 'completed', audit=result.stdout)
            send_webhook_callback(order['callback_url'], 'completed')
        else:
            if job.meta.get('retry_count', 0) < order['max_retries']:
                raise RetryException  # goes to retry queue
            else:
                update_order_state(order['order_id'], 'failed', audit=result.stderr)
                send_webhook_callback(order['callback_url'], 'failed')
                alert_ops_channel(f"Order {order['order_id']} FAILED: {result.stderr}")
```

### 4.4 Database Schema

```sql
-- Product Catalog
CREATE TABLE product_catalog (
    id          TEXT PRIMARY KEY,  -- 'prod-l3vpn-01'
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,     -- 'VPN', 'Internet', 'Voice', etc.
    description TEXT,
    service_template TEXT,         -- path to TOSCA/YAML template
    decomposition_rules JSONB,     -- how to break into service orders
    required_resources JSONB,      -- [{type: 'VRF', count: 1}, ...]
    supported_devices TEXT[],      -- ['cisco-ios-xr', 'juniper-junos']
    sla_tiers JSONB,               -- [{name: 'standard', max_fulfillment_sec: 600}, ...]
    active      BOOLEAN DEFAULT true
);

-- Product Orders (TMF622)
CREATE TABLE product_orders (
    id              TEXT PRIMARY KEY DEFAULT 'ord-' || to_char(now(), 'YYYYMMDD') || '-' || nextval('order_seq'),
    external_id     TEXT,           -- CRM order reference
    state           TEXT DEFAULT 'acknowledged',
                    -- acknowledged | inProgress | pending | held | cancelled | completed | failed
    priority        TEXT DEFAULT 'standard',  -- urgent | standard | bulk
    category        TEXT,
    customer_id     TEXT,
    customer_name   TEXT,
    callback_url    TEXT,           -- Where CRM wants status updates
    order_data      JSONB,         -- Full original request
    expected_completion TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Service Orders (TMF641)
CREATE TABLE service_orders (
    id              TEXT PRIMARY KEY DEFAULT 'so-' || nextval('service_order_seq'),
    product_order_id TEXT REFERENCES product_orders(id),
    parent_order_id TEXT REFERENCES service_orders(id),  -- NULL for root
    state           TEXT DEFAULT 'acknowledged',
    external_id     TEXT,
    action          TEXT DEFAULT 'add',  -- add | modify | delete | noChange
    product_id      TEXT REFERENCES product_catalog(id),
    service_id      TEXT,           -- Set when service instance created
    characteristics JSONB,         -- Site, bandwidth, device, etc.
    audit_log       JSONB DEFAULT '[]',
    worker_id       TEXT,           -- Which Hermes worker picked it up
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Service Inventory (TMF638)
CREATE TABLE service_inventory (
    id              TEXT PRIMARY KEY DEFAULT 'svc-' || nextval('service_seq'),
    service_order_id TEXT REFERENCES service_orders(id),
    customer_id     TEXT NOT NULL,
    product_id      TEXT REFERENCES product_catalog(id),
    name            TEXT NOT NULL,
    state           TEXT DEFAULT 'designed',
                    -- designed | reserved | provisioning | active | suspended | terminated
    service_characteristics JSONB,
    child_services  JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Resource Inventory (TMF639)
CREATE TABLE resource_inventory (
    id              TEXT PRIMARY KEY DEFAULT 'res-' || nextval('resource_seq'),
    service_id      TEXT REFERENCES service_inventory(id),
    resource_type   TEXT NOT NULL,  -- VRF | BGP_PEER | IP_SUBNET | INTERFACE | VLAN | VNF | ...
    name            TEXT NOT NULL,
    device_name     TEXT,           -- Physical/virtual device
    device_vendor   TEXT,           -- Cisco, Juniper, Nokia, AWS, Azure
    config          JSONB,          -- Actual configuration applied
    state           TEXT DEFAULT 'planned',
                    -- planned | allocated | configuring | in_service | maintenance | decommissioned
    parent_resource_id TEXT REFERENCES resource_inventory(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Webhook Delivery Log
CREATE TABLE webhook_deliveries (
    id              SERIAL PRIMARY KEY,
    order_id        TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    callback_url    TEXT NOT NULL,
    payload         JSONB NOT NULL,
    response_code   INTEGER,
    response_body   TEXT,
    attempt_count   INTEGER DEFAULT 0,
    delivered       BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 5. State Machine & Callback Contract

### 5.1 Order State Transitions

```
                  ┌─────────────┐
  CRM POSTs ───→  │ acknowledged │
                  └──────┬──────┘
                         │ (queued for worker)
                  ┌──────▼──────┐
                  │  inProgress  │──── callback: order.processing
                  └──┬──┬──┬──┬─┘
                     │  │  │  │
              ┌──────┘  │  │  └──────────┐
              │         │  │             │
     ┌────────▼──┐ ┌───▼──▼──┐   ┌──────▼──────┐
     │   held    │ │pending  │   │   completed  │── callback: order.completed
     └───────────┘ └────┬────┘   └──────────────┘
                        │
                 ┌──────▼──────┐
                 │  cancelled  │── callback: order.cancelled
                 └─────────────┘

  On retry exhaustion:
                 ┌─────────────┐
                 │   failed    │── callback: order.failed + alert ops channel
                 └─────────────┘
```

### 5.2 Webhook Callback Specification

Every state change fires exactly one webhook delivery.

```yaml
Webhook Payload:
  eventId: "evt-{timestamp}-{counter}"     # Unique, idempotent
  eventTime: "ISO8601"
  eventType: "ServiceOrderStateChangeEvent"
  correlationId: "{productOrder.id}"        # CRM ties it back
  event:
    serviceOrder:
      id: "{serviceOrder.id}"
      state: "{new_state}"
      auditEntry:                           # Only the delta
        state: "{new_state}"
        message: "Human-readable summary of what just happened"

Delivery Guarantees:
  - At-least-once delivery (CRM must be idempotent on eventId)
  - Retry: 3 attempts with exponential backoff (10s, 30s, 90s)
  - Timeout per attempt: 15 seconds
  - On 3rd failure: dead-letter queue, alert ops

Authentication:
  - HMAC-SHA256 signature in X-Signature header
  - CRM verifies with shared secret
  - Optional: mTLS for high-security deployments
```

---

## 6. Security Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        SECURITY LAYERS                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐  │
│  │ Transport│    │ Authentication│    │   Authorization    │  │
│  │          │    │              │    │                    │  │
│  │ TLS 1.3  │    │ API Key (S2S)│    │ Scope-based tokens │  │
│  │ (mTLS    │    │ OAuth2 (CRM) │    │ read:order         │  │
│  │  opt.)   │    │ HMAC webhook │    │ write:order        │  │
│  │          │    │              │    │ admin:config       │  │
│  └──────────┘    └──────────────┘    └────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                INPUT VALIDATION                          │ │
│  │  Request schema validation (JSON Schema)                 │ │
│  │  Product exists in catalog                               │ │
│  │  Customer exists and is active                           │ │
│  │  Callback URL is whitelisted domain                      │ │
│  │  No SSRF via callback URL                                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              DEVICE ACCESS CONTROL                       │ │
│  │  SSH keys in vault (never in config files)               │ │
│  │  Jump host for device access (no direct from orchestrator)│ │
│  │  Device commands whitelisted per role                    │ │
│  │  All device interactions logged to audit trail           │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. Deployment Architecture on Hostinger VPS

```
Hostinger VPS (KVM-8 recommended: 8 vCPU, 16 GB RAM, 200 GB NVMe)
│
├── Docker Compose stack:
│   │
│   ├── nginx:latest
│   │   Ports: 443 (API), 80→443 redirect
│   │   Volumes: ./nginx/conf.d/, ./certs/
│   │
│   ├── api-gateway (FastAPI)
│   │   Python 3.12 + uvicorn + gunicorn
│   │   Endpoints: TMF622, TMF641, TMF638, TMF639
│   │   Health: /healthz, /readyz
│   │
│   ├── redis:7-alpine
│   │   Task queue backend
│   │   Persistence: AOF enabled
│   │
│   ├── postgresql:16
│   │   Product catalog, orders, inventory
│   │   Replication: streaming to standby (future)
│   │
│   ├── hermes-worker-{1..4}
│   │   Each: hermes-agent + telecom skills
│   │   Each: separate profile (worker-prod-N)
│   │   RQ workers, each picks jobs from Redis
│   │
│   ├── webhook-dispatcher
│   │   Dedicated process for callback delivery
│   │   Handles retries, dead-letter, alerting
│   │
│   └── netbox (optional, separate or same host)
│       IPAM/DCIM source of truth
│       Exposed to Hermes via MCP

├── Monitoring:
│   ├── Prometheus + Grafana (or Hermes `hermes insights`)
│   ├── Order throughput, latency, failure rate dashboards
│   ├── Alertmanager → Slack/Telegram on failures
│
└── Cron (via Hermes):
    ├── Nightly inventory sync: hermes cron "0 2 * * *"
    ├── Capacity trending: hermes cron "0 8 * * 1"
    └── DB cleanup/vacuum: hermes cron "0 3 * * 0"
```

### 7.1 Docker Compose Fragment

```yaml
version: '3.8'

services:
  api:
    build: ./api
    ports: ['127.0.0.1:8000:8000']
    environment:
      DATABASE_URL: postgresql://hermes:${DB_PASSWORD}@postgres:5432/orchestrator
      REDIS_URL: redis://redis:6379/0
      HERMES_HOME: /data/hermes-home
      JWT_SECRET: ${JWT_SECRET}
    volumes:
      - ./api:/app
      - /opt/data/telecom-orchestrator:/data
    depends_on: [postgres, redis]

  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_USER: hermes
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data

  worker:
    build: ./worker
    deploy:
      replicas: 3
    environment:
      REDIS_URL: redis://redis:6379/0
      DATABASE_URL: postgresql://hermes:${DB_PASSWORD}@postgres:5432/orchestrator
    volumes:
      - /opt/data/telecom-orchestrator:/data
      - /opt/data/skills:/opt/data/skills:ro
    depends_on: [redis, postgres]

  webhook-dispatcher:
    build: ./webhook-dispatcher
    environment:
      REDIS_URL: redis://redis:6379/0
      DATABASE_URL: postgresql://hermes:${DB_PASSWORD}@postgres:5432/orchestrator
      WEBHOOK_SECRET: ${WEBHOOK_SECRET}

  nginx:
    image: nginx:alpine
    ports: ['443:443', '80:80']
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro

volumes:
  pgdata:
  redisdata:
```

---

## 8. CRM Integration Patterns

### Pattern A: Salesforce Communications Cloud (Native TMF)

Salesforce Communications Cloud has native support for TMF622 and TMF641. No custom middleware needed.

```
Salesforce OmniStudio / Industries CPQ
  │
  │  Order Capture → Order Decomposition
  │
  ▼
Salesforce TMF622 Outbound Connector
  │
  │  POST /api/tmf622/productOrder
  │
  ▼
Your Orchestrator (same TMF622 endpoint)

Configuration in Salesforce:
  Named Credential: Orchestrator_API
    URL: https://orchestrator.yourcompany.com/api
    Auth: API Key in header X-API-Key
  TMF622 Connector points to that Named Credential
  Webhook listener (Salesforce Apex REST endpoint) receives status callbacks
```

### Pattern B: Non-TMF CRM (REST + Webhook)

For CRMs that don't speak TMF natively (Zoho, custom ERPs, etc.):

```
CRM
  │
  │  Adapter layer (simple translation)
  │
  ├── POST /api/v1/orders
  │    { customer, product, site, bandwidth, callbackUrl }
  │    
  │    Adapter translates to TMF622 JSON and forwards
  │
  └── GET /api/v1/orders/{id}/status
       Adapter proxies to GET /api/tmf641/serviceOrder/{id}
```

### Pattern C: Webhook-Only (Simplest Integration)

For minimum CRM-side development:

```
1. CRM sends order via a simple REST POST
2. CRM exposes a single webhook endpoint
3. Orchestrator pushes ALL status updates to that endpoint
4. CRM updates its order record on each webhook received

CRM webhook endpoint pseudocode:
  POST /webhooks/orchestrator/order-status
  {
    orderId: "CRM-ORDER-12345",
    serviceId: "svc-acme-sjc-l3vpn",
    status: "completed",
    resources: { vrf: "CUST-SJC-CORP", ip: "10.1.0.0/30", ... }
  }

  → CRM updates Order.Status = "Provisioned"
  → CRM stores Service ID for future reference
```

---

## 9. Order Lifecycle — End-to-End Trace

```
T=0s    CRM POST /api/tmf622/productOrder
          → Order Manager validates, decomposes into ServiceOrders
          → Response 202 Accepted { orderId: "ord-20260621-0001" }
          → Enqueue child ServiceOrders to Redis

T=1s    RQ Worker picks up first ServiceOrder
          → Hermes worker loads telecom-service-provisioning skill
          → Callback: state=inProgress { message: "Feasibility check starting" }
          → CRM: Order Status = "In Progress"

T=5s    Feasibility check completes
          → NetBox MCP confirms sfo-pe-01 has capacity
          → Callback: { message: "Feasibility check PASS" }

T=10s   Resource allocation
          → VRF=CUST-SJC-CORP, RD=65001:1001, Subnet=10.1.0.0/30
          → Callback: { message: "Resources allocated" }

T=30s   Device configuration
          → Ansible MCP pushes 18-line config to sfo-pe-01
          → Callback: { message: "Configuration deployed" }

T=45s   Verification
          → Ping 10.1.0.2: 4.2ms, BGP Established, 12 prefixes
          → Callback: { message: "Verification passed" }

T=48s   Activation
          → Service → ACTIVE, Resources → IN_SERVICE
          → Memory: persist pattern
          → Callback: state=completed { serviceId: "svc-acme-sjc-l3vpn", resources: {...} }
          → CRM: Order Status = "Provisioned", Service ID = "svc-acme-sjc-l3vpn"

TOTAL: 48 seconds from CRM order to active service
```

---

## 10. Failure Modes & Resilience

| Failure Scenario              | System Response                                              |
|-------------------------------|--------------------------------------------------------------|
| Device unreachable            | Retry 3x (30s apart), then mark `failed`, alert ops          |
| Resource pool exhausted       | Mark `held`, check for alternatives, alert capacity team     |
| Config push fails             | Execute rollback, retry 2x, then `failed` + alert            |
| Verification fails            | Execute rollback, log exact failure reason, `failed` + alert |
| Webhook delivery fails        | Retry 3x with backoff, dead-letter queue, alert if critical  |
| Redis/DB unreachable          | API returns 503, RQ workers pause, auto-reconnect            |
| Hermes worker crash mid-job   | RQ auto-requeues, new worker picks up, idempotent replay     |
| Race condition (two same orders)| Idempotency key on externalId, detect duplicate, return 409 |

---

## 11. Scaling

- **Horizontal**: Add more RQ workers (Hermes agents). Each is stateless beyond the task at hand.
- **Database**: Read replicas for inventory queries. Primary for writes.
- **Redis**: Sentinel for HA or Redis Cluster for sharding.
- **API**: Nginx + multiple uvicorn workers behind load balancer.
- **Multi-DC**: Deploy worker pools in each region for device-local orchestration (lower latency, no cross-region SSH).
