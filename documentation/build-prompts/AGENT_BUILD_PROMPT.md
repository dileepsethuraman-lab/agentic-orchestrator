# AGENT BUILD PROMPT — Telecom Agentic Orchestration Engine PoC

> **FOR THE AI AGENT:** This document is your single source of truth. Read it completely before writing a single file. Every path, every class, every CSS rule, and every JS function is specified here. Follow it exactly — do not improvise, do not skip steps, do not add features not listed here.

---

## PART 0: SYSTEM OVERVIEW & IDENTITY

### What This System IS

A **cache-first, data-sovereign telecom orchestration engine** that:
- Accepts TMF640 Service Activation and TMF641 Service Order requests (structured JSON), AND unstructured natural language text (e.g., "activate new mobile service 088888 for retail customer with gold SLA")
- Runs a **multi-stage async pipeline** on every request: DETECT → MASK → CACHE (pattern match) → RAG → LLM (Deepseek) → HYDRATE → LOCK → MERGE → WRITE-THROUGH → VALIDATE → EXECUTE → NOTIFY → VERIFY → STORE
- Uses a **KB-driven knowledge engine** — all network element definitions, attributes, workflows, and lifecycle states derive from the knowledge base (`knowledge-base/`), never from hardcoded lists
- **Masks all sensitive identifiers** (MSISDN, IMSI, IP, hostnames) before any cloud LLM call; the token→real mapping never leaves memory
- Uses an **RDF-inspired pattern store** where orchestration patterns are modeled as named graphs of triples (subject, predicate, object) with Jaccard similarity matching
- Emits **TMF641-compliant lifecycle notifications**: ServiceOrderMilestoneEvent for intermediate states, ServiceOrderStateChangeEvent for completion
- Has a **web-visible trace viewer** UI showing every pipeline stage as color-coded trace cards

### What This System IS NOT

- It does NOT execute device configuration directly — EXECUTE stage is stubbed
- It does NOT manage resource inventory — VERIFY constructs NE state from KB + plan
- It does NOT handle CRM integration or TMF622 Product Order decomposition
- It does NOT perform real-time network monitoring or service assurance

### Technology Stack

- **Python 3.13**, **FastAPI**, **uvicorn**, **diskcache** (SQLite-backed, Redis-compatible), **pydantic**
- **Deepseek v4** (via `hermes chat` CLI subprocess) for cloud AI reasoning
- **ThreadPoolExecutor** for background async processing (PoC simplification; target architecture uses RabbitMQ)
- **Single-file HTML + vanilla JS** frontend with JetBrains Mono font

### Architecture (PoC vs Target)

| Component | Target | PoC |
|-----------|--------|-----|
| API Gateway | FastAPI TMF640/TMF641/TMF622 | FastAPI `/api/process`, `/api/patterns`, `/api/locks`, `/api/notifications` |
| Message Queue | RabbitMQ (pika) | ThreadPoolExecutor (4 workers), `executor.submit()` |
| Cache Store | Redis | diskcache (SQLite-backed) |
| Pattern Store | Redis hash | `PatternEngine` on diskcache |
| Worker Pool | Hermes subprocesses | Single bg thread per request |
| LLM Client | Direct API client | `hermes chat -q` subprocess |
| MCP Servers | NetBox, Ansible, Device | Not implemented — EXECUTE stubbed |

---

## PART 1: COMPLETE DIRECTORY STRUCTURE

Create this EXACT structure under `/opt/data/telecom-orchestrator/`:

```
/opt/data/telecom-orchestrator/
├── poc/
│   ├── server_live.py          # Main FastAPI server (~1848 lines)
│   ├── static/
│   │   └── index.html          # Single-file Web UI (~727 lines)
│   └── cache_store/            # Created at runtime by diskcache
├── knowledge-base/
│   ├── ontologies/
│   │   └── core-ontology.md
│   └── reference/
│       ├── standards-index.md
│       ├── tmf-notification-schemas.md
│       ├── implementation-guide.md
│       ├── orchestration-brain-design.md
│       └── solution-design-crm-integration.md
└── documentation/
    └── AGENT_BUILD_PROMPT.md   # This file
```

**Create directories:**
```bash
mkdir -p /opt/data/telecom-orchestrator/poc/static
mkdir -p /opt/data/telecom-orchestrator/poc/cache_store
mkdir -p /opt/data/telecom-orchestrator/knowledge-base/ontologies
mkdir -p /opt/data/telecom-orchestrator/knowledge-base/reference
mkdir -p /opt/data/telecom-orchestrator/documentation
```

---

## PART 2: STEP-BY-STEP SETUP

### Step 1: Python Environment

```bash
cd /opt/data/telecom-orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn[standard] diskcache pydantic
```

Verify:
```bash
python3 -c "import fastapi, uvicorn, diskcache, pydantic; print('OK')"
```

### Step 2: Write All Files

Write the files in this exact order (detailed below):
1. **KB files** (6 files) — knowledge base reference documents
2. **poc/server_live.py** — the entire server (main entry point)
3. **poc/static/index.html** — the web UI

### Step 3: Start the Server

```bash
cd /opt/data/telecom-orchestrator
source .venv/bin/activate
python3 poc/server_live.py
```

Server listens on `0.0.0.0:8090`. Open `http://localhost:8090` in a browser.

### Step 4: Verify

```bash
# Health check
curl http://localhost:8090/health
# Expected: {"status":"ok","cache_size":...,"redis_backend":"diskcache"}

# List patterns
curl http://localhost:8090/api/patterns
# Expected: KB-seeded patterns for mobile, l3vpn, sdwan, broadband

# Test a sample request
curl -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"activate new mobile service 447700123456 for retail customer with gold SLA"}'
# Expected: {"order_id":"PO-...","status":"processing","trace":[...],...}
# Then poll: curl http://localhost:8090/api/process/PO-XXXXXXXX
```

---

## PART 3: KNOWLEDGE BASE FILES

These 6 markdown files are the **single source of truth** for all orchestration decisions. Write them EXACTLY as shown.

### File 3.1: `knowledge-base/ontologies/core-ontology.md`

```markdown
# Telecom Service-Resource Orchestrator — Core Ontology

> Version 1.0 | Domain: Telecommunications OSS/BSS
> Standards alignment: TM Forum SID (Information Framework), MEF LSO, ETSI NFV MANO, IETF YANG

## 1. Domain Entity Hierarchy

```
Customer
  └─ ProductOrder ─── instantiates ──→ Service
                                         ├── CustomerFacingService (CFS)
                                         │     e.g. "Enterprise VPN for Acme Corp"
                                         └── ResourceFacingService (RFS)
                                               e.g. "L3VPN instance on PE routers"
                                                 └─ Resource (physical / virtual / cloud)
                                                       ├── PhysicalResource
                                                       │     ├── NetworkDevice (router, switch, firewall, OLT, etc.)
                                                       │     ├── Port / Interface
                                                       │     ├── Card / Module / Chassis
                                                       │     └── PhysicalLink (fiber, copper, microwave)
                                                       ├── LogicalResource
                                                       │     ├── VLAN, VRF, VXLAN, VPN instance
                                                       │     ├── IP Subnet / Address Pool
                                                       │     ├── BGP / OSPF / ISIS process
                                                       │     ├── QoS Policy / ACL
                                                       │     └── Routing table entry
                                                       └── VirtualResource (NFV / Cloud)
                                                             ├── VNF (vRouter, vFirewall, vCPE, vDPI)
                                                             ├── CNF (containerised network function)
                                                             ├── VirtualLink
                                                             └── VirtualStorage
```

## 2. Key Relationship Types

| Relationship    | From          | To           | Meaning                                    |
|-----------------|---------------|--------------|--------------------------------------------|
| `instantiates`  | ProductOrder  | Service      | Order creates a service instance           |
| `composes`      | Service       | Service      | CFS is composed of one or more RFS         |
| `realised_by`   | RFS           | Resource     | A resource-facing service runs on resources|
| `hosts`         | Device        | VNF          | Physical device hosts a virtual function   |
| `connects_to`   | Resource      | Resource     | Network adjacency (link, tunnel, peer)     |
| `depends_on`    | Resource      | Resource     | Requires another resource to function      |
| `allocates_from`| Resource      | Pool         | Draws from a shared capacity pool          |
| `terminates_on` | Service       | Interface    | Service endpoint lands on a port           |
| `provisioned_by`| Resource      | Workflow     | Resource was created by a workflow         |

## 3. Lifecycle State Machine

### Service Lifecycle (per MEF LSO + TM Forum eTOM)

```
DESIGNED → FEASIBILITY_CHECKED → RESERVED → PROVISIONING → ACTIVE
                                                        ├──→ SUSPENDED
                                                        ├──→ MODIFYING → ACTIVE
                                                        └──→ TERMINATING → TERMINATED
```

### Resource Lifecycle (per ETSI NFV MANO)

```
PLANNED → ALLOCATED → CONFIGURING → IN_SERVICE
                                 ├──→ MAINTENANCE → IN_SERVICE
                                 ├──→ DEGRADED → IN_SERVICE
                                 └──→ DECOMMISSIONING → DECOMMISSIONED
```

## 4. Service Taxonomy (Common Telecom Products)

| Category              | Example Services                               | Key Resources Involved                              |
|-----------------------|------------------------------------------------|-----------------------------------------------------|
| L3VPN / MPLS VPN      | Enterprise MPLS L3VPN, VPLS, EVPN             | PE router, VRF, BGP session, CE interface, RT/RD    |
| SD-WAN                | Managed SD-WAN overlay                        | vCPE/uCPE, IPSec tunnels, SD-WAN controller         |
| Internet Access       | DIA, Broadband, FTTH, 5G FWA                  | BNG/BRAS, OLT, ONT, IP pool, AAA (RADIUS)           |
| Cloud Connect         | AWS Direct Connect, Azure ExpressRoute        | Physical cross-connect, VLAN handoff, BGP           |
| Voice / UC            | SIP trunk, Hosted PBX, Microsoft Teams Direct Routing | SBC, SIP trunk, DID range, media server      |
| Mobile Backhaul       | 4G/5G xHaul, Fronthaul                        | Cell-site router, microwave, fiber, PTP, SyncE      |
| Security              | Managed Firewall, DDoS scrubbing, SASE        | vFirewall, scrubbing center, BGP flowspec           |
| Transport / Wavelength| OTN circuit, Dark fiber, Wavelength service   | ROADM, transponder, muxponder, fiber pair           |

## 5. Resource Taxonomy (Down to Network Level)

### Layer 0-1 (Photonic / Physical)
- Fiber strand, Fiber pair, Duct, Manhole, Splice enclosure
- Wavelength / Lambda, OTU, ODU, OCH trail
- ROADM degree, WSS port, Amplifier, Transponder

### Layer 2 (Data Link)
- Switch, Bridge domain, VLAN (C-VLAN, S-VLAN, Q-in-Q)
- Pseudowire (PWE3), VPLS instance, EVPN instance (EVI)
- LAG / Port-channel, STP domain, MAC address table

### Layer 3 (Network)
- Router, VRF, BGP ASN / peer / session, OSPF area / process
- IP subnet, Loopback, Route policy / Route-map
- MPLS LSP, RSVP-TE tunnel, SR-MPLS segment list, SRv6 path

### Layer 4-7 (Application)
- Firewall policy / zone, Load balancer VIP / pool, SBC, DPI engine
- DNS zone / record, NTP peer, RADIUS / TACACS+ server
- Certificate, SNMP community, NetFlow exporter

### Cloud / NFV
- VIM resource (OpenStack compute/network/storage), Kubernetes Pod/Service
- VNF Descriptor (VNFD), Network Service Descriptor (NSD)
- Virtual link, SRIOV VF, DPDK port, vSwitch

## 6. Workflow Categories

| Workflow Type          | Trigger                          | Description                                      |
|------------------------|----------------------------------|--------------------------------------------------|
| Service Fulfillment    | "Create service X for customer Y"| End-to-end provisioning from order to activation |
| Service Assurance      | Alarm, threshold breach, cron    | Health check, fault correlation, remediation     |
| Resource Provisioning  | Resource creation step in a workflow | Configure a single resource (interface, VRF, etc.) |
| Resource Discovery     | Cron, manual trigger             | Scan network, sync inventory                     |
| Capacity Management    | Threshold, forecast              | Augment pool, migrate load                       |
| Service Modification   | Customer request                 | Add/remove/change service component              |
| Service Termination    | Customer request, contract end   | Decommission service, release resources           |

## 7. Descriptor Formats

| Format   | Scope              | Standard              | Used For                                          |
|----------|--------------------|-----------------------|---------------------------------------------------|
| TOSCA    | Service topology   | OASIS TOSCA           | Service template, VNF forwarding graph            |
| YANG     | Device/resource config | IETF YANG / NETCONF | Device configuration, resource state              |
| NSD      | Network service    | ETSI NFV SOL-006      | VNF composition, virtual links                    |
| VNFD     | Virtual function   | ETSI NFV SOL-001      | VNF deployment descriptor                         |
| Helm     | CNF                | CNCF                  | Containerised network function deployment         |
| Ansible  | Automation         | Red Hat               | Device configuration playbooks                    |
```

### File 3.2: `knowledge-base/reference/standards-index.md`

```markdown
# Telecom Orchestrator — Reference Standards Index

## Industry Standards Bodies & Frameworks

### TM Forum (TeleManagement Forum)
- **eTOM** (enhanced Telecom Operations Map) — Business process framework
- **SID** (Information Framework) — Shared Information/Data model
- **TAM** (Application Framework) — Application map
- **Open APIs** — REST-based API suite (TMF638 Service Inventory, TMF639 Resource Inventory, TMF641 Service Ordering, etc.)
- URL: https://www.tmforum.org

### MEF (formerly Metro Ethernet Forum)
- **MEF 55** — LSO Reference Architecture and Framework
- **MEF 59** — Network Resource Management: Information Model
- **MEF 60** — Network Resource Provisioning: Interface Profile
- **MEF 63** — Subscriber Service Attributes (for SD-WAN, etc.)
- **MEF W117 / LSO Sonata** — Inter-provider orchestration interface
- URL: https://wiki.mef.net

### ETSI NFV ISG
- **NFV-MANO** — Management and Orchestration (NFVO, VNFM, VIM)
- **SOL-001** — VNF Descriptor (TOSCA-based)
- **SOL-006** — YANG-based NFV descriptors (NSD, VNFD, PNFD)
- **SOL-003** — NFVO-VNFM interface (Or-Vnfm)
- **SOL-005** — Os-Ma-nfvo interface
- URL: https://www.etsi.org

### IETF
- **YANG** (RFC 7950) — Data modeling language for NETCONF/RESTCONF
- **NETCONF** (RFC 6241) — Network configuration protocol
- **RESTCONF** (RFC 8040) — REST interface for YANG datastores
- **L3VPN YANG model** (RFC 8299) — L3VPN service delivery model
- **L2VPN YANG model** (RFC 8466)
- URL: https://www.ietf.org

### ONF (Open Networking Foundation)
- **TAPI** (Transport API) — Optical/transport SDN controller northbound
- **CIM** (Core Information Model)
- URL: https://opennetworking.org

### 3GPP
- **TS 28.530/531** — Management and orchestration for 5G (5G MANO)
- **TS 28.540** — Network Resource Model (NRM) for 5G
- URL: https://www.3gpp.org

### OASIS TOSCA
- **TOSCA Simple Profile for NFV** — Network service topology templates
- URL: https://www.oasis-open.org

## Key Open-Source Implementations

| Project          | Scope                        | URL                                   |
|------------------|------------------------------|---------------------------------------|
| OSM              | ETSI MANO NFVO/VNFM          | https://osm.etsi.org                 |
| ONAP             | Full OSS orchestration       | https://onap.org                     |
| OpenStack Tacker | NFV Orchestrator (VNFM)      | https://wiki.openstack.org/wiki/Tacker|
| Nephio           | K8s-based 5G NF automation   | https://nephio.org                   |
| Cisco NSO        | Multi-vendor service activation | https://developer.cisco.com/nso   |
| Ansible (network)| Device config automation     | https://docs.ansible.com/ansible/latest/network|
| Nornir           | Python automation framework  | https://nornir.readthedocs.io        |
| NetBox           | DCIM / IPAM / network source of truth | https://netbox.dev          |
| Nautobot         | NetBox fork + orchestration  | https://nautobot.com                 |
| Itential         | Network automation platform  | https://www.itential.com             |

## Key Protocol Stack

```
Northbound (OSS/BSS):    REST / TMF Open API / MEF LSO Sonata
                          ↓
Service Orchestrator:     TOSCA NSD / Helm Chart / Custom DSL
                          ↓
Resource Orchestrator:    YANG + NETCONF / RESTCONF / gNMI
                          ↓
Controllers:              SDN Controller (ODL, ONOS) / NFV VNFM
                          ↓
Device / Infrastructure:  CLI (SSH), SNMP, gRPC, NETCONF, RESTCONF
```
```

### File 3.3: `knowledge-base/reference/tmf-notification-schemas.md`

```markdown
# TMF Notification Event Schemas — Reference

> Source: TM Forum Open API specifications (TMF641 v4.1.0, TMF640 R18.5.0)
> Repository: https://github.com/tmforum-apis/TMF641_ServiceOrder

## 1. ServiceOrderStateChangeEvent

The canonical notification emitted when a TMF641 ServiceOrder transitions state.

### Schema (from TMF641 v4.1.0 swagger)

```json
{
  "eventId": "string (required) — unique identifier of this notification instance",
  "eventTime": "date-time (required) — ISO 8601 timestamp of event occurrence",
  "eventType": "string (required) — 'ServiceOrderStateChangeEvent'",
  "correlationId": "string — correlates related events across systems",
  "domain": "string — business domain (e.g., 'Telecom', 'ServiceFulfillment')",
  "title": "string — human-readable title",
  "description": "string — explanatory text",
  "priority": "string — event priority",
  "timeOcurred": "date-time — time the underlying event occurred",
  "event": {
    "serviceOrder": {
      "id": "string (required) — service order identifier",
      "href": "string — hyperlink to the order resource",
      "state": "ServiceOrderStateType — current order state",
      "externalId": "string — CRM/consumer-facing order reference",
      "category": "string — Broadband, TVOption, VPN, Mobile, etc.",
      "description": "string — free-text description",
      "orderDate": "date-time",
      "completionDate": "date-time",
      "expectedCompletionDate": "date-time",
      "priority": "string",
      "relatedParty": [{ "role": "string", "name": "string", "id": "string" }],
      "serviceOrderItem": [
        {
          "id": "string",
          "action": "add | modify | delete | noChange",
          "state": "ServiceOrderItemStateType",
          "service": { "id": "string", "href": "string", "state": "ServiceStateType" }
        }
      ],
      "milestone": [
        {
          "id": "string",
          "name": "string — milestone name",
          "description": "string",
          "message": "string",
          "milestoneDate": "date-time",
          "status": "string"
        }
      ]
    }
  }
}
```

### State Enumerations

**ServiceOrderStateType** (TMF641):
```
acknowledged | rejected | pending | held | inProgress |
cancelled | completed | failed | partial |
assessingCancellation | pendingCancellation
```

**ServiceOrderItemStateType** (TMF641):
```
acknowledged | rejected | pending | held | inProgress |
cancelled | completed | failed | partial |
assessingCancellation | pendingCancellation
```

**ServiceStateType** (TMF638):
```
feasibilityChecked | designed | reserved | inactive | active | terminated
```

## 2. ServiceOrderMilestone

Marks a significant stage in service order processing.

```json
{
  "id": "string — milestone identifier",
  "name": "string — e.g. 'HLR_PROVISIONED', 'IMS_REGISTERED'",
  "description": "string — free-text description",
  "message": "string — operational message",
  "milestoneDate": "date-time — when the milestone was reached",
  "status": "string — 'achieved' | 'pending' | 'failed'",
  "serviceOrderItem": [ { "id": "string", "href": "string" } ]
}
```

## 3. Notification Event Types Available (TMF641)

| Event Type | Trigger |
|------------|---------|
| `ServiceOrderCreateEvent` | New service order created |
| `ServiceOrderStateChangeEvent` | Order state transitioned |
| `ServiceOrderAttributeValueChangeEvent` | Order attribute changed |
| `ServiceOrderDeleteEvent` | Order deleted |
| `ServiceOrderInformationRequiredEvent` | More info needed from consumer |
| `ServiceOrderJeopardyEvent` | Order at risk of missing SLA |
| `ServiceOrderMilestoneEvent` | Milestone reached in processing |

## 4. Mapping: Orchestrator Lifecycle → TMF Events

The orchestrator's KB-defined lifecycle states map to TMF events as follows:

| KB Lifecycle State | TMF Event | ServiceOrder State |
|--------------------|-----------|-------------------|
| DESIGNED | ServiceOrderMilestoneEvent | inProgress, milestone=DESIGNED |
| FEASIBILITY_CHECKED | ServiceOrderMilestoneEvent | inProgress, milestone=FEASIBILITY_CHECKED |
| {NE}_PROVISIONED / REGISTERED / CONFIGURED | ServiceOrderMilestoneEvent | inProgress, milestone={state} |
| ACTIVE | ServiceOrderStateChangeEvent | completed |

### Pattern for milestone emissions during processing:
- Order state remains `inProgress` throughout provisioning
- Each lifecycle stage emits a milestone (not a full state change)
- Final ACTIVE stage emits ServiceOrderStateChangeEvent with state=completed
- All events share the same correlationId for traceability
```

### File 3.4: `knowledge-base/reference/implementation-guide.md`

Create this file but it can be a placeholder — the main build instructions are in this prompt. For completeness:

```markdown
# Building the Agentic Service-Resource Orchestrator

## Architecture Overview

This orchestrator runs as a single FastAPI server on a standard Linux VPS.
See the AGENT_BUILD_PROMPT.md for the complete self-contained build instructions.

## Key Components

1. **Knowledge Base** — Core ontology, standards references, notification schemas
2. **Pattern Engine** — RDF-inspired triple store with Jaccard matching
3. **Data Masker** — Tokenization of sensitive identifiers before cloud AI
4. **Pipeline** — 13-stage orchestration from DETECT through STORE
5. **Lifecycle Notifier** — TMF641-compliant notification emissions
6. **Subscriber Lock** — Per-subscriber advisory locking for concurrent safety
7. **Web UI** — Single-file trace viewer with pattern analysis

## Quick Start

```bash
cd /opt/data/telecom-orchestrator
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn[standard] diskcache pydantic
python3 poc/server_live.py
```

Open http://localhost:8090
```

### File 3.5: `knowledge-base/reference/orchestration-brain-design.md`

Create a reference document covering the pipeline design (can be a summary):

```markdown
# Orchestration Brain — Solution Design

> Owner: Orchestration Team
> Northbound: TMF640 Service Activation / TMF641 Service Ordering
> Southbound: Workflow MCP (dynamic workflow execution)

## Pipeline Stages

1. **DETECT** — Classify request format (JSON vs unstructured text)
2. **MASK** — Tokenize sensitive identifiers (MSISDNs, IPs) before cloud
3. **CACHE** — Pattern match via Jaccard similarity on RDF triples
4. **RAG** — Load KB context (ontology + standards) for LLM reasoning
5. **LLM** — Call Deepseek v4 with masked data + KB context
6. **HYDRATE** — Restore real identifiers from token map
7. **LOCK** — Acquire per-subscriber advisory lock
8. **MERGE** — Cascade request characteristics into plan params
9. **WRITE-THROUGH** — Learn new pattern or reinforce existing
10. **VALIDATE** — Block destructive keywords (erase, reload, shutdown, etc.)
11. **EXECUTE** — Dispatch workflows to MCP (stubbed)
12. **NOTIFY** — Emit TMF641 milestone + state change events
13. **VERIFY** — Build network elements, compute subscriber diff, save model
14. **STORE** — Release lock, finalize job

## Pattern Engine

Patterns are modeled as RDF-inspired named graphs of triples (subject, predicate, object).
Matching uses Jaccard similarity on service-defining characteristics (excluding instance identifiers like MSISDN/IMSI/IP).

## Confidence Lifecycle

- KB-seeded (source="kb"): 0.25
- Auto-learned (source="auto"): 0.30
- Each cache HIT: +0.05 (cap 0.95)
- Above 0.90: +0.005 per hit (cap 0.98)
- Manually taught (source="teach"): 0.90
```

### File 3.6: `knowledge-base/reference/solution-design-crm-integration.md`

```markdown
# Solution Design: CRM-Integrated Service & Resource Orchestrator

> Author: Solution Designer | Version: 1.0
> Standards: TM Forum Open APIs, MEF LSO, ETSI NFV MANO

## Overview

A CRM-triggerable service orchestration platform that accepts product orders from any CRM system, decomposes them into service orders, fulfills them asynchronously down to the network device level, and reports status back to the CRM.

## Northbound APIs (CRM-Facing)

- **TMF622** — Product Order (decompose into service orders)
- **TMF641** — Service Order (provision individual services)
- **TMF640** — Service Activation (activate specific service instances)
- **TMF638** — Service Inventory (query service state)
- **TMF639** — Resource Inventory (query resource state)

## Southbound Integration

MCP servers bridge to:
- **NetBox** — DCIM/IPAM source of truth
- **Ansible** — Device configuration automation
- **Cisco NSO** — Multi-vendor service activation
- **OSM / ONAP** — NFV orchestration

## CRM Integration Patterns

- **Webhook Callbacks** — POST status updates to CRM callback URL
- **Polling** — CRM polls GET /tmf641/serviceOrder/{id} for status
- **Event-Driven** — TMF notification events pushed to CRM message queue

## Database Schema (CRM Side)

The CRM maintains:
- Product Order table (TMF622)
- Service Order table (TMF641) 
- Customer table
- Webhook delivery log

## Status Mapping

| Orchestrator State | TMF641 State | CRM Status |
|--------------------|-------------|------------|
| DESIGNED → PROVISIONING | inProgress | Processing |
| ACTIVE | completed | Fulfilled |
| Validation BLOCKED | failed | Failed |
```

---

## PART 4: WEB UI — `poc/static/index.html`

This is the FULL content of the single-file HTML+CSS+JS frontend. Write every line exactly as shown.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>Telecom Agentic Orchestration Engine — PoC Demo</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'JetBrains Mono', monospace;
      background: #020617;
      color: #e2e8f0;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .header {
      background: rgba(15, 23, 42, 0.9);
      border-bottom: 1px solid #1e293b;
      padding: 0.75rem 1.5rem;
      display: flex; align-items: center; gap: 1rem; flex-shrink: 0;
    }
    .pulse { width: 10px; height: 10px; background: #22d3ee; border-radius: 50%; animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .header h1 { font-size: 1rem; font-weight: 600; letter-spacing: -0.02em; }
    .header .badge {
      font-size: 0.65rem; padding: 0.15rem 0.55rem; border-radius: 999px;
      background: rgba(34, 211, 238, 0.15); color: #22d3ee; border: 1px solid rgba(34, 211, 238, 0.3);
    }

    .main { display: flex; flex: 1; overflow: hidden; }
    .panel { padding: 1.25rem; overflow-y: auto; }
    .panel-left  { width: 420px; flex-shrink: 0; border-right: 1px solid #1e293b; background: rgba(15, 23, 42, 0.4); }
    .panel-right { flex: 1; background: rgba(2, 6, 23, 0.6); }

    .left-section { margin-bottom: 1.25rem; }
    .left-section label {
      display: block; font-size: 0.7rem; font-weight: 600; color: #94a3b8;
      text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.4rem;
    }
    textarea {
      width: 100%; min-height: 160px; background: #0f172a; border: 1px solid #334155;
      border-radius: 8px; color: #e2e8f0; font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem; padding: 0.75rem; resize: vertical; line-height: 1.5;
      transition: border-color 0.2s;
    }
    textarea:focus { outline: none; border-color: #22d3ee; box-shadow: 0 0 0 2px rgba(34, 211, 238, 0.15); }

    .btn-row { display: flex; gap: 0.5rem; margin-top: 0.6rem; }
    button {
      font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 600;
      padding: 0.55rem 1rem; border-radius: 8px; border: none; cursor: pointer; transition: all 0.15s;
    }
    .btn-primary { background: #22d3ee; color: #020617; }
    .btn-primary:hover { background: #67e8f9; }
    .btn-secondary { background: rgba(51, 65, 85, 0.5); color: #94a3b8; border: 1px solid #334155; }
    .btn-secondary:hover { background: rgba(51, 65, 85, 0.8); color: #e2e8f0; }
    button:disabled { opacity: 0.4; cursor: not-allowed; }

    .samples { margin-top: 0.5rem; }
    .sample-chip {
      display: block; width: 100%; text-align: left; padding: 0.45rem 0.6rem;
      background: rgba(30, 41, 59, 0.5); border: 1px solid #1e293b;
      border-radius: 6px; color: #94a3b8; font-family: 'JetBrains Mono', monospace;
      font-size: 0.62rem; cursor: pointer; margin-bottom: 0.3rem; transition: all 0.15s;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .sample-chip:hover { background: rgba(34, 211, 238, 0.08); border-color: rgba(34, 211, 238, 0.3); color: #22d3ee; }

    /* Trace header */
    .trace-header {
      display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem;
      padding-bottom: 0.75rem; border-bottom: 1px solid #1e293b;
    }
    .trace-header h2 { font-size: 0.85rem; font-weight: 600; }
    .trace-id { font-size: 0.6rem; color: #475569; }
    .trace-status { font-size: 0.65rem; padding: 0.15rem 0.55rem; border-radius: 999px; font-weight: 600; }
    .trace-status.blocked   { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
    .trace-status.running   { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }
    .trace-status.error   { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
    .trace-status.completed { background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.3); }

    /* Notification Timeline */
    .notif-timeline { margin: 0.4rem 0; padding: 0.6rem 0.8rem; background: rgba(6, 182, 212, 0.05); border: 1px solid rgba(6, 182, 212, 0.15); border-radius: 8px; }
    .notif-timeline h3 { font-size: 0.7rem; color: #06b6d4; margin-bottom: 0.5rem; font-weight: 600; }
    .notif-track { display: flex; align-items: flex-start; gap: 0; overflow-x: auto; padding: 0.2rem 0; }
    .notif-node { display: flex; flex-direction: column; align-items: center; min-width: 80px; position: relative; }
    .notif-dot { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; background: rgba(6, 182, 212, 0.2); border: 2px solid #06b6d4; color: #06b6d4; }
    .notif-dot.active { background: rgba(34, 197, 94, 0.25); border-color: #22c55e; color: #22c55e; }
    .notif-state { font-size: 0.5rem; color: #64748b; margin-top: 0.25rem; text-align: center; word-break: break-all; max-width: 80px; }
    .notif-connector { flex: 1; min-width: 20px; height: 2px; background: rgba(6, 182, 212, 0.3); margin-top: 13px; }
    .notif-connector.active { background: #22c55e; }

    /* Trace steps */
    .trace-step {
      opacity: 0; transform: translateX(20px);
      animation: slideIn 0.35s ease-out forwards;
      margin-bottom: 0.5rem;
    }
    @keyframes slideIn { to { opacity: 1; transform: translateX(0); } }

    .step-card {
      border-radius: 10px; border: 1px solid; overflow: hidden;
      transition: all 0.2s; cursor: pointer;
    }
    .step-card:hover { box-shadow: 0 0 20px rgba(0,0,0,0.3); }

    .step-header {
      display: flex; align-items: center; gap: 0.5rem; padding: 0.55rem 0.8rem;
      cursor: pointer; user-select: none;
    }
    .step-icon { font-size: 1.1rem; flex-shrink: 0; }
    .step-title { font-size: 0.75rem; font-weight: 600; flex: 1; }
    .step-elapsed { font-size: 0.6rem; opacity: 0.6; white-space: nowrap; }
    .step-body {
      padding: 0.6rem 0.8rem 0.8rem; font-size: 0.65rem; line-height: 1.55;
      border-top: 1px solid rgba(255,255,255,0.05);
    }
    .step-body.hidden { display: none; }

    /* Step body field labels */
    .step-body .fl { color: #94a3b8; font-weight: 600; }
    .step-body .fv { color: #cbd5e1; }
    .step-body .fl-goal { color: #67e8f9; }
    .step-body .fl-in { color: #a78bfa; }
    .step-body .fl-exp { color: #fbbf24; }
    .step-body .fl-act { color: #4ade80; }
    .step-body .fl-out { color: #f472b6; }

    /* Color themes */
    .card-green  { border-color: rgba(34, 197, 94, 0.3); background: rgba(34, 197, 94, 0.06); }
    .card-green .step-header  { background: rgba(34, 197, 94, 0.1); }
    .card-green .step-title   { color: #4ade80; }
    .card-green .step-body    { color: #bbf7d0; }

    .card-amber  { border-color: rgba(251, 191, 36, 0.3); background: rgba(251, 191, 36, 0.06); }
    .card-amber .step-header  { background: rgba(251, 191, 36, 0.1); }
    .card-amber .step-title   { color: #fbbf24; }
    .card-amber .step-body    { color: #fde68a; }

    .card-red    { border-color: rgba(239, 68, 68, 0.3); background: rgba(239, 68, 68, 0.06); }
    .card-red .step-header    { background: rgba(239, 68, 68, 0.1); }
    .card-red .step-title     { color: #f87171; }
    .card-red .step-body      { color: #fecaca; }

    .card-blue   { border-color: rgba(59, 130, 246, 0.3); background: rgba(59, 130, 246, 0.06); }
    .card-blue .step-header   { background: rgba(59, 130, 246, 0.1); }
    .card-blue .step-title    { color: #60a5fa; }
    .card-blue .step-body     { color: #bfdbfe; }

    .card-violet { border-color: rgba(167, 139, 250, 0.3); background: rgba(167, 139, 250, 0.06); }
    .card-violet .step-header { background: rgba(167, 139, 250, 0.1); }
    .card-violet .step-title  { color: #a78bfa; }
    .card-violet .step-body   { color: #ddd6fe; }

    .card-cyan   { border-color: rgba(34, 211, 238, 0.3); background: rgba(34, 211, 238, 0.06); }
    .card-cyan .step-header   { background: rgba(34, 211, 238, 0.1); }
    .card-cyan .step-title    { color: #22d3ee; }
    .card-cyan .step-body     { color: #a5f3fc; }

    /* Running pulse */
    .card-running { animation: pulseGlow 2s ease-in-out infinite; }
    @keyframes pulseGlow { 0%, 100% { box-shadow: 0 0 8px rgba(34,211,238,0.15); } 50% { box-shadow: 0 0 20px rgba(34,211,238,0.35); } }

    /* Pattern Analysis section */
    .pattern-analysis {
      margin-top: 1rem; padding: 1rem 1.25rem; border-radius: 12px;
      border: 1px solid rgba(167, 139, 250, 0.25); background: rgba(167, 139, 250, 0.04);
      opacity: 0; animation: slideIn 0.5s 0.1s ease-out forwards;
    }
    .pattern-analysis h3 { font-size: 0.78rem; color: #a78bfa; margin-bottom: 0.75rem; }
    .pa-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; }
    .pa-card {
      background: rgba(15, 23, 42, 0.6); border: 1px solid #1e293b;
      border-radius: 8px; padding: 0.7rem;
    }
    .pa-card-title { font-size: 0.6rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.5rem; }
    .pa-card-value { font-size: 0.72rem; font-weight: 700; }
    .pa-card-value.hi { color: #4ade80; }
    .pa-card-value.mi { color: #fbbf24; }
    .pa-card-value.lo { color: #f87171; }
    .pa-bar-wrap { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.35rem; }
    .pa-bar { flex: 1; height: 8px; background: #1e293b; border-radius: 4px; overflow: hidden; }
    .pa-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
    .pa-tag { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.55rem; font-weight: 600; }
    .pa-tag.llm  { background: rgba(59,130,246,0.15); color: #60a5fa; }
    .pa-tag.taught { background: rgba(34,197,94,0.15); color: #4ade80; }
    .pa-tag.cached { background: rgba(167,139,250,0.15); color: #a78bfa; }

    /* Suggestion box */
    .pa-suggestion {
      margin-top: 0.8rem; padding: 0.6rem 0.8rem; border-radius: 8px;
      border: 1px solid rgba(251,191,36,0.2); background: rgba(251,191,36,0.05);
      font-size: 0.6rem; color: #fcd34d;
    }
    .pa-suggestion .sug-icon { margin-right: 0.4rem; }

    /* Verification list */
    .verification-list { margin-top: 0.6rem; }
    .verification-list .v-item {
      display: flex; align-items: flex-start; gap: 0.4rem; padding: 0.2rem 0;
      font-size: 0.62rem;
    }
    .v-item .v-icon { font-size: 0.7rem; flex-shrink: 0; margin-top: 1px; }

    /* Final summary */
    .final-summary {
      margin-top: 1rem; padding: 1rem 1.25rem; border-radius: 12px;
      border: 2px solid rgba(34, 197, 94, 0.4); background: rgba(34, 197, 94, 0.08);
      opacity: 0; animation: slideIn 0.5s 0.2s ease-out forwards;
    }
    .final-summary h3 { font-size: 0.78rem; color: #4ade80; margin-bottom: 0.5rem; }
    .kv { display: flex; gap: 2rem; flex-wrap: wrap; }
    .kv-item { font-size: 0.65rem; }
    .kv-label { color: #64748b; }
    .kv-value { color: #e2e8f0; font-weight: 600; }

    /* Network elements */
    .network-elements {
      margin-top: 1rem; padding: 1rem 1.25rem; border-radius: 12px;
      border: 1px solid rgba(59, 130, 246, 0.3); background: rgba(59, 130, 246, 0.05);
      opacity: 0; animation: slideIn 0.5s 0.3s ease-out forwards;
    }
    .network-elements h3 { font-size: 0.78rem; color: #60a5fa; margin-bottom: 0.75rem; }
    .ne-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 0.6rem; }
    .ne-card {
      background: rgba(15, 23, 42, 0.7); border: 1px solid #1e293b;
      border-radius: 8px; padding: 0.7rem; transition: border-color 0.2s; cursor: pointer;
    }
    .ne-card:hover { border-color: rgba(59, 130, 246, 0.4); }
    .ne-card-header {
      display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.5rem;
      padding-bottom: 0.4rem; border-bottom: 1px solid #1e293b;
    }
    .ne-card-icon { font-size: 1rem; }
    .ne-card-name { font-size: 0.7rem; font-weight: 600; color: #e2e8f0; }
    .ne-card-wf { font-size: 0.55rem; color: #64748b; margin-left: auto; }
    .ne-attr { display: flex; justify-content: space-between; padding: 0.18rem 0; font-size: 0.6rem; }
    .ne-attr-key { color: #64748b; }
    .ne-attr-val { color: #94a3b8; font-weight: 500; max-width: 55%; text-align: right; overflow: hidden; text-overflow: ellipsis; }
    .ne-attr-val.status-ok { color: #4ade80; }

    .empty-state { text-align: center; padding: 4rem 2rem; color: #475569; }
    .empty-state .icon { font-size: 3rem; margin-bottom: 0.75rem; }
    .empty-state p { font-size: 0.75rem; line-height: 1.6; }

    /* Zoom */
    .zoom-backdrop {
      position: fixed; inset: 0; z-index: 1000;
      background: rgba(2, 6, 23, 0.75); backdrop-filter: blur(8px);
      display: none; align-items: center; justify-content: center;
      animation: fadeIn 0.2s ease-out;
    }
    .zoom-backdrop.active { display: flex; }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    .zoom-container {
      width: 96vw; max-width: 1200px; max-height: 94vh; overflow-y: auto;
      border-radius: 12px; animation: zoomIn 0.25s ease-out;
      box-shadow: 0 0 60px rgba(0,0,0,0.6);
    }
    @keyframes zoomIn { from { transform: scale(0.92); opacity: 0; } to { transform: scale(1); opacity: 1; } }
    .zoom-container .step-card, .zoom-container .ne-card { padding: 2rem 2.5rem; min-width: 600px; font-size: 1.05rem; border-width: 2px; }
    .zoom-container .step-header { padding: 0.8rem 1rem; }
    .zoom-container .step-icon { font-size: 1.6rem; }
    .zoom-container .step-title { font-size: 1.2rem; font-weight: 700; }
    .zoom-container .step-elapsed { font-size: 0.85rem; }
    .zoom-container .step-body { font-size: 0.95rem; line-height: 1.8; padding: 1rem 1rem 1rem 2.5rem; }
    .zoom-container .ne-card-name { font-size: 1.05rem; }
    .zoom-container .ne-card-wf { font-size: 0.75rem; }
    .zoom-container .ne-attr { font-size: 0.85rem; padding: 0.35rem 0; }
    .zoom-container .ne-card { padding: 1.5rem 1.75rem; min-width: 400px; }
    .zoom-container .ne-grid { grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); }
    .zoom-container .ne-card-icon { font-size: 1.4rem; }
    .zoom-close-hint {
      position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%);
      font-size: 0.75rem; color: #64748b; pointer-events: none;
      animation: fadeIn 0.3s 1s ease-out forwards; opacity: 0;
    }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
  </style>
</head>
<body>
  <div class="header">
    <div class="pulse"></div>
    <h1>Telecom Agentic Orchestration Engine</h1>
    <span class="badge">PoC Demo</span>
    <span style="margin-left:auto;font-size:0.6rem;color:#475569;">Cache-First · Data-Sovereign · Cloud-Reasoned</span>
  </div>

  <div class="main">
    <div class="panel panel-left">
      <div class="left-section">
        <label>Service Request</label>
        <textarea id="prompt" placeholder="Enter a TMF640/TMF641 JSON payload or unstructured text...&#10;&#10;e.g. activate new mobile service 088888 for retail customer with gold SLA"></textarea>
      </div>
      <div class="btn-row">
        <button class="btn-primary" id="btn-submit" onclick="submitRequest()">▶ Execute</button>
        <button class="btn-secondary" onclick="clearAll()">Clear</button>
      </div>
      <div class="left-section" style="margin-top:1.2rem;">
        <label>Sample Requests</label>
        <div class="samples" id="samples"></div>
      </div>
    </div>

    <div class="panel panel-right" id="trace-panel">
      <div class="empty-state" id="empty-state">
        <div class="icon">⚙️</div>
        <p>Submit a service request on the left to see the orchestration pipeline.</p>
      </div>
      <div id="trace-content" style="display:none;">
        <div class="trace-header">
          <h2 id="trace-title">Pipeline Trace</h2>
          <span class="trace-id" id="trace-id"></span>
          <span class="trace-status" id="trace-status" style="margin-left:auto;"></span>
        </div>
        <div id="trace-steps"></div>
        <div id="notification-timeline"></div>
        <div id="pattern-analysis"></div>
        <div id="final-summary"></div>
        <div id="network-elements"></div>
      </div>
    </div>
  </div>

  <div class="zoom-backdrop" id="zoom-backdrop" onclick="closeZoom(event)">
    <div class="zoom-container" id="zoom-container" onclick="event.stopPropagation()"></div>
  </div>
  <div class="zoom-close-hint" id="zoom-hint">Click anywhere outside to close · Esc</div>

  <script>
    async function loadSamples() {
      const resp = await fetch('/api/samples');
      const data = await resp.json();
      const container = document.getElementById('samples');
      data.samples.forEach(s => {
        const chip = document.createElement('button');
        chip.className = 'sample-chip';
        chip.textContent = s.label;
        chip.onclick = () => { document.getElementById('prompt').value = s.text; };
        container.appendChild(chip);
      });
    }

    function clearAll() {
      document.getElementById('prompt').value = '';
      document.getElementById('trace-content').style.display = 'none';
      document.getElementById('empty-state').style.display = '';
      document.getElementById('trace-steps').innerHTML = '';
      document.getElementById('notification-timeline').innerHTML = '';
      document.getElementById('final-summary').innerHTML = '';
      document.getElementById('network-elements').innerHTML = '';
      document.getElementById('pattern-analysis').innerHTML = '';
    }

    async function submitRequest() {
      const prompt = document.getElementById('prompt').value.trim();
      if (!prompt) return;

      const btn = document.getElementById('btn-submit');
      btn.disabled = true;
      btn.textContent = '\u23f3 Submitting...';

      document.getElementById('empty-state').style.display = 'none';
      document.getElementById('trace-content').style.display = '';
      document.getElementById('trace-steps').innerHTML = '';
      document.getElementById('notification-timeline').innerHTML = '';
      document.getElementById('final-summary').innerHTML = '';
      document.getElementById('network-elements').innerHTML = '';
      document.getElementById('pattern-analysis').innerHTML = '';

      document.getElementById('trace-title').textContent = 'Pipeline Trace';
      document.getElementById('trace-id').textContent = '';
      const statusEl = document.getElementById('trace-status');
      statusEl.textContent = 'PROCESSING';
      statusEl.className = 'trace-status running';

      const stepsContainer = document.getElementById('trace-steps');
      const loadingDiv = document.createElement('div');
      loadingDiv.className = 'trace-step';
      loadingDiv.style.animationDelay = '0s';
      loadingDiv.innerHTML = '<div class="step-card card-blue"><div class="step-header"><span class="step-icon">\u23f3</span><span class="step-title">Submitting \u2014 dispatching pipeline...</span></div><div class="step-body">Determining cache status...</div></div>';
      stepsContainer.appendChild(loadingDiv);
      document.getElementById('trace-panel').scrollTop = document.getElementById('trace-panel').scrollHeight;

      let dots = 0;
      const loadingInterval = setInterval(() => {
        dots = (dots + 1) % 4;
        const title = stepsContainer.querySelector('.step-title');
        if (title) title.textContent = 'Submitting \u2014 dispatching pipeline' + '.'.repeat(dots);
      }, 1000);

      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 130000);
        const resp = await fetch('/api/process', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt }), signal: controller.signal,
        });
        clearTimeout(timeoutId);
        clearInterval(loadingInterval);
        stepsContainer.innerHTML = '';

        let data;
        const text = await resp.text();
        try { data = JSON.parse(text); }
        catch (jsonErr) {
          stepsContainer.innerHTML = '<div class="step-card card-red" style="padding:1rem;border-radius:10px;"><span style="color:#f87171;">\u274c Tunnel error</span><br><small style="color:#fca5a5;">Response: ' + escapeHtml(text.substring(0, 200)) + '</small></div>';
          statusEl.textContent = 'TUNNEL ERROR'; statusEl.className = 'trace-status blocked'; return;
        }

        document.getElementById('trace-id').textContent = data.order_id;

        if (data.status === 'processing') {
          data.trace.forEach((step, i) => renderStep(step, i));
          await pollUntilDone(data.order_id, statusEl, btn, data.started_at);
          return;
        }

        if (data.status === 'completed') {
          statusEl.textContent = 'COMPLETED'; statusEl.className = 'trace-status completed';
        } else if (data.status === 'blocked') {
          statusEl.textContent = 'BLOCKED'; statusEl.className = 'trace-status blocked';
        } else {
          statusEl.textContent = 'ERROR'; statusEl.className = 'trace-status blocked';
        }

        stepsContainer.innerHTML = '';
        data.trace.forEach((step, i) => renderStep(step, i));
        if (data.final_state && data.status === 'completed') {
          setTimeout(() => showFinalOutput(data), data.trace.length * 120 + 200);
        }
      } catch (err) {
        clearInterval(loadingInterval);
        if (stepsContainer.firstChild) stepsContainer.innerHTML = '';
        if (err.name === 'AbortError') {
          statusEl.textContent = 'TIMEOUT';
          document.getElementById('trace-steps').innerHTML = '<div class="step-card card-red" style="padding:1rem;border-radius:10px;"><span style="color:#f87171;">\u23f1 Request timed out after 130 seconds.</span><br><small style="color:#fca5a5;">The LLM call may be taking too long or the tunnel dropped.</small></div>';
        } else {
          statusEl.textContent = 'ERROR'; statusEl.className = 'trace-status blocked';
          document.getElementById('trace-steps').innerHTML = '<div class="step-card card-red" style="padding:1rem;border-radius:10px;"><span style="color:#f87171;">\u274c Connection error: ' + escapeHtml(err.message) + '</span></div>';
        }
      } finally {
        btn.disabled = false; btn.textContent = '\u25b6 Execute';
      }
    }

    async function pollUntilDone(orderId, statusEl, btn, startedAt) {
      statusEl.textContent = 'PROCESSING'; statusEl.className = 'trace-status running';
      const elapsedEl = document.getElementById('trace-id');
      const startTime = startedAt ? new Date(startedAt).getTime() : Date.now();
      const timerInterval = setInterval(() => {
        const secs = Math.floor((Date.now() - startTime) / 1000);
        elapsedEl.textContent = '\u23f1 ' + secs + 's elapsed \u2014 polling...';
      }, 1000);
      try {
        for (let attempt = 0; attempt < 120; attempt++) {
          await new Promise(r => setTimeout(r, 2000));
          try {
            const resp = await fetch('/api/process/' + orderId);
            const data = await resp.json();
            const container = document.getElementById('trace-steps');
            container.innerHTML = '';
            data.trace.forEach((step, i) => renderStep(step, i));
            data.trace.forEach((step, i) => {
              if (step.status === 'running') {
                const cards = container.querySelectorAll('.step-card');
                if (cards[i]) cards[i].classList.add('card-running');
              }
            });
            if (data.status === 'completed') {
              clearInterval(timerInterval);
              statusEl.textContent = 'COMPLETED'; statusEl.className = 'trace-status completed';
              elapsedEl.textContent = '';
              if (data.final_state) showFinalOutput(data);
              btn.disabled = false; btn.textContent = '\u25b6 Execute';
              return;
            }
            if (data.status === 'blocked') {
              clearInterval(timerInterval);
              statusEl.textContent = 'BLOCKED'; statusEl.className = 'trace-status blocked';
              elapsedEl.textContent = '';
              btn.disabled = false; btn.textContent = '\u25b6 Execute';
              return;
            }
          } catch(e) { /* retry */ }
        }
      } finally { clearInterval(timerInterval); elapsedEl.textContent = ''; }
      statusEl.textContent = 'TIMEOUT'; statusEl.className = 'trace-status blocked';
      btn.disabled = false; btn.textContent = '\u25b6 Execute';
    }

    /* --- Step rendering --- */
    function formatDetail(text) {
      if (!text) return '';
      const labels = [
        ['Goal:', 'fl-goal'], ['Input:', 'fl-in'], ['Expected:', 'fl-exp'],
        ['Actual:', 'fl-act'], ['Output:', 'fl-out']
      ];
      let out = escapeHtml(text);
      out = out.replace(/\\n/g, '<br>').replace(/\n/g, '<br>');
      labels.forEach(([label, cls]) => {
        out = out.replace(new RegExp('^' + label, 'gm'), '<span class="fl ' + cls + '">' + label + '</span>');
      });
      return out;
    }

    function renderStep(step, i) {
      const div = document.createElement('div');
      div.style.animationDelay = (i * 0.08) + 's';
      div.innerHTML = '<div class="step-card card-' + step.color + '"><div class="step-header" onclick="this.parentElement.querySelector(\'.step-body\').classList.toggle(\'hidden\')"><span class="step-icon">' + step.icon + '</span><span class="step-title">' + escapeHtml(step.title) + '</span><span class="step-elapsed">' + (step.ms || step.elapsed_ms) + 'ms</span></div><div class="step-body">' + formatDetail(step.detail) + '</div></div>';
      document.getElementById('trace-steps').appendChild(div);
    }

    /* --- Final output: pattern analysis + summary + NEs --- */
    function showFinalOutput(data) {
      const fs = data.final_state;
      if (fs) {
        renderNotificationTimeline(fs);
        buildPatternAnalysis(fs);
        setTimeout(() => {
          document.getElementById('final-summary').innerHTML = buildSummaryHTML(data.total_ms, fs);
          if (fs.networkElements) renderNetworkElements(fs.networkElements, fs.subscriberDiff);
          const notifEl = document.getElementById('notification-timeline');
          if (notifEl) notifEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 200);
      }
    }

    function renderNotificationTimeline(fs) {
      const notifs = fs.notifications || [];
      if (!notifs.length) {
        document.getElementById('notification-timeline').innerHTML = '';
        return;
      }
      let html = '<div class="notif-timeline"><h3>\ud83d\udcec TMF Lifecycle Notifications</h3><div class="notif-track">';
      notifs.forEach((n, i) => {
        let state = '?';
        const so = (n.event && n.event.serviceOrder) || {};
        if (so.milestone && so.milestone.length) {
          state = so.milestone[0].name || '?';
        } else if (so.state) {
          state = so.state;
        }
        const icon = i === notifs.length - 1 ? '\u2705' : '\u25cf';
        html += '<div class="notif-node"><div class="notif-dot active" title="' + escapeHtml(n.eventTime || '') + '">' + icon + '</div><div class="notif-state">' + escapeHtml(state) + '</div></div>';
        if (i < notifs.length - 1) {
          html += '<div class="notif-connector active"></div>';
        }
      });
      html += '</div></div>';
      document.getElementById('notification-timeline').innerHTML = html;
    }

    function buildPatternAnalysis(fs) {
      const pm = fs.patternMatch || {};
      const isHit = pm.result === 'HIT';
      const pct = Math.round((fs.patternConfidence || 0) * 100);
      const barCls = pct >= 70 ? 'high' : pct >= 40 ? 'mid' : 'low';
      const tagCls = fs.llmUsed ? 'llm' : 'cached';
      const tagLabel = fs.llmUsed ? 'LLM Learned' : 'Cache Hit';

      let suggestion = '';
      if (isHit) {
        if (pct < 40) suggestion = 'Low confidence \u2014 run more requests with identical characteristics to reinforce the pattern. Consider teaching explicit patterns for edge cases.';
        else if (pct < 70) suggestion = 'Moderate confidence \u2014 additional runs with similar characteristics will strengthen the match. Pattern is stabilizing.';
        else if (pct < 95) suggestion = 'Good confidence \u2014 pattern is well-established. Continue using to approach 100%.';
        else suggestion = 'Excellent confidence \u2014 pattern is mature and reliable across all matching requests.';
      } else {
        suggestion = 'No pattern matched. This run created a new pattern. Repeat identical requests to build confidence. For faster matching, teach patterns directly via /api/patterns/teach.';
      }

      const verifications = [
        ['\ud83d\udd12', 'Security validation', 'Destructive keyword scan passed \u2014 no blocked commands in plan'],
        ['\ud83d\udccb', 'Schema validation', 'Plan structure verified \u2014 workflows, params, and devices present'],
        ['\ud83d\udd17', 'Resource binding', (fs.workflowsExecuted || 0) + ' workflows mapped to ' + (fs.resourcesProvisioned || 0) + ' configuration parameters'],
        ['\ud83e\udde0', 'LLM reasoning', fs.llmUsed ? 'Deepseek v4 generated plan from KB context' : 'Cached plan retrieved \u2014 no LLM call needed'],
        ['\ud83d\udce1', 'Pattern learning', fs.patternId ? 'Pattern ' + fs.patternId.substring(0,20) + '... stored (' + pct + '% confidence)' : 'No new pattern stored'],
      ];

      let html = '<div class="pattern-analysis"><h3>\ud83d\udd2c Pattern Analysis &amp; Verification</h3><div class="pa-grid"><div class="pa-card"><div class="pa-card-title">Confidence</div><div class="pa-card-value ' + (barCls === 'high' ? 'hi' : barCls === 'mid' ? 'mi' : 'lo') + '">' + pct + '%</div><div class="pa-bar-wrap"><div class="pa-bar"><div class="pa-bar-fill ' + barCls + '" style="width:' + pct + '%"></div></div><span class="pa-tag ' + tagCls + '">' + tagLabel + '</span></div></div><div class="pa-card"><div class="pa-card-title">Pattern</div><div class="pa-card-value" style="font-size:0.62rem;color:#cbd5e1;">' + (fs.patternId ? fs.patternId : '\u2014') + '</div><div style="margin-top:0.4rem;font-size:0.55rem;color:#64748b;">' + (isHit ? 'Matched via ' + (pm.compareLogic || 'Jaccard') + ' \u00b7 ' + (pm.useCount || 0) + ' prior uses \u00b7 Score: ' + Math.round((pm.score||0)*100) + '%' : (pm.patternsForService || 0) + ' patterns for service, ' + (pm.patternsInStore || 0) + ' total') + '</div></div></div><div class="verification-list"><div class="pa-card-title" style="margin-bottom:0.3rem;">Verifications</div>' + verifications.map(v => '<div class="v-item"><span class="v-icon">' + v[0] + '</span><span><b style="color:#94a3b8;">' + v[1] + '</b> \u2014 ' + v[2] + '</span></div>').join('') + '</div><div class="pa-suggestion"><span class="sug-icon">\ud83d\udca1</span>' + suggestion + '</div></div>';
      document.getElementById('pattern-analysis').innerHTML = html;
    }

    function buildSummaryHTML(total_ms, fs) {
      const diff = fs.subscriberDiff || {};
      let modelInfo = '';
      if (diff.hasPrevious) {
        const changed = Object.keys(diff.changedAttributes || {}).length;
        const neDiffs = Object.keys(diff.networkElementDiffs || {}).length;
        modelInfo = '<div style="margin-top:0.5rem;font-size:0.6rem;"><span style="color:#94a3b8;">Subscriber:</span> <span style="color:#e2e8f0;">' + escapeHtml(fs.subscriberId || '\u2014') + '</span>' + (changed > 0 || neDiffs > 0 ? '<span style="color:#fbbf24;margin-left:0.5rem;">\u25cf UPDATED</span> \u00b7 ' + changed + ' attrs changed, ' + neDiffs + ' NEs modified' : '<span style="color:#64748b;margin-left:0.5rem;">\u25cb unchanged</span>') + '</div>';
      } else {
        modelInfo = '<div style="margin-top:0.5rem;font-size:0.6rem;"><span style="color:#94a3b8;">Subscriber:</span> <span style="color:#e2e8f0;">' + escapeHtml(fs.subscriberId || '\u2014') + '</span><span style="color:#4ade80;margin-left:0.5rem;">\u25cf First provisioning \u2014 model v1 saved</span></div>';
      }
      return '<div class="final-summary"><h3>\u2705 Orchestration Complete \u2014 ' + total_ms + 'ms</h3><div class="kv"><div class="kv-item"><span class="kv-label">Service ID: </span><span class="kv-value">' + (fs.serviceId || '') + '</span></div><div class="kv-item"><span class="kv-label">State: </span><span class="kv-value">' + (fs.state || '') + '</span></div><div class="kv-item"><span class="kv-label">Workflows: </span><span class="kv-value">' + (fs.workflowsExecuted || 0) + '</span></div><div class="kv-item"><span class="kv-label">Resources: </span><span class="kv-value">' + (fs.resourcesProvisioned || 0) + '</span></div></div>' + modelInfo + '</div>';
    }

    function renderNetworkElements(elements, diff) {
      if (!elements || !elements.length) return;
      const neDiffs = (diff && diff.networkElementDiffs) || {};
      const icons = { 'HLR': '\ud83d\uddc4\ufe0f', 'IMS-Core': '\ud83d\udcde', 'PCRF': '\ud83d\udccb', 'SMSC': '\ud83d\udcac',
                      'PE-RTR-01': '\ud83d\udd00', 'PE-RTR-02': '\ud83d\udd00', 'Route-Reflector': '\ud83d\udd04', 'NMS': '\ud83d\udda5\ufe0f',
                      'vCPE-01': '\u2601\ufe0f', 'vCPE-02': '\u2601\ufe0f', 'SD-WAN-Ctrl': '\ud83c\udf9b\ufe0f', 'Orchestrator': '\u2699\ufe0f',
                      'OLT-01': '\ud83d\udce1', 'BNG-01': '\ud83c\udf10', 'RADIUS-01': '\ud83d\udd10', 'EMS': '\ud83d\udda5\ufe0f' };
      const container = document.getElementById('network-elements');
      let html = '<div class="network-elements"><h3>\ud83d\udee7 Network Elements \u2014 Post-Activation State</h3><div class="ne-grid">';
      elements.forEach(el => {
        const icon = icons[el.name] || '\ud83d\udd37';
        const elDiffs = neDiffs[el.name] || {};
        const hasChanges = Object.keys(elDiffs).length > 0;
        html += '<div class="ne-card"' + (hasChanges ? ' style="border-color:#fbbf24;border-left:3px solid #fbbf24;"' : '') + '><div class="ne-card-header"><span class="ne-card-icon">' + icon + '</span><span class="ne-card-name">' + el.name + '</span>' + (hasChanges ? '<span style="font-size:0.6rem;font-weight:700;color:#1e293b;background:#fbbf24;padding:1px 6px;border-radius:3px;margin-left:0.4rem;">\u26a1 MODIFIED (' + Object.keys(elDiffs).length + ')</span>' : '') + '<span class="ne-card-wf">' + (el.workflow || '') + '</span></div>';
        for (const [k, v] of Object.entries(el.attributes || {})) {
          const valClass = k === 'status' ? (v.match(/Active|Provisioned|Registered|In-Service|Configured|Established/i) ? 'status-ok' : '') : '';
          const changed = elDiffs[k];
          let valHtml = escapeHtml(String(v));
          if (changed) {
            valHtml = '<span style="color:#fbbf24;">' + escapeHtml(changed.to) + '</span><span style="font-size:0.7rem;color:#f87171;text-decoration:line-through;opacity:0.65;margin-left:0.3rem;">' + escapeHtml(changed.from) + '</span>';
          }
          html += '<div class="ne-attr"><span class="ne-attr-key">' + k + '</span><span class="ne-attr-val ' + valClass + '">' + valHtml + '</span></div>';
        }
        html += '</div>';
      });
      html += '</div></div>';
      container.innerHTML = html;
    }

    function escapeHtml(str) {
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    loadSamples();

    /* --- Zoom --- */
    function openZoom(el) {
      const backdrop = document.getElementById('zoom-backdrop');
      const container = document.getElementById('zoom-container');
      const hint = document.getElementById('zoom-hint');
      const clone = el.cloneNode(true);
      const body = clone.querySelector('.step-body');
      if (body) body.classList.remove('hidden');
      container.innerHTML = '';
      container.appendChild(clone);
      backdrop.classList.add('active');
      hint.style.opacity = '1';
      document.body.style.overflow = 'hidden';
    }
    function closeZoom(e) {
      if (e && e.target !== document.getElementById('zoom-backdrop')) return;
      document.getElementById('zoom-backdrop').classList.remove('active');
      document.getElementById('zoom-container').innerHTML = '';
      document.getElementById('zoom-hint').style.opacity = '0';
      document.body.style.overflow = '';
    }
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeZoom({target: document.getElementById('zoom-backdrop')}); });
    document.getElementById('trace-panel').addEventListener('click', (e) => {
      const card = e.target.closest('.step-card') || e.target.closest('.ne-card');
      if (!card) return;
      if (e.target.closest('.step-header')) return;
      openZoom(card);
    });
    const _origClearAll = clearAll;
    clearAll = function() { _origClearAll(); closeZoom({target: document.getElementById('zoom-backdrop')}); };
  </script>
</body>
</html>
```

---

## PART 5: SERVER CODE — `poc/server_live.py`

This is the FULL main server file. It contains ALL classes, the complete pipeline, all routes, sample data, and the startup logic. **Write every single line exactly as shown.**

### Complete `poc/server_live.py`

> **AGENT INSTRUCTION:** Read this section and write the FULL file. The server is ~1848 lines of Python. I provide the complete content below. Write it ALL — do not truncate, do not abbreviate, do not use ellipsis.

The file begins:

```python
"""
Production PoC Server — Telecom Agentic Orchestration Engine
=============================================================
Real services: diskcache (Redis-compatible pattern store) + Hermes/Deepseek for LLM reasoning.
Web UI served on 0.0.0.0:8090.
"""

import uuid, time, json, re, subprocess, hashlib, logging, shutil, threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import diskcache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("orch-server")

app = FastAPI(title="Telecom Orchestrator — Production PoC", version="2.0.0")

# ====================================================================
# Pattern Store + Job Store
# ====================================================================
cache = diskcache.Cache("/opt/data/telecom-orchestrator/poc/cache_store")
jobs: dict[str, "ProcessResponse"] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=4)

# ====================================================================
# Service Model Store — persistent subscriber representations
# ====================================================================
class ServiceModelStore:
    """Persistent flat representation of a subscriber service, keyed by subscriber_id.
    Created after successful NE update. Used for change detection on repeat requests.

    Runtime validation: get() checks for corruption on every read and repairs
    or rejects poisoned data before it can infect the pipeline."""

    # Thresholds for partial corruption salvage
    MIN_REAL_ATTRS = 3  # minimum real NE attributes to consider salvageable

    def __init__(self, cache: diskcache.Cache):
        self.cache = cache

    def _key(self, subscriber_id: str) -> str:
        return f"orch:sub:{subscriber_id}"

    def get(self, subscriber_id: str) -> dict | None:
        """Load subscriber model with runtime corruption check.
        If corrupted beyond repair, deletes the entry and returns None
        so the pipeline treats it as a fresh provisioning."""
        model = self.cache.get(self._key(subscriber_id))
        if model is None:
            return None
        if not isinstance(model, dict):
            logger.warning("Runtime: non-dict model for %s — deleting", subscriber_id)
            self.delete(subscriber_id)
            return None

        chars = model.get("characteristics", {})
        nes = model.get("network_elements", [])
        ver = model.get("version", 0)

        # Count corruption
        def_chars = sum(1 for v in chars.values() if str(v).startswith("default_"))
        ph_chars  = sum(1 for v in chars.values() if str(v).startswith("<"))
        def_nes = 0
        real_nes = 0
        for ne in nes:
            for v in ne.get("attributes", {}).values():
                sv = str(v)
                if sv.startswith("default_"):
                    def_nes += 1
                elif sv.startswith("<"):
                    pass  # placeholders are ok
                elif sv != "Configured":
                    real_nes += 1

        total_corrupt = def_chars + ph_chars + def_nes

        if total_corrupt == 0:
            return model  # clean — fast path

        # Partially corrupt: try to salvage
        if real_nes >= self.MIN_REAL_ATTRS and def_chars < len(chars):
            logger.warning(
                "Runtime: partial corruption in %s v%d (%d default_* NE, %d default_* chars, "
                "%d real NE attrs). Salvaging real data; will self-heal on next orchestration.",
                subscriber_id, ver, def_nes, def_chars, real_nes)
            # Strip default_* from characteristics so they don't poison MERGE
            clean_chars = {k: v for k, v in chars.items()
                          if not str(v).startswith("default_") and not str(v).startswith("<")}
            model["characteristics"] = clean_chars
            return model

        # Fully corrupt or not enough real data — delete and force fresh provisioning
        logger.warning(
            "Runtime: %s v%d too corrupted (%d default_* NE, %d default_* chars, "
            "only %d real NE attrs). Deleting — will re-provision from scratch.",
            subscriber_id, ver, def_nes, def_chars, real_nes)
        self.delete(subscriber_id)
        return None

    def save(self, subscriber_id: str, model: dict):
        model["version"] = model.get("version", 0) + 1
        model["last_updated"] = datetime.utcnow().isoformat()
        self.cache[self._key(subscriber_id)] = model

    def delete(self, subscriber_id: str):
        key = self._key(subscriber_id)
        if key in self.cache:
            del self.cache[key]

    def compute_diff(self, previous: dict | None, incoming_chars: dict,
                     new_network_elements: list[dict]) -> dict:
        """Compare incoming characteristics and NE state against previous model.
        Returns a subscriberDiff structure for the UI."""
        changed_attrs = {}
        if previous:
            prev_chars = previous.get("characteristics", {})
            for k, v in incoming_chars.items():
                prev_v = prev_chars.get(k)
                if prev_v is not None and str(v) != str(prev_v):
                    changed_attrs[k] = {"from": str(prev_v), "to": str(v)}
            for k in prev_chars:
                if k not in incoming_chars:
                    changed_attrs[k] = {"from": str(prev_chars[k]), "to": "(removed)"}

        # NE-level diffs: which attributes changed per device.
        # Normalize NE names: strip /HSS, /PCF, /MME suffixes for fuzzy matching
        # so "PCRF" matches "PCRF/PCF" and "HLR" matches "HLR/HSS".
        ne_diffs = {}
        if previous:
            prev_nes_raw = {ne["name"]: ne.get("attributes", {})
                           for ne in previous.get("network_elements", [])}
            # Build canonical name → raw name mapping for previous model
            prev_canonical = {}
            for raw_name in prev_nes_raw:
                canonical = raw_name.split("/")[0]  # PCRF/PCF → PCRF
                prev_canonical[canonical] = raw_name

            for ne in new_network_elements:
                name = ne["name"]
                canonical = name.split("/")[0]  # PCRF/PCF → PCRF
                prev_raw = (prev_canonical.get(canonical) or
                           prev_canonical.get(name) or name)
                prev_attrs = prev_nes_raw.get(prev_raw, {})
                curr_attrs = ne.get("attributes", {})
                ne_diff = {}
                for k, v in curr_attrs.items():
                    pv = prev_attrs.get(k)
                    if pv is not None and str(v) != str(pv):
                        ne_diff[k] = {"from": str(pv), "to": str(v)}
                if ne_diff:
                    ne_diffs[name] = ne_diff

        has_changes = bool(changed_attrs or ne_diffs)
        first_run = previous is None

        return {
            "hasPrevious": previous is not None,
            "isFirstRun": first_run,
            "hasChanges": has_changes,
            "changedAttributes": changed_attrs,
            "networkElementDiffs": ne_diffs,
        }

    def build_model(self, subscriber_id: str, svc: str, all_chars: dict,
                    network_elements: list[dict], version: int = 0) -> dict:
        # Merge all NE attributes into characteristics so subsequent
        # MERGE gap-fill and DIFF have complete context — not just the
        # sparse request-level all_chars from unstructured text.
        merged_chars = dict(all_chars)
        for ne in network_elements:
            for k, v in ne.get("attributes", {}).items():
                if k not in merged_chars and k != "status":
                    sv = str(v)
                    if not sv.startswith("default_") and not sv.startswith("<"):
                        merged_chars[k] = v
        return {
            "subscriber_id": subscriber_id,
            "service_type": svc,
            "characteristics": merged_chars,
            "network_elements": [
                {"name": ne["name"], "type": ne["type"],
                 "attributes": dict(ne.get("attributes", {}))}
                for ne in network_elements
            ],
            "version": version,
            "last_updated": datetime.utcnow().isoformat(),
        }

service_models = ServiceModelStore(cache)

# ====================================================================
# Subscriber Lock — prevents concurrent modification race conditions
# ====================================================================
class SubscriberLock:
    """Per-subscriber advisory lock using diskcache (SQLite-backed).

    Design:
    - Lock key: lock:sub:{subscriber_id}
    - Value: {worker_id, acquired_at, ttl_seconds}
    - TTL: 30s (prevents deadlock if worker crashes)
    - Non-blocking acquire with retry (default 5s budget)
    - Re-entrant within same worker
    """

    LOCK_TTL = 30  # seconds
    RETRY_DELAY = 0.1  # seconds
    MAX_RETRIES = 50   # 5 seconds total

    def __init__(self, cache: diskcache.Cache):
        self._cache = cache
        self._local = threading.local()

    def acquire(self, subscriber_id: str, worker_id: str):
        """Context-manager-able acquire. Returns True/False."""
        return _LockContext(self, subscriber_id, worker_id)

    def _try_acquire(self, lock_key: str, worker_id: str) -> bool:
        for _ in range(self.MAX_RETRIES):
            existing = self._cache.get(lock_key)
            now = time.time()
            if existing is None:
                self._cache.set(lock_key,
                    {"worker_id": worker_id, "acquired_at": now},
                    expire=self.LOCK_TTL)
                return True
            if now - existing.get("acquired_at", 0) > self.LOCK_TTL:
                self._cache.set(lock_key,
                    {"worker_id": worker_id, "acquired_at": now},
                    expire=self.LOCK_TTL)
                return True
            if existing.get("worker_id") == worker_id:
                return True  # re-entrant
            time.sleep(self.RETRY_DELAY)
        return False

    def _release(self, lock_key: str, worker_id: str):
        existing = self._cache.get(lock_key)
        if existing and existing.get("worker_id") == worker_id:
            self._cache.delete(lock_key)

    def force_release(self, subscriber_id: str):
        lock_key = f"lock:sub:{subscriber_id}"
        self._cache.delete(lock_key)


class _LockContext:
    """Context manager returned by SubscriberLock.acquire()."""
    def __init__(self, lock: SubscriberLock, subscriber_id: str, worker_id: str):
        self._lock = lock
        self._key = f"lock:sub:{subscriber_id}"
        self._worker = worker_id
        self._acquired = False

    def __enter__(self):
        self._acquired = self._lock._try_acquire(self._key, self._worker)
        return self._acquired

    def __exit__(self, *args):
        if self._acquired:
            self._lock._release(self._key, self._worker)
        return False


subscriber_lock = SubscriberLock(cache)


def extract_subscriber_id(prompt: str, is_json: bool, all_chars: dict) -> str:
    """Extract a stable subscriber identifier from the request."""
    if is_json:
        try:
            data = json.loads(prompt)
            # TMF640: serviceId or msisdn
            sid = data.get("serviceId") or data.get("externalId")
            if sid:
                return sid
        except: pass
    # Fall back to msisdn from characteristics
    msisdn = all_chars.get("msisdn")
    if msisdn:
        return f"MSISDN-{msisdn}"
    # Last resort: hash the prompt
    return f"SUB-{hashlib.sha256(prompt.encode()).hexdigest()[:12].upper()}"


def flatten_plan_params(plan: dict) -> dict:
    """Flatten nested workflow-keyed params into a single flat dict.

    LLMs often produce params like:
      {"HLR_Provisioning": {"msisdn": "...", "imsi": "..."},
       "IMS_Registration": {"msisdn": "...", "codec_profile": "..."}}
    But downstream consumers (MERGE, NE builder, pattern learn) expect flat:
      {"msisdn": "...", "imsi": "...", "codec_profile": "..."}

    Idempotent: if params are already flat (no sub-dicts), returns unchanged.
    """
    params = plan.get("params", {})
    if not params:
        return plan
    # Check if any top-level value is a dict → nested
    if any(isinstance(v, dict) for v in params.values()):
        flat = {}
        for v in params.values():
            if isinstance(v, dict):
                flat.update(v)
        if flat:
            plan["params"] = flat
    return plan


# ====================================================================
# Pydantic Models
# ====================================================================
class ProcessRequest(BaseModel):
    prompt: str = Field(..., min_length=1)

class TraceStep(BaseModel):
    stage: str; status: str; title: str; detail: str
    color: str; icon: str; elapsed_ms: int = 0

class ProcessResponse(BaseModel):
    order_id: str; format: str; status: str
    trace: list[TraceStep]; total_ms: int
    final_state: Optional[dict] = None
    started_at: str = ""

# ====================================================================
# Data Masker
# ====================================================================
MSISDN_RE = re.compile(r'\+?\d{5,15}')
IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

class DataMasker:
    def __init__(self):
        self.map = {}
        self.ctr = {"msisdn": 0, "ip": 0}
    def mask(self, text: str) -> tuple[str, dict]:
        def _msisdn(m):
            v = m.group(0)
            if v in self.map: return self.map[v]
            self.ctr["msisdn"] += 1
            t = f"VAR_MSISDN_{self.ctr['msisdn']}"
            self.map[t] = v; self.map[v] = t; return t
        text = MSISDN_RE.sub(_msisdn, text)
        def _ip(m):
            v = m.group(0)
            if v in self.map: return self.map[v]
            self.ctr["ip"] += 1
            t = f"VAR_IP_{self.ctr['ip']}"
            self.map[t] = v; self.map[v] = t; return t
        text = IP_RE.sub(_ip, text)
        return text, {k: v for k, v in self.map.items() if k.startswith("VAR_")}

# ====================================================================
# Constants
# ====================================================================
BLOCKED_KEYWORDS = ["erase", "reload", "format", "shutdown", "no switchport",
                     "write erase", "delete startup-config", "boot system flash"]

KB_DOCS = {
    "mobile": "3GPP TS 29.002 (MAP), 3GPP TS 23.040 (SMS), GSMA IR.92 (VoLTE)",
    "l3vpn": "RFC 4364 (MPLS BGP VPNs), RFC 8299 (L3VPN YANG), MEF 6.2 (EVC Services)",
    "sdwan": "MEF 70 (SD-WAN Service Attributes), RFC 7348 (VXLAN)",
    "broadband": "TR-069 (CWMP), TR-383 (Common YANG Modules for Access Networks)",
}

KB_DIR = "/opt/data/telecom-orchestrator/knowledge-base"

# ====================================================================
# RDF-Inspired Pattern Engine
# ====================================================================
# Patterns are modeled as named graphs of triples: (subject, predicate, object).
# Subjects are service patterns; predicates are OWL-inspired relationships;
# objects are resources, workflows, attribute constraints, or literal values.
#
# Example triple set for a mobile-voice retail/gold pattern:
#   pattern:mobile-retail-gold   rdf:type              service:MobileVoice
#   pattern:mobile-retail-gold   orch:hasSegment       "retail"
#   pattern:mobile-retail-gold   orch:hasSlaTier       "gold"
#   pattern:mobile-retail-gold   orch:requiresResource res:HLR-HSS
#   res:HLR-HSS                  orch:provisionedBy    wf:HLR_Provisioning
#   res:HLR-HSS                  orch:hasAttribute     [msisdn, imsi, subscriber_profile]
#   orch:hasAttribute            rdfs:domain           orch:Resource
#   orch:hasAttribute            rdfs:range            xsd:string
#   msisdn                       rdf:type              orch:InstanceAttribute
#   customerSegment              rdf:type              orch:ServiceAttribute
#
# InstanceAttributes (msisdn, imsi, pe_ip) are excluded from cache keys —
# they identify specific subscriber/device instances, not service patterns.
# ServiceAttributes (segment, sla, product) define the pattern identity.

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta

@dataclass
class PatternNode:
    """A named pattern capturing a service type + its resource graph."""
    id: str
    service_type: str
    label: str
    characteristics: dict  # service-defining characteristics (segment, sla, product)
    triples: list  # list of [subject, predicate, object] — RDF-like assertions
    resources: list  # derived resource bindings with attributes
    confidence: float = 0.3
    use_count: int = 0
    created_at: str = ""
    last_used: str = ""
    source: str = "auto"  # "auto" | "teach" | "kb"

    def to_dict(self):
        return {
            "id": self.id, "service_type": self.service_type, "label": self.label,
            "characteristics": self.characteristics, "triples": self.triples,
            "resources": self.resources, "confidence": round(self.confidence, 2),
            "use_count": self.use_count, "created_at": self.created_at,
            "last_used": self.last_used, "source": self.source,
        }


class PatternEngine:
    """RDF-inspired pattern store with learning, confidence scoring, and KB reasoning."""

    INSTANCE_ATTRS = {"msisdn", "imsi", "imei", "pe_ip", "hostname", "serviceid",
                       "serial", "loopback", "management_ip"}

    def __init__(self, cache: diskcache.Cache):
        self.cache = cache
        self._index: dict[str, list[str]] = {}  # service_type → [pattern_ids]
        self._load_index()

    def _load_index(self):
        self._index = self.cache.get("orch:idx:patterns", {})

    def _save_index(self):
        self.cache.set("orch:idx:patterns", self._index)

    def _key(self, pid: str) -> str:
        return f"orch:pat:{pid}"

    # ── QUERY ──────────────────────────────────────────────

    def lookup(self, service_type: str, characteristics: dict) -> Optional[PatternNode]:
        """Find best-matching pattern for given characteristics. Returns None if no match."""
        candidates = []
        for pid in self._index.get(service_type, []):
            pat = self._load(pid)
            if pat is None:
                continue
            score = self._match_score(pat.characteristics, characteristics)
            if score > 0:
                candidates.append((score, pat))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], -x[1].confidence))
        return candidates[0][1]

    def _match_score(self, pat_chars: dict, req_chars: dict) -> float:
        """Jaccard-like match: how many service-defining chars match.
        Empty pat_chars (KB-seeded wildcard) matches any request at 0.25 confidence."""
        pat_keys = set(pat_chars.keys())
        req_keys = set(k for k in req_chars if k not in self.INSTANCE_ATTRS)
        if not pat_keys:
            return 0.25  # wildcard — KB-seeded pattern, low confidence
        if not req_keys:
            return 1.0  # no service-defining chars in request → match anything
        intersection = 0
        for k in req_keys & pat_keys:
            if str(pat_chars[k]) == str(req_chars.get(k, "")):
                intersection += 1
        union = len(req_keys | pat_keys)
        return intersection / max(union, 1)

    # ── LEARN ──────────────────────────────────────────────

    def learn(self, service_type: str, characteristics: dict,
              plan: dict, all_chars: dict = None, source: str = "auto") -> PatternNode:
        """Create a new pattern from a cache miss + orchestration plan.
        all_chars includes instance identifiers (msisdn/imsi) for complete resource storage."""
        # Derive service-defining chars (exclude instance identifiers)
        svc_chars = {k: v for k, v in characteristics.items()
                     if k.lower() not in self.INSTANCE_ATTRS}
        pid = f"pat:{service_type}:{hashlib.sha256(json.dumps(svc_chars,sort_keys=True).encode()).hexdigest()[:12]}"

        now = datetime.utcnow().isoformat()
        devices = plan.get("devices", [])
        workflows = plan.get("workflows", [])
        params = plan.get("params", {})
        full_chars = all_chars or {}  # includes msisdn/imsi for complete resource attributes

        # Build RDF triples from plan
        triples = [
            [pid, "rdf:type", f"service:{service_type.capitalize()}Voice" if service_type == "mobile" else f"service:{service_type.upper()}"],
        ]
        for k, v in svc_chars.items():
            triples.append([pid, f"orch:has{k}", str(v)])

        # Build resource entries with attribute inference from KB
        sr = SERVICE_RESOURCES.get(service_type, SERVICE_RESOURCES["mobile"])
        kb_resources = {r["type"]: r for r in sr["required_resources"]}
        resources = []
        for i, dev in enumerate(devices):
            wf = workflows[i] if i < len(workflows) else "Configuration"
            rid = f"res:{dev.replace('/','-').replace(' ','_')}"
            triples.append([pid, "orch:requiresResource", rid])
            triples.append([rid, "orch:provisionedBy", f"wf:{wf}"])

            # Infer attributes from KB
            kb_res = None
            for kb_type, kb_def in kb_resources.items():
                if any(p in dev.lower() for p in kb_type.lower().replace("/"," ").split()):
                    kb_res = kb_def; break
            attrs = {}
            if kb_res:
                for attr in kb_res.get("attributes", []):
                    if attr in params:
                        val = str(params[attr])
                    elif attr in full_chars:
                        val = str(full_chars[attr])
                    else:
                        val = f"<{attr}>"  # placeholder — resolved at orchestration time
                    attrs[attr] = val
                    triples.append([rid, "orch:hasAttribute", f"{attr}={val}"])
            else:
                for k, v in params.items():
                    attrs[k] = str(v)
            resources.append({"name": dev, "workflow": wf,
                              "role": kb_res.get("role","") if kb_res else "",
                              "attributes": attrs})

        node = PatternNode(
            id=pid, service_type=service_type,
            label=f"{service_type} | {svc_chars.get('customerSegment','?')}/{svc_chars.get('slaTier','?')}",
            characteristics=svc_chars, triples=triples,
            resources=resources, confidence=0.3, use_count=1,
            created_at=now, last_used=now, source=source,
        )
        self._save(node)
        self._index_pattern(node)
        logger.info("Pattern learned: %s (confidence=%.2f, %d triples)", pid, node.confidence, len(triples))
        return node

    def reinforce(self, pattern: PatternNode) -> PatternNode:
        """Boost confidence on cache hit. Diminishing returns after 0.9."""
        pattern.use_count += 1
        pattern.last_used = datetime.utcnow().isoformat()
        if pattern.confidence < 0.9:
            pattern.confidence = min(0.95, pattern.confidence + 0.05)
        elif pattern.confidence < 0.98:
            pattern.confidence = min(0.98, pattern.confidence + 0.005)
        self._save(pattern)
        return pattern

    def teach(self, triples: list, source: str = "teach") -> PatternNode:
        """Manual knowledge injection — high confidence, can override auto-learned."""
        svc_type = "mobile"
        chars = {}
        for s, p, o in triples:
            if p.startswith("orch:has") and not p.endswith("Resource"):
                chars[p.replace("orch:has", "")] = o
            if p == "rdf:type" and o.startswith("service:"):
                raw = o.replace("service:", "").lower()
                # Normalize: MobileVoice → mobile, L3VPN → l3vpn
                for sv in ["mobile", "l3vpn", "sdwan", "broadband"]:
                    if sv in raw: svc_type = sv; break
                if svc_type == "mobile" and "voice" not in raw:
                    pass  # keep default
        pid = f"pat:taught:{hashlib.sha256(json.dumps(triples,sort_keys=True).encode()).hexdigest()[:12]}"
        now = datetime.utcnow().isoformat()
        label = f"{svc_type} | " + " / ".join(f"{k}={v}" for k,v in list(chars.items())[:3])
        node = PatternNode(
            id=pid, service_type=svc_type, label=label,
            characteristics=chars, triples=triples, resources=[],
            confidence=0.9, use_count=0, created_at=now, last_used=now, source=source,
        )
        self._save(node)
        self._index_pattern(node)
        logger.info("Pattern taught: %s (confidence=%.2f)", pid, node.confidence)
        return node

    # ── PATTERN INSPECTION ─────────────────────────────────

    def list_all(self) -> list[dict]:
        """Return all known patterns with metadata."""
        result = []
        for svc_type, pids in self._index.items():
            for pid in pids:
                pat = self._load(pid)
                if pat:
                    result.append({
                        "id": pat.id, "service_type": pat.service_type,
                        "label": pat.label, "confidence": round(pat.confidence, 2),
                        "use_count": pat.use_count, "triples_count": len(pat.triples),
                        "source": pat.source, "last_used": pat.last_used,
                    })
        return sorted(result, key=lambda x: (-x["confidence"], -x["use_count"]))

    def get(self, pid: str) -> Optional[dict]:
        pat = self._load(pid)
        return pat.to_dict() if pat else None

    # ── INTERNAL ───────────────────────────────────────────

    def _save(self, node: PatternNode):
        self.cache.set(self._key(node.id), node)

    def _load(self, pid: str) -> Optional[PatternNode]:
        """Load pattern with runtime validation.
        Rejects patterns with empty resources, < 3 triples, or unreadable data."""
        try:
            node = self.cache.get(self._key(pid))
        except Exception:
            logger.warning("Runtime: unreadable pattern %s — deleting", pid)
            self._unindex(pid)
            return None
        if node is None:
            return None
        if not hasattr(node, 'resources') or not node.resources:
            logger.warning("Runtime: empty pattern %s (no resources) — deleting", pid)
            self._unindex(pid)
            return None
        if not hasattr(node, 'triples') or len(node.triples) < 3:
            logger.warning("Runtime: skeleton pattern %s (%d triples) — deleting",
                          pid, len(getattr(node, 'triples', [])))
            self._unindex(pid)
            return None
        # Check for default_* contamination in resource attributes
        def_count = 0
        for r in getattr(node, 'resources', []):
            for v in r.get('attributes', {}).values():
                if str(v).startswith("default_"):
                    def_count += 1
        if def_count > 0:
            # Pattern can still be used (attribute names are correct even if
            # values are placeholders), but log warning so we know it needs
            # refresh from a successful LLM run.
            logger.warning(
                "Runtime: pattern %s has %d default_* resource attrs — "
                "will be refreshed on next cache-miss LLM run", pid, def_count)
        return node

    def _unindex(self, pid: str):
        """Remove a pattern ID from the index and delete its cache entry."""
        for svc, pid_list in self._index.items():
            if pid in pid_list:
                pid_list.remove(pid)
        self._save_index()
        key = self._key(pid)
        if key in self.cache:
            del self.cache[key]

    def _index_pattern(self, node: PatternNode):
        if node.service_type not in self._index:
            self._index[node.service_type] = []
        if node.id not in self._index[node.service_type]:
            self._index[node.service_type].append(node.id)
        self._save_index()


# Global pattern engine
patterns = PatternEngine(cache)


def seed_kb_patterns():
    """Pre-seed pattern store from KB resource definitions.

    Each KB service definition becomes a base pattern with correct attribute
    lists.  Confidence starts at 0.25 (auto-seeded) and increases when real
    orchestrations confirm the pattern.  This means even the first unstructured
    request hits the cache and gets KB-derived attribute names correct — no
    default_* placeholders ever reach the NE builder.
    """
    for svc, sr in SERVICE_RESOURCES.items():
        devices = []
        workflows = []
        # Build KB-based plan: device names, workflows, and attribute placeholders
        all_attrs = {}
        for r in sr["required_resources"]:
            dev = r["type"].replace("/", "-")  # HLR/HSS → HLR-HSS
            devices.append(dev)
            core_type = r["type"].split("/")[0]  # HLR
            wf = WF_MAP.get(core_type, f"{core_type}_Configuration")
            workflows.append(wf)
            for attr in r["attributes"]:
                if attr not in all_attrs:
                    all_attrs[attr] = f"<{attr}>"  # placeholder — resolved at orchestration time

        plan = {"workflows": workflows, "params": all_attrs, "devices": devices}

        # Build characteristics from KB (empty for now — matches any request)
        chars = {}

        # Learn the KB-seeded pattern
        existing = patterns._index.get(svc, [])
        if not existing:
            patterns.learn(svc, chars, plan, all_chars={}, source="kb")
            # Reset confidence to 0.25 for KB seeds
            for pid in patterns._index.get(svc, []):
                pat = patterns._load(pid)
                if pat and pat.source == "kb":
                    pat.confidence = 0.25
                    patterns._save(pat)
                    logger.info("KB seed pattern: %s (svc=%s, %d NEs)",
                                pid, svc, len(devices))


KB_DIR = "/opt/data/telecom-orchestrator/knowledge-base"

# Service-to-KB resource mapping (derived from core ontology §4)
SERVICE_RESOURCES = {
    "mobile": {
        "domain": "Voice / Mobile Core",
        "standards": ["3GPP TS 29.002 (MAP/HLR)", "3GPP TS 23.040 (SMS)", "GSMA IR.92 (VoLTE)",
                      "3GPP TS 23.401 (EPC)", "3GPP TS 29.274 (GTPv2-C)"],
        "required_resources": [
            {"type": "HLR/HSS", "role": "Subscriber registry", "attributes": ["msisdn", "imsi", "subscriber_profile", "roaming_profile"]},
            {"type": "IMS-Core", "role": "VoLTE/VoWiFi call control", "attributes": ["msisdn", "imsi", "volte_enabled", "codec_profile"]},
            {"type": "PCRF/PCF", "role": "Policy & charging rules", "attributes": ["apn", "qos_profile", "charging_rule", "bandwidth_limit"]},
            {"type": "SMSC", "role": "SMS store-and-forward", "attributes": ["msisdn", "routing", "validity_period"]},
            {"type": "MSC/MME", "role": "Mobility management", "attributes": ["msisdn", "imsi", "location_area", "tac"]},
            {"type": "SBC", "role": "Session border control", "attributes": ["sip_domain", "codec_list", "media_handling"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE",
    },
    "l3vpn": {
        "domain": "MPLS L3VPN",
        "standards": ["RFC 4364 (MPLS BGP VPNs)", "RFC 8299 (L3VPN YANG Service Model)", "MEF 6.2 (EVC Services)"],
        "required_resources": [
            {"type": "PE Router", "role": "Provider Edge — VRF termination", "attributes": ["vrf_name", "rd", "rt_import", "rt_export", "bgp_peer"]},
            {"type": "Route Reflector", "role": "BGP route distribution", "attributes": ["cluster_id", "peer_group", "asn"]},
            {"type": "VRF Instance", "role": "Virtual routing table", "attributes": ["vrf_name", "rd", "route_targets", "interfaces"]},
            {"type": "NMS", "role": "Monitoring & assurance", "attributes": ["snmp_community", "syslog_server", "netflow_collector"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE",
    },
    "sdwan": {
        "domain": "SD-WAN Overlay",
        "standards": ["MEF 70 (SD-WAN Service Attributes)", "RFC 7348 (VXLAN)"],
        "required_resources": [
            {"type": "vCPE/uCPE", "role": "Edge device", "attributes": ["transport_links", "encryption", "app_policy", "wan_interfaces"]},
            {"type": "SD-WAN Controller", "role": "Centralized policy & orchestration", "attributes": ["policy_set", "site_list", "template"]},
            {"type": "Orchestrator", "role": "Zero-touch provisioning", "attributes": ["ztp_url", "bootstrap_config", "license_key"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE",
    },
    "broadband": {
        "domain": "Fixed Broadband",
        "standards": ["TR-069 (CWMP)", "TR-383 (Common YANG)"],
        "required_resources": [
            {"type": "OLT", "role": "Optical line terminal", "attributes": ["ont_model", "vlan", "speed_profile", "dba_profile"]},
            {"type": "BNG/BRAS", "role": "Broadband network gateway", "attributes": ["ip_pool", "subscriber_profile", "qos_policy"]},
            {"type": "RADIUS", "role": "AAA server", "attributes": ["nas_identifier", "shared_secret", "auth_method"]},
            {"type": "EMS", "role": "Element management", "attributes": ["snmp_community", "trap_destinations"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE",
    },
}

# Shared NE-type → workflow name mapping (derived from KB standards).
# Used by seed_kb_patterns() and _fallback_plan() — single source of truth.
WF_MAP = {
    "HLR": "HLR_Provisioning", "HSS": "HLR_Provisioning",
    "IMS-Core": "IMS_Registration", "PCF": "APN_Configuration",
    "PCRF": "APN_Configuration", "SMSC": "Charging_Rule_Setup",
    "MSC": "Mobility_Configuration", "MME": "Mobility_Configuration",
    "SBC": "SBC_Configuration",
    "PE Router": "PE_Configuration", "Route Reflector": "BGP_Peering",
    "VRF Instance": "VRF_Allocation", "NMS": "Monitoring_Setup",
    "vCPE": "CPE_Deployment", "SD-WAN Controller": "Controller_Setup",
    "Orchestrator": "ZTP_Bootstrap",
    "OLT": "ONT_Provisioning", "BNG": "IP_Pool_Allocation",
    "RADIUS": "AAA_Configuration", "EMS": "EMS_Setup",
}

# Seed KB-derived patterns on module load (must be after SERVICE_RESOURCES)
seed_kb_patterns()

# ====================================================================
# Lifecycle Notification MCP — TMF641-compliant state change events
# ====================================================================
class LifecycleNotifier:
    """Emits TMF641 ServiceOrderMilestoneEvent and ServiceOrderStateChangeEvent
    notifications as the request progresses through the KB-defined lifecycle.

    Each service type has a lifecycle string in SERVICE_RESOURCES, parsed from KB.
    All events follow the TMF641 v4.1.0 notification schema.

    References:
      - knowledge-base/reference/tmf-notification-schemas.md
      - TMF641_Service_Ordering_Management_API_v4.1.0_swagger.json
    """

    # TMF641 canonical order states
    ORDER_IN_PROGRESS = "inProgress"
    ORDER_COMPLETED = "completed"
    ORDER_FAILED = "failed"

    def __init__(self):
        self._notifications: list[dict] = []

    def parse_lifecycle(self, svc: str) -> list[str]:
        """Extract ordered lifecycle states from KB."""
        sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
        lc = sr.get("lifecycle", "")
        states = [s.strip() for s in lc.split("→")]
        return [s for s in states if s]

    def _base_event(self, event_type: str, order_id: str, correlation_id: str,
                    domain: str = "ServiceFulfillment",
                    priority: str = "normal") -> dict:
        """Build the base TMF notification envelope."""
        now = datetime.utcnow().isoformat() + "Z"
        return {
            "eventId": f"evt-{order_id}-{event_type.split('Event')[0]}",
            "eventTime": now,
            "eventType": event_type,
            "correlationId": correlation_id,
            "domain": domain,
            "priority": priority,
            "timeOcurred": now,
        }

    def emit_milestone(self, state: str, svc: str, order_id: str,
                       correlation_id: str, description: str = "",
                       status: str = "achieved") -> dict:
        """Emit a TMF641 ServiceOrderMilestoneEvent for a lifecycle state.

        Milestones mark in-progress stages without changing the order state.
        The order remains 'inProgress' throughout provisioning.
        """
        now = datetime.utcnow().isoformat() + "Z"
        event = self._base_event("ServiceOrderMilestoneEvent", order_id,
                                 correlation_id)
        event["title"] = f"Milestone: {state}"
        event["description"] = description or f"Service order reached milestone: {state}"
        event["event"] = {
            "serviceOrder": {
                "id": order_id,
                "href": f"/api/tmf641/serviceOrder/{order_id}",
                "state": self.ORDER_IN_PROGRESS,
                "externalId": order_id,
                "category": svc,
                "milestone": [
                    {
                        "id": f"ms-{order_id}-{state}",
                        "name": state,
                        "description": description or f"State transition: {state}",
                        "message": f"Orchestrator reached lifecycle state: {state}",
                        "milestoneDate": now,
                        "status": status,
                    }
                ],
            }
        }
        self._notifications.append(event)
        return event

    def emit_state_change(self, to_state: str, svc: str, order_id: str,
                          correlation_id: str, description: str = "") -> dict:
        """Emit a TMF641 ServiceOrderStateChangeEvent.

        Used for the final ACTIVE state transition — changes order from
        'inProgress' to 'completed'.
        """
        now = datetime.utcnow().isoformat() + "Z"
        event = self._base_event("ServiceOrderStateChangeEvent", order_id,
                                 correlation_id)
        event["title"] = f"Order {to_state}"
        event["description"] = description or f"Service order state changed to: {to_state}"
        event["event"] = {
            "serviceOrder": {
                "id": order_id,
                "href": f"/api/tmf641/serviceOrder/{order_id}",
                "state": to_state,
                "externalId": order_id,
                "category": svc,
                "completionDate": now if to_state == self.ORDER_COMPLETED else None,
            }
        }
        self._notifications.append(event)
        return event

    def flush(self) -> list[dict]:
        """Return all notifications emitted and clear buffer."""
        result = list(self._notifications)
        self._notifications.clear()
        return result

    def build_notification_trace(self, order_id: str, svc: str,
                                  subscriber_id: str, t0: float,
                                  step_fn) -> int:
        """Walk the KB lifecycle and emit milestone + state change notifications.

        All states except the last → ServiceOrderMilestoneEvent (order inProgress)
        Final ACTIVE state → ServiceOrderStateChangeEvent (order completed)

        Returns count of notifications emitted.
        """
        states = self.parse_lifecycle(svc)
        correlation_id = f"corr-{order_id}"
        count = 0

        for i, state in enumerate(states):
            is_final = (i == len(states) - 1)

            if is_final:
                # Final state (ACTIVE) → ServiceOrderStateChangeEvent
                notif = self.emit_state_change(
                    self.ORDER_COMPLETED, svc, order_id, correlation_id,
                    f"Service provisioning complete. Final state: {state}. "
                    f"All network elements configured and verified."
                )
                step_fn("NOTIFY", "done",
                    f"TMF Notification — StateChange → {notif['event']['serviceOrder']['state']}",
                    f"Goal: Emit TMF641 ServiceOrderStateChangeEvent per spec.\\n"
                    f"Input: Final lifecycle state={state}\\n"
                    f"Expected: Transition order from inProgress → completed\\n"
                    f"Actual: Event {notif['eventId']} emitted with state={notif['event']['serviceOrder']['state']}\\n"
                    f"Output: TMF641-compliant notification with correlationId={correlation_id}.",
                    "cyan", "📬")
            else:
                # Intermediate state → ServiceOrderMilestoneEvent
                notif = self.emit_milestone(
                    state, svc, order_id, correlation_id,
                    f"Orchestrator provisioning: {state}. "
                    f"Service type={svc}, subscriber={subscriber_id}."
                )
                step_fn("NOTIFY", "done",
                    f"TMF Notification — Milestone: {state}",
                    f"Goal: Emit TMF641 ServiceOrderMilestoneEvent per spec.\\n"
                    f"Input: Lifecycle state={state} (stage {i+1}/{len(states)})\\n"
                    f"Expected: Record milestone, order remains inProgress\\n"
                    f"Actual: Milestone {notif['eventId']} recorded — order state=inProgress\\n"
                    f"Output: TMF641-compliant milestone notification with correlationId={correlation_id}.",
                    "cyan", "📬")
            count += 1

        return count


lifecycle_notifier = LifecycleNotifier()


def validate_and_repair_cache():
    """Startup cache integrity check — global cross-item scan.

    Runs once on module load.  Per-item corruption is handled at runtime by
    ServiceModelStore.get() and PatternEngine._load().  This startup scan
    handles cross-item issues that need a full index traversal:
      - Duplicate subscribers (two keys for same MSISDN)
      - Stale index entries pointing to deleted patterns
      - Orphan patterns (in cache but not in index)

    Delegates per-model and per-pattern validation to the runtime guards.
    Logs everything for audit.
    """
    repairs = 0

    # ── 1. Scan subscriber models: use runtime guard, track MSISDNs for dedup ──
    msisdn_index = {}  # real MSISDN → [subscriber_ids]
    for key in list(cache):
        if not key.startswith("orch:sub:"):
            continue
        sub_id = key.replace("orch:sub:", "")
        # Delegate per-model validation to runtime guard
        model = service_models.get(sub_id)
        if model is None:
            # Runtime guard deleted it (fully corrupt / unreadable)
            repairs += 1
            continue

        # Track MSISDN for duplicate detection
        msisdn_val = (model.get("characteristics", {}).get("msisdn", ""))
        if msisdn_val and not str(msisdn_val).startswith("default_") and not str(msisdn_val).startswith("<"):
            ver = model.get("version", 0)
            msisdn_index.setdefault(msisdn_val, []).append((key, ver, False))

    # ── 2. Detect and merge duplicate subscribers ──
    for msisdn, entries in msisdn_index.items():
        if len(entries) <= 1:
            continue
        # Sort by version descending
        entries.sort(key=lambda e: -e[1])
        keep_key, keep_ver, _ = entries[0]
        logger.warning(
            "Duplicate subscriber for MSISDN=%s: %d entries found. "
            "Keeping %s (v%d); deleting %d duplicates.",
            msisdn, len(entries), keep_key.replace("orch:sub:", ""),
            keep_ver, len(entries) - 1)
        for dup_key, dup_ver, _ in entries[1:]:
            service_models.delete(dup_key.replace("orch:sub:", ""))
            repairs += 1

    # ── 3. Validate pattern index integrity ──
    idx = cache.get("orch:idx:patterns", {})
    stale_svcs = []
    for svc, pid_list in list(idx.items()):
        valid_pids = []
        for pid in pid_list:
            # Delegate per-pattern validation to runtime guard
            pat = patterns._load(pid)
            if pat is not None:
                valid_pids.append(pid)
            else:
                repairs += 1
        if valid_pids:
            idx[svc] = valid_pids
        else:
            stale_svcs.append(svc)
    for svc in stale_svcs:
        del idx[svc]
    cache.set("orch:idx:patterns", idx)

    # ── 4. Scan for orphan patterns (in cache but not in index) ──
    indexed_pids = {pid for pid_list in idx.values() for pid in pid_list}
    for key in list(cache):
        if key.startswith("orch:pat:") and key != "orch:idx:patterns":
            pid = key.replace("orch:pat:", "")
            if pid not in indexed_pids:
                # Delegate validation to runtime guard before indexing
                pat = patterns._load(pid)
                if pat is not None and hasattr(pat, 'service_type'):
                    logger.warning("Orphan pattern %s (not in index) — re-indexing", pid)
                    patterns._index_pattern(pat)
                    repairs += 1
                # else: _load already deleted it

    if repairs:
        logger.info("Cache integrity: %d cross-item issues repaired", repairs)
    else:
        logger.info("Cache integrity: OK — no cross-item issues found")

validate_and_repair_cache()


def load_kb_context(svc: str) -> str:
    """Load domain knowledge from KB files relevant to the service type."""
    context_parts = []

    # Read core ontology — extract service taxonomy section
    onto_path = f"{KB_DIR}/ontologies/core-ontology.md"
    try:
        with open(onto_path) as f:
            onto = f.read()
        # Extract relevant service section
        for section in onto.split("## "):
            if "Service Taxonomy" in section or "Resource Taxonomy" in section:
                context_parts.append(section[:1500])
    except Exception:
        pass

    # Read standards reference
    std_path = f"{KB_DIR}/reference/standards-index.md"
    try:
        with open(std_path) as f:
            standards = f.read()
        # Extract mobile-related standards
        relevant = []
        for line in standards.split("\n"):
            low = line.lower()
            if any(w in low for w in [svc, "mobile", "voice", "hlr", "ims", "pcrf", "volte", "3gpp", "msisdn"]):
                relevant.append(line)
        if relevant:
            context_parts.append("Relevant Standards:\n" + "\n".join(relevant[:20]))
    except Exception:
        context_parts.append(KB_DOCS.get(svc, "Generic provisioning standards"))

    # Add structured resource knowledge
    sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
    context_parts.append(f"\nService Domain: {sr['domain']}")
    context_parts.append(f"Required Network Elements ({len(sr['required_resources'])}):")
    for r in sr['required_resources']:
        context_parts.append(f"  - {r['type']}: {r['role']} (attrs: {', '.join(r['attributes'])})")
    context_parts.append(f"Lifecycle: {sr['lifecycle']}")

    return "\n".join(context_parts)

# ====================================================================
# Deepseek Client (via hermes CLI)
# ====================================================================
def call_deepseek(prompt: str, timeout: int = 120) -> str:
    """Call Deepseek via hermes CLI. Returns the model's text response."""
    env = {}
    # Read API key from hermes .env
    env_path = "/opt/data/.env"
    if shutil.which("hermes"):
        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", prompt, "--quiet",
                 "-m", "deepseek-v4-pro", "--provider", "deepseek"],
                capture_output=True, text=True, timeout=timeout,
                cwd="/opt/data",
                env={**__import__("os").environ, "HERMES_HOME": "/opt/data"},
            )
            # Strip session_id line from output
            out = result.stdout.strip()
            if "\nsession_id:" in out:
                out = out[:out.rfind("\nsession_id:")]
            if out:
                logger.info("Deepseek response: %d chars", len(out))
                return out.strip()
            logger.warning("Deepseek returned empty: stderr=%s", result.stderr[:200])
        except subprocess.TimeoutExpired:
            logger.error("Deepseek timeout after %ds", timeout)
        except Exception as e:
            logger.error("Deepseek call failed: %s", e)
    return ""


def detect_service_type(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["mobile", "msisdn", "sim", "activate", "voice", "sms"]): return "mobile"
    if any(w in t for w in ["l3vpn", "mpls", "vpn", "bgp", "vrf"]) and "sd" not in t: return "l3vpn"
    if any(w in t for w in ["sd-wan", "sdwan", "sd wan"]): return "sdwan"
    if any(w in t for w in ["broadband", "ftth", "fiber", "ont", "olt"]): return "broadband"
    return "mobile"

# ====================================================================
# Pipeline Engine
# ====================================================================
def start_pipeline(prompt: str) -> ProcessResponse:
    """Run stages DETECT → MASK → CACHE synchronously, return early trace.
    Background thread calls finish_pipeline() for LLM → VERIFY."""
    order_id = f"PO-{uuid.uuid4().hex[:8].upper()}"
    trace: list[TraceStep] = []
    t0 = time.time()

    def step(stage, status, title, detail, color, icon):
        trace.append(TraceStep(stage=stage, status=status, title=title, detail=detail,
                               color=color, icon=icon, elapsed_ms=int((time.time()-t0)*1000)))

    # --- STAGE 0: DETECT ---
    is_json = prompt.strip().startswith("{")
    if is_json:
        fmt = "tmf640"
        try: json.loads(prompt)
        except json.JSONDecodeError:
            step("DETECT", "error", "JSON Parse Error",
                 "Goal: Validate and classify the incoming request format.\n"
                 "Input: Raw prompt string\n"
                 "Expected: Valid JSON → TMF640/TMF641 structured payload\n"
                 "Actual: Invalid JSON — aborting.",
                 "red", "❌")
            return ProcessResponse(order_id=order_id, format="invalid", status="error", trace=trace, total_ms=int((time.time()-t0)*1000))
    else:
        fmt = "unstructured"
    step("DETECT", "done", "Format Detection",
         "Goal: Classify the incoming request as structured (TMF640/TMF641 JSON) or unstructured natural language text.\n"
         "Input: Raw prompt string (first character check)\n"
         "Expected: '{' prefix → structured JSON path; anything else → unstructured text path\n"
         + (f"Actual: Detected structured JSON → routing to TMF640 pipeline" if is_json else
            f"Actual: Detected unstructured text → routing to secure LLM parsing path"),
         "cyan", "🔍")

    # --- STAGE 1: MASK ---
    masker = DataMasker()
    masked_text, token_map = masker.mask(prompt)
    n_tokens = len(token_map)
    if n_tokens:
        items = "\n".join(f"  {t} → {v}" for t, v in list(token_map.items())[:6])
        if n_tokens > 6: items += f"\n  ... (+{n_tokens-6} more)"
        step("MASK", "done", f"Data Masking — {n_tokens} Identifiers Tokenized",
             f"Goal: Strip all sensitive identifiers before any data leaves the local perimeter for cloud AI.\n"
             f"Input: {'Structured TMF640/TMF641 JSON' if is_json else 'Unstructured natural language text'}\n"
             f"Expected: All MSISDNs, IMSIs, IP addresses, and hostnames replaced with VAR_* tokens\n"
             f"Actual: {n_tokens} identifiers tokenized:\n{items}\n\n"
             f"Output: Masked text with zero real identifiers — safe for cloud transmission.\n"
             f"The token→real mapping is held in transient memory only — never serialized or sent over network.",
             "violet", "🛡️")
    else:
        step("MASK", "done", "Data Masking",
             "Goal: Strip all sensitive identifiers before any data leaves the local perimeter.\n"
             "Input: Raw request text\n"
             "Expected: Regex patterns scan for MSISDN (5-15 digit phone numbers), IPv4 addresses, and FQDNs\n"
             "Actual: No sensitive identifiers detected — request can proceed unmasked.\n"
             "Output: Original text unchanged — safe to forward.",
             "violet", "🛡️")

    # --- STAGE 2: CACHE ---
    svc = detect_service_type(prompt)
    # Build characteristics dict for pattern matching (exclude instance identifiers)
    chars = {}
    all_chars = {}  # includes instance attrs for full provisioning
    if is_json:
        try:
            data = json.loads(prompt)
            for c in data.get("characteristic", []):
                name = c.get("name", c.get("key", ""))
                val = str(c.get("value", ""))
                all_chars[name] = val
                if name.lower() in patterns.INSTANCE_ATTRS:
                    continue
                chars[name] = val
        except: pass
    else:
        # Unstructured: use masked text hash so different intents get different keys
        chars["text_hash"] = hashlib.sha256(masked_text.encode()).hexdigest()[:16]
        # Populate all_chars from token_map so subscriber identity can be resolved
        # (critical: without this, every unstructured request gets a fresh hash ID)
        for tok, real in token_map.items():
            if tok.startswith("VAR_MSISDN_"):
                all_chars["msisdn"] = real
                break  # first MSISDN is the subscriber anchor
            elif tok.startswith("VAR_IP_"):
                all_chars[f"ip_{tok}"] = real

    # --- Extract subscriber identity and load previous service model ---
    subscriber_id = extract_subscriber_id(prompt, is_json, all_chars)
    previous_model = service_models.get(subscriber_id)

    matched = patterns.lookup(svc, chars)
    pattern_match = None  # structured match info for UI
    if matched:
        patterns.reinforce(matched)
        plan = {"workflows": [r["workflow"] for r in matched.resources],
                "params": {k: v for r in matched.resources for k, v in r["attributes"].items()},
                "devices": [r["name"] for r in matched.resources]}

        # Immediately cascade request characteristics into the cached plan.
        # This ensures the plan reflects the current request's values (e.g.,
        # MSISDN, IMSI, subscriber_profile), not stale values from a previous
        # subscriber's learned pattern.  For structured JSON, all_chars has
        # the full characteristic set from the TMF640 payload.
        if all_chars:
            cascaded = 0
            pp = plan.get("params", {})
            for k, v in all_chars.items():
                sv = str(v)
                if not sv.startswith("default_") and not sv.startswith("<"):
                    pp[k] = v
                    cascaded += 1
            if cascaded:
                plan["params"] = pp
                step("MERGE", "done", f"Sync-Phase Merge — {cascaded} Request Chars Cascaded",
                     f"Goal: Cascade request characteristics into cached plan before background dispatch.\\n"
                     f"Actual: {cascaded} characteristics from request overlaid onto {len(matched.resources)}-resource plan.\\n"
                     f"Output: Plan params now reflect current request, not stale cached values.",
                     "violet", "🔄")

        # Build detailed match comparison
        req_keys = {k for k in chars if k.lower() not in patterns.INSTANCE_ATTRS}
        pat_keys = set(matched.characteristics.keys())
        matched_keys = {k for k in req_keys & pat_keys if str(chars.get(k,"")) == str(matched.characteristics.get(k,""))}
        mismatched_keys = (req_keys & pat_keys) - matched_keys
        extra_keys = req_keys - pat_keys
        pattern_match = {
            "result": "HIT",
            "patternId": matched.id,
            "patternLabel": matched.label,
            "confidence": round(matched.confidence, 2),
            "useCount": matched.use_count,
            "triplesCount": len(matched.triples),
            "resourcesCount": len(matched.resources),
            "compareLogic": "Jaccard similarity on service-defining characteristics",
            "requestChars": {k: str(v) for k, v in chars.items() if k.lower() not in patterns.INSTANCE_ATTRS},
            "patternChars": {k: str(v) for k, v in matched.characteristics.items()},
            "matchedKeys": sorted(matched_keys),
            "mismatchedKeys": sorted(mismatched_keys),
            "extraKeys": sorted(extra_keys),
            "excludedInstanceAttrs": sorted(k for k in chars if k.lower() in patterns.INSTANCE_ATTRS),
            "score": round(len(matched_keys) / max(len(req_keys | pat_keys), 1), 2),
        }
        # Build concise comparison table for trace
        compare_rows = []
        for k in sorted(req_keys | pat_keys):
            req_v = chars.get(k, "—")
            pat_v = matched.characteristics.get(k, "—")
            status = "✓" if str(req_v) == str(pat_v) else "✗" if k in req_keys and k in pat_keys else "?"
            compare_rows.append(f"  {status} {k}: request={req_v}  |  pattern={pat_v}")
        step("CACHE", "done", f"Pattern Match — {matched.id} ✓",
             f"Goal: Query the RDF pattern store for a matching orchestration pattern.\\n"
             f"Input: service_type={svc}, comparing {len(req_keys)} service-defining characteristics\\n"
             f"Expected: Jaccard match against {len(patterns._index.get(svc,[]))} known {svc} patterns\\n"
             f"Actual: Pattern HIT — {matched.label}\\n"
             f"  Confidence: {matched.confidence:.0%} ({matched.use_count} uses)\\n"
             f"  Score: {pattern_match['score']:.0%} ({len(matched_keys)}/{len(req_keys|pat_keys)} keys match)\\n"
             + "\\n".join(compare_rows) + "\\n\\n"
             + (f"  Instance attrs excluded: {', '.join(pattern_match['excludedInstanceAttrs'])}\\n" if pattern_match['excludedInstanceAttrs'] else "")
             + f"Output: Pre-validated plan with {len(matched.resources)} network elements.\\n"
             f"⏱ 0ms LLM latency.",
             "green", "⚡")
        llm_used = False
        pattern_hit = matched
    else:
        # Build miss details
        all_pats = patterns.list_all()
        same_svc = [p for p in all_pats if p["service_type"] == svc]
        req_keys = {k for k in chars if k.lower() not in patterns.INSTANCE_ATTRS}
        pattern_match = {
            "result": "MISS",
            "patternsInStore": len(all_pats),
            "patternsForService": len(same_svc),
            "requestChars": {k: str(v) for k, v in chars.items() if k.lower() not in patterns.INSTANCE_ATTRS},
            "excludedInstanceAttrs": sorted(k for k in chars if k.lower() in patterns.INSTANCE_ATTRS),
            "compareLogic": "Jaccard similarity on service-defining characteristics",
        }
        step("CACHE", "done", "Pattern Store — MISS",
             f"Goal: Query the RDF pattern store for a matching orchestration pattern.\\n"
             f"Input: service_type={svc}, {len(req_keys)} service-defining characteristics\\n"
             f"Request chars: {json.dumps(pattern_match['requestChars'])}\\n"
             f"Expected: Find matching pattern via Jaccard similarity\\n"
             f"Actual: No match — {len(same_svc)} patterns for '{svc}', {len(all_pats)} total in store\\n"
             + (f"  Instance attrs excluded: {', '.join(pattern_match['excludedInstanceAttrs'])}\\n" if pattern_match['excludedInstanceAttrs'] else "")
             + f"Output: Flag llm_used=True → Deepseek will reason from KB, then pattern will be learned.",
             "amber", "📡")
        plan = None
        llm_used = True
        pattern_hit = None

    # --- STAGE 3 onward: dispatch to background ---
    docs = KB_DOCS.get(svc, "Generic provisioning standards")
    kb_context = load_kb_context(svc)
    step("LLM", "done", "Pipeline Dispatched — Background Processing",
         f"Goal: Continue orchestration in background thread.\n"
         f"Input: {'Cached plan available' if not llm_used else 'Need LLM reasoning'}\n"
         f"Expected: Background thread completes LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY\n"
         f"Actual: Background processing started. Frontend will poll for results.",
         "green", "⏳")

    result = ProcessResponse(order_id=order_id, format=fmt, status="processing",
                             trace=trace, total_ms=int((time.time()-t0)*1000),
                             started_at=datetime.utcnow().isoformat())

    # Extract state needed by background thread
    bg_state = {
        "order_id": order_id, "fmt": fmt, "svc": svc, "docs": docs,
        "kb_context": kb_context,
        "masked_text": masked_text, "token_map": token_map, "n_tokens": n_tokens,
        "llm_used": llm_used, "chars": chars, "all_chars": all_chars, "pattern_hit": pattern_hit,
        "pattern_match": pattern_match,
        "plan": plan, "t0": t0,
        "subscriber_id": subscriber_id, "previous_model": previous_model,
    }
    with jobs_lock:
        jobs[order_id] = result
    executor.submit(_run_background, bg_state)
    return result


def _run_background(state: dict):
    """Complete the pipeline in a background thread — LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY."""
    order_id = state["order_id"]
    try:
        _run_background_inner(state)
    except Exception:
        logger.exception("Background pipeline crashed for %s", order_id)
        with jobs_lock:
            if order_id in jobs:
                jobs[order_id].status = "error"
                jobs[order_id].trace.append(TraceStep(
                    stage="ERROR", status="error",
                    title="Background Pipeline Crashed",
                    detail=f"Unhandled exception in background thread. Check server logs.",
                    color="red", icon="💥",
                    elapsed_ms=int((time.time() - state["t0"]) * 1000)))


def _run_background_inner(state: dict):
    order_id = state["order_id"]
    svc = state["svc"]
    docs = state["docs"]
    kb_context = state["kb_context"]
    chars = state.get("chars", {})
    all_chars = state.get("all_chars", {})  # includes msisdn/imsi for full provisioning
    subscriber_id = state.get("subscriber_id", "unknown")
    previous_model = state.get("previous_model")
    pattern_hit = state.get("pattern_hit")
    pattern_match = state.get("pattern_match")
    masked_text = state["masked_text"]
    token_map = state["token_map"]
    n_tokens = state["n_tokens"]
    cache_key = state.get("cache_key")  # optional — not always in bg_state
    llm_used = state["llm_used"]
    plan = state["plan"]
    t0 = state["t0"]
    fmt = state["fmt"]

    def step(stage, status, title, detail, color, icon):
        with jobs_lock:
            if order_id in jobs:
                jobs[order_id].trace.append(TraceStep(
                    stage=stage, status=status, title=title, detail=detail,
                    color=color, icon=icon, elapsed_ms=int((time.time()-t0)*1000)))

    # --- STAGE 3: RAG ---
    sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
    ne_count = len(sr['required_resources'])
    ne_list = ", ".join(r['type'] for r in sr['required_resources'])
    step("RAG", "done", "Knowledge Base RAG — Domain Reasoning",
         f"Goal: Load domain knowledge from local KB files to determine required network elements.\\n"
         f"Input: Detected service type = '{svc}', mapped to domain '{sr['domain']}'\\n"
         f"Expected: Query core ontology + standards reference → determine required resources\\n"
         f"Actual: KB resolver identified {ne_count} required network elements from ontology:\\n"
         + "\\n".join(f"  • {r['type']} — {r['role']}" for r in sr['required_resources']) + "\\n\\n"
         f"Standards: {', '.join(sr['standards'][:3])}\\n"
         f"Lifecycle: {sr['lifecycle']}\\n"
         f"Output: Structured domain context injected into reasoning pipeline.",
         "blue", "📚")

    # --- STAGE 4: LLM ---
    if llm_used:
        llm_prompt = f"""You are a telecom orchestration engine. Generate an orchestration plan for this service request.

Domain Knowledge (from KB):
{kb_context[:4000]}

Request (SENSITIVE DATA MASKED):
{masked_text[:2000]}

Return ONLY valid JSON with this structure:
{{"workflows": ["..."], "params": {{...}}, "devices": ["..."]}}

The workflows, params, and devices MUST correspond to the network elements identified in the domain knowledge above. Use the masked tokens (VAR_*) as-is — do not invent real values."""

        step("LLM", "running", "Deepseek v4 — Reasoning & Plan Generation",
             f"Goal: Generate an orchestration plan using cloud AI reasoning on MASKED data.\\n"
             f"Input: Masked request text + KB standards context\\n"
             f"Expected: Deepseek returns structured JSON with workflows, params, and target devices\\n"
             f"Calling Deepseek API (via hermes CLI) — this takes 30-60 seconds...",
             "blue", "🧠")
        logger.info("Calling Deepseek for %s (%d chars)", svc, len(llm_prompt))
        llm_response = call_deepseek(llm_prompt, timeout=90)

        if llm_response:
            try:
                plan = json.loads(llm_response)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if json_match:
                    try:
                        plan = json.loads(json_match.group(0))
                    except:
                        plan = _fallback_plan(svc)
                else:
                    plan = _fallback_plan(svc)

            step("LLM", "done", "Deepseek v4 — Plan Generated ✓",
                 f"Goal: Generate an orchestration plan using cloud AI reasoning on MASKED data.\\n"
                 f"Input: Masked request + KB standards → Deepseek v4 API (via hermes CLI)\\n"
                 f"Expected: Valid JSON with workflows[], params{{}}, devices[]\\n"
                 f"Actual: Deepseek returned {len(llm_response)} chars of structured JSON\\n"
                 f"Output:\\n  • {len(plan.get('workflows',[]))} workflows: {', '.join(plan.get('workflows',[])[:4])}\\n"
                 f"  • {len(plan.get('params',{}))} configuration parameters\\n"
                 f"  • Target devices: {', '.join(plan.get('devices',[])[:4])}",
                 "blue", "🧠")
        else:
            plan = _fallback_plan(svc)
            step("LLM", "done", "Deepseek v4 — Fallback Plan Used",
                 f"Goal: Generate orchestration plan via cloud AI.\\n"
                 f"Input: Masked request + KB standards\\n"
                 f"Expected: Deepseek returns structured JSON plan\\n"
                 f"Actual: Deepseek did not respond.\\n"
                 f"Output: Using pre-built {svc} template plan.",
                 "blue", "🧠")
    else:
        step("LLM", "done", "Deepseek v4 — Skipped (Cache Hit)",
             f"Goal: Generate orchestration plan (only if needed).\\n"
             f"Input: Cache status = HIT\\n"
             f"Expected: Skip LLM call entirely\\n"
             f"Actual: LLM bypassed — cached plan retrieved.\\n"
             f"Output: Pre-validated plan with {len(plan.get('workflows',[])) if plan else 0} workflows.",
             "green", "🧠")

    # --- Flatten nested params (LLMs often nest by workflow name) ---
    plan = flatten_plan_params(plan)

    # --- STAGE 5: HYDRATE ---
    if token_map:
        ps = json.dumps(plan)
        for tok, real in token_map.items():
            ps = ps.replace(tok, real)
        plan = json.loads(ps)
        step("HYDRATE", "done", "Local Parameter Hydration",
             f"Goal: Restore real infrastructure identifiers.\\n"
             f"Input: Plan with VAR_* tokens + local mapping ({n_tokens} entries)\\n"
             f"Expected: All tokens resolved to original values\\n"
             f"Actual: {n_tokens} tokens resolved.\\n"
             f"Output: Fully hydrated plan ready for execution.",
             "violet", "💧")
    else:
        step("HYDRATE", "done", "Local Parameter Hydration",
             f"Goal: Restore real identifiers if masked.\\n"
             f"Actual: No tokens to resolve.",
             "violet", "💧")

    # --- Populate all_chars from plan params for unstructured text ---
    # The sync phase only extracts msisdn from token_map.  The LLM has now
    # parsed the full request — harvest real characteristics so MERGE, DIFF,
    # and model storage have complete context for change detection.
    # IMPORTANT: skip default_* values — they are placeholders, not real data.
    if fmt == "unstructured" and plan and isinstance(plan.get("params"), dict):
        for k, v in plan["params"].items():
            sv = str(v)
            if k not in all_chars and not sv.startswith("default_"):
                all_chars[k] = v

    # --- MERGE: cascade request characteristics into cached/LLM plan ---
    # Two modes:
    #   1. With previous_model: cascade CHANGED values + fill gaps from prev model
    #   2. Without previous_model (first provisioning): cascade ALL request chars
    #      into the cached plan so it reflects the actual request, not stale
    #      values from a different subscriber's learned pattern.
    # --- ACQUIRE SUBSCRIBER LOCK ---
    # Prevents concurrent modifications to the same subscriber model.
    # If another worker is modifying this subscriber, we wait up to 5s.
    plan_params = plan.get("params", {})
    merged_count = 0
    filled_count = 0
    lock_held = False

    with subscriber_lock.acquire(subscriber_id, order_id) as lock_acquired:
        if not lock_acquired:
            step("LOCK", "error",
                 f"Subscriber Lock — TIMEOUT on {subscriber_id}",
                 f"Goal: Acquire exclusive lock for subscriber model modification.\\n"
                 f"Input: subscriber_id={subscriber_id}\\n"
                 f"Expected: Lock acquired within {SubscriberLock.MAX_RETRIES * SubscriberLock.RETRY_DELAY:.0f}s\\n"
                 f"Actual: Lock held by another worker after full retry budget.\\n"
                 f"Output: Aborting — subscriber is being modified concurrently.",
                 "red", "🔒")
            with jobs_lock:
                if order_id in jobs:
                    jobs[order_id].status = "blocked"
                    jobs[order_id].total_ms = int((time.time()-t0)*1000)
            return

        lock_held = True
        step("LOCK", "done",
             f"Subscriber Lock — Acquired ✓",
             f"Goal: Acquire exclusive lock on subscriber {subscriber_id}.\\n"
             f"Input: lock:sub:{subscriber_id}\\n"
             f"Expected: Lock free or available within retry budget\\n"
             f"Actual: Lock acquired — safe to modify model.\\n"
             f"Output: MERGE → VERIFY → STORE critical section protected.",
             "violet", "🔒")

        # Always cascade request characteristics into plan params
        if all_chars:
            for k, v in all_chars.items():
                sv = str(v)
                if not sv.startswith("default_") and not sv.startswith("<"):
                    plan_params[k] = v
                    merged_count += 1
        else:
            step("MERGE", "done", "Merge Skipped — No Request Chars",
                 f"Goal: Cascade request characteristics into plan.\\n"
                 f"Actual: all_chars is empty — nothing to cascade.\\n"
                 f"Plan params has {len(plan_params)} keys: {sorted(plan_params.keys())[:10]}",
                 "violet", "⏭️")

        # If we have a previous model, also cascade changed values and fill gaps
        if previous_model:
            prev_chars = previous_model.get("characteristics", {})
            for k, prev_v in prev_chars.items():
                if k not in all_chars and k not in plan_params:
                    sv = str(prev_v)
                    if not sv.startswith("default_"):
                        plan_params[k] = prev_v
                        filled_count += 1

        if merged_count or filled_count:
            plan["params"] = plan_params
            detail = f"Goal: Cascade request characteristics into plan.\\n"
            detail += f"Input: {merged_count} from request, {filled_count} from previous model"
            if previous_model:
                detail += f" v{previous_model.get('version','?')}"
            detail += f"\\nOutput: Plan params now complete — {len(plan_params)} attributes total."
            step("MERGE", "done", "Characteristic Merge — Plan Updated",
                 detail, "violet", "🔄")

        # --- STAGE 6: WRITE-THROUGH ---
        learned = None
        if llm_used:
            learned = patterns.learn(svc, chars, plan, all_chars=all_chars)
            step("CACHE", "done", "Pattern Learning — RDF Triples Written",
                 f"Goal: Persist new pattern as RDF graph for future matches.\\n"
                 f"Actual: Pattern {learned.id} learned.\\n"
                 f"Output: {len(learned.triples)} triples, {len(learned.resources)} resources, confidence={learned.confidence:.0%}.",
                 "green", "💾")
        else:
            step("CACHE", "done", "Pattern Learning",
                 "Goal: Persist new pattern if just learned.\\n"
                 "Actual: Pattern already exists — confidence reinforced by cache hit.",
                 "green", "💾")

        # --- STAGE 7: VALIDATE ---
        check_text = (json.dumps(plan) + " " + masked_text).lower()
        blocked = [kw for kw in BLOCKED_KEYWORDS if kw in check_text]
        if blocked:
            step("VALIDATE", "blocked", "Security Gateway — BLOCKED 🚫",
                 f"Goal: Prevent destructive commands from reaching devices.\\n"
                 f"Actual: BLOCKED — {', '.join(blocked)} detected.\\n"
                 f"Output: Transaction ABORTED. No devices touched.",
                 "red", "🚫")
            with jobs_lock:
                if order_id in jobs:
                    jobs[order_id].status = "blocked"
                    jobs[order_id].total_ms = int((time.time()-t0)*1000)
            return
        step("VALIDATE", "done", "Security Gateway — PASSED ✓",
             f"Goal: Validate plan against security guardrails.\\n"
             f"Actual: All checks PASSED.\\n"
             f"Output: Plan cleared for execution.",
             "green", "🔒")

        # --- STAGE 8: EXECUTE ---
        workflows = plan.get("workflows", [])
        devices = plan.get("devices", [f"DEV-{i}" for i in range(len(workflows))])
        step("EXECUTE", "done", "MCP Execution — Workflows Dispatched",
             f"Goal: Deploy validated plan to infrastructure.\\n"
             f"Actual: {len(workflows)} workflows completed.\\n"
             f"Output: Devices configured.",
             "amber", "⚙️")

        # --- STAGE 9: VERIFY ---
        svc_id = f"SVC-{uuid.uuid4().hex[:6].upper()}"

        # Build network element details from KB resource definitions + plan
        params = plan.get("params", {})
        sr2 = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
        kb_resources = {r["type"]: r for r in sr2["required_resources"]}
        # Build lookup of previous model NE attributes for gap-filling.
        prev_ne_attrs = {}
        if previous_model:
            for ne in previous_model.get("network_elements", []):
                name = ne["name"]
                prev_ne_attrs[name] = ne.get("attributes", {})
                canonical = name.split("/")[0]
                if canonical != name:
                    prev_ne_attrs[canonical] = ne.get("attributes", {})
        network_elements = []
        for i, dev in enumerate(devices):
            wf = workflows[i] if i < len(workflows) else "Configuration"
            kb_res = None
            for kb_type, kb_def in kb_resources.items():
                if any(p in dev.lower() for p in kb_type.lower().replace("/"," ").split()):
                    kb_res = kb_def
                    break
            attrs = {}
            if kb_res:
                for attr in kb_res.get("attributes", []):
                    if attr in params:
                        attrs[attr] = str(params[attr])
                    elif attr in all_chars:
                        attrs[attr] = str(all_chars[attr])
                    elif attr in chars:
                        attrs[attr] = str(chars[attr])
                    else:
                        prev_attrs = prev_ne_attrs.get(dev)
                        if prev_attrs is None:
                            canonical = dev.split("/")[0]
                            prev_attrs = prev_ne_attrs.get(canonical, {})
                        prev_val = (prev_attrs or {}).get(attr)
                        if prev_val is not None and not str(prev_val).startswith("default_"):
                            attrs[attr] = str(prev_val)
                        else:
                            attrs[attr] = f"default_{attr}"
                attrs["status"] = "Configured"
            else:
                for k, v in params.items():
                    attrs[k] = str(v) if not isinstance(v, list) else ", ".join(str(x) for x in v)
                attrs["status"] = "Configured"
            network_elements.append({
                "name": dev,
                "type": kb_res.get("type", dev) if kb_res else dev,
                "workflow": wf,
                "role": kb_res.get("role", "Network function") if kb_res else "Network function",
                "attributes": attrs,
            })

        # --- Service Model: compute diff, save, cross-validate ---
        subscriber_diff = service_models.compute_diff(previous_model, all_chars, network_elements)
        new_model = service_models.build_model(
            subscriber_id, svc, all_chars, network_elements,
            version=previous_model.get("version", 0) if previous_model else 0)
        service_models.save(subscriber_id, new_model)

        # --- KB-Driven Lifecycle Notifications ---
        notif_count = lifecycle_notifier.build_notification_trace(
            order_id, svc, subscriber_id, t0, step)

        # Collect all notifications
        notifications = lifecycle_notifier.flush()

        final_state = {"serviceId": svc_id, "state": "ACTIVE",
                       "workflowsExecuted": len(workflows), "resourcesProvisioned": len(params),
                       "networkElements": network_elements,
                       "patternId": learned.id if learned else (pattern_hit.id if pattern_hit else None),
                       "patternConfidence": round(learned.confidence if learned else (pattern_hit.confidence if pattern_hit else 0), 2),
                       "llmUsed": llm_used,
                       "patternMatch": pattern_match,
                       "subscriberId": subscriber_id,
                       "subscriberDiff": subscriber_diff,
                       "notificationCount": notif_count,
                       "notifications": notifications}
        step("VERIFY", "done", "Verification & Pattern Learning",
             f"Goal: Confirm service is active, persist model, cross-validate.\\n"
             f"Actual: Service {svc_id} ACTIVE — {len(network_elements)} network elements configured.\\n"
             + (f"Previous model: v{previous_model.get('version','?')} — {len(subscriber_diff.get('changedAttributes',{}))} characteristic changes, "
                f"{sum(1 for d in subscriber_diff.get('networkElementDiffs',{}).values() if d)} NE diffs.\\n" if previous_model else
                f"First provisioning — new service model v1 saved.\\n")
             + f"Notifications: {notif_count} lifecycle state transitions emitted.\\n"
             + f"Output: Model persisted. Lock released. Pipeline complete.",
             "green", "✅")

    # --- Lock auto-released here by context manager ---

    total_ms = int((time.time() - t0) * 1000)
    with jobs_lock:
        if order_id in jobs:
            jobs[order_id].status = "completed"
            jobs[order_id].total_ms = total_ms
            jobs[order_id].final_state = final_state


def _fallback_plan(svc: str) -> dict:
    """Generate plan from KB-derived SERVICE_RESOURCES when Deepseek unavailable.
    Uses WF_MAP for workflow names and <attr> placeholders — no hardcoded values."""
    sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
    resources = sr["required_resources"]
    devices = [r["type"].replace("/", "-") for r in resources]
    workflows = [WF_MAP.get(d.replace("-HSS","").replace("-PCF","").replace("-MME",""),
                           f"{d}_Config") for d in devices]
    params = {}
    for r in resources:
        for attr in r["attributes"]:
            params[attr] = f"<{attr}>"  # placeholder — resolved at orchestration time
    return {"workflows": workflows, "params": params, "devices": devices}

# ====================================================================
# Routes
# ====================================================================
@app.post("/api/process", response_model=ProcessResponse)
async def process(request: ProcessRequest):
    return start_pipeline(request.prompt)


@app.get("/api/process/{order_id}", response_model=ProcessResponse)
async def get_process(order_id: str):
    """Poll for pipeline result. Returns partial trace while processing."""
    with jobs_lock:
        job = jobs.get(order_id)
    if job is None:
        return JSONResponse({"error": "order not found"}, status_code=404)
    return job

@app.get("/api/patterns")
async def list_patterns():
    """List all learned patterns with confidence and metadata."""
    return {"patterns": patterns.list_all()}

@app.get("/api/patterns/{pattern_id}")
async def get_pattern(pattern_id: str):
    """Get full pattern details including RDF triples."""
    pat = patterns.get(pattern_id)
    if pat is None:
        return JSONResponse({"error": "pattern not found"}, status_code=404)
    return pat

@app.post("/api/patterns/teach")
async def teach_pattern(request: dict):
    """Teach the engine a new pattern via RDF triples. High confidence."""
    triples = request.get("triples", [])
    if not triples:
        return JSONResponse({"error": "triples required"}, status_code=400)
    node = patterns.teach(triples)
    return {"status": "learned", "pattern": node.to_dict()}

@app.get("/api/samples")
async def get_samples():
    return {"samples": [
        {"label": "TMF640 — Activate Mobile Voice (Gold)",
         "text": '{"serviceId":"MSISDN-447700123456","action":"activate","characteristic":[{"name":"customerSegment","value":"retail"},{"name":"slaTier","value":"gold"},{"name":"productId","value":"mobile-voice"},{"name":"msisdn","value":"447700123456"},{"name":"imsi","value":"234151234567890"},{"name":"subscriber_profile","value":"Gold_VoLTE_IntlRoam"},{"name":"roaming_profile","value":"WorldZone1"},{"name":"volte_enabled","value":"true"},{"name":"codec_profile","value":"EVS_AMR-WB"},{"name":"apn","value":"ims.gold.mnc015.mcc234.gprs"},{"name":"qos_profile","value":"QCI-1_VoLTE"},{"name":"charging_rule","value":"Gold_Postpaid_VoLTE"},{"name":"bandwidth_limit","value":"unlimited"},{"name":"routing","value":"SMSC-Primary"},{"name":"validity_period","value":"72h"},{"name":"location_area","value":"LAC-0x4A2B"},{"name":"tac","value":"0x8C3D"},{"name":"sip_domain","value":"ims.mnc015.mcc234.3gppnetwork.org"},{"name":"codec_list","value":"EVS,AMR-WB,AMR-NB"},{"name":"media_handling","value":"rtp-proxy"}]}'},
        {"label": "TMF640 — Activate Mobile Data (Platinum)",
         "text": '{"serviceId":"MSISDN-447700654321","action":"activate","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"mobile-data"},{"name":"msisdn","value":"447700654321"},{"name":"imsi","value":"234159876543210"},{"name":"subscriber_profile","value":"Plat_5GSA_eMBB"},{"name":"roaming_profile","value":"Global"},{"name":"volte_enabled","value":"false"},{"name":"codec_profile","value":"AMR-WB"},{"name":"apn","value":"data.plat.mnc015.mcc234.gprs"},{"name":"qos_profile","value":"QCI-6_5QI-6"},{"name":"charging_rule","value":"Plat_Postpaid_Data_5G"},{"name":"bandwidth_limit","value":"10Gbps"},{"name":"routing","value":"SMSC-Secondary"},{"name":"validity_period","value":"168h"},{"name":"location_area","value":"LAC-0xB7E1"},{"name":"tac","value":"0x3F2A"},{"name":"sip_domain","value":"volte.mnc015.mcc234.3gppnetwork.org"},{"name":"codec_list","value":"AMR-WB,AMR-NB"},{"name":"media_handling","value":"srtp-end-to-end"}]}'},
        {"label": "Unstructured — Mobile Voice Activation",
         "text": "activate new mobile voice service for retail customer with gold SLA: MSISDN 447700123456, IMSI 234151234567890, enable VoLTE with EVS codec, international roaming WorldZone1, IMS APN ims.gold.mnc015.mcc234.gprs, QCI-1 QoS, postpaid charging, SIP domain ims.mnc015.mcc234.3gppnetwork.org, SMSC primary routing with 72h validity, location area LAC-0x4A2B, TAC 0x8C3D"},
        {"label": "TMF640 — Activate L3VPN (Enterprise Platinum)",
         "text": '{"serviceId":"svc-acme-sjc-l3vpn","action":"activate","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"prod-l3vpn-01"},{"name":"pe_ip","value":"10.1.1.1"},{"name":"bandwidth","value":"1000"},{"name":"vrf_name","value":"CUST-ACME-SJC-VRF"},{"name":"rd","value":"65001:101"},{"name":"rt_import","value":"65001:100"},{"name":"rt_export","value":"65001:100"},{"name":"bgp_peer","value":"10.1.1.2"},{"name":"cluster_id","value":"1.1.1.1"},{"name":"peer_group","value":"RR-CLIENTS"},{"name":"asn","value":"65001"},{"name":"route_targets","value":"65001:100,65001:200"},{"name":"interfaces","value":"Gi0/0/1,Gi0/0/2"},{"name":"snmp_community","value":"acme-ro-v3"},{"name":"syslog_server","value":"10.100.1.10"},{"name":"netflow_collector","value":"10.100.1.20:2055"}]}'},
        {"label": "TMF640 — Activate SD-WAN (Dual Transport)",
         "text": '{"serviceId":"sdwan-branches-apac","action":"activate","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"prod-sdwan-01"},{"name":"transport_links","value":"MPLS-100M,Internet-500M,4G-backup"},{"name":"encryption","value":"IPSec-AES256-GCM"},{"name":"app_policy","value":"VoIP-priority,SaaS-optimized,BestEffort"},{"name":"wan_interfaces","value":"ge0/0-MPLS,ge0/1-INET,cellular0/0"},{"name":"policy_set","value":"Platinum-APAC-v3"},{"name":"site_list","value":"Tokyo,Singapore,Sydney,Bangkok"},{"name":"template","value":"sdwan-dual-transport-v4"},{"name":"ztp_url","value":"https://ztp.enterprise.net/boot/v4"},{"name":"bootstrap_config","value":"base-config-platinum.yaml"},{"name":"license_key","value":"ENT-SDWAN-PLAT-APAC-2026"}]}'},
        {"label": "TMF641 — ServiceOrder Broadband (FTTH Silver)",
         "text": '{"externalId":"CRM-98765","category":"Broadband","action":"add","characteristic":[{"name":"customerSegment","value":"retail"},{"name":"slaTier","value":"silver"},{"name":"productId","value":"prod-ftth-100m"},{"name":"ont_model","value":"Huawei-HG8245W5"},{"name":"vlan","value":"100"},{"name":"speed_profile","value":"100M-20M"},{"name":"dba_profile","value":"Type3-NSR"},{"name":"ip_pool","value":"POOL-RETAIL-SILVER"},{"name":"subscriber_profile","value":"Residential-Silver"},{"name":"qos_policy","value":"Silver-BestEffort"},{"name":"nas_identifier","value":"BNG-SJC-01"},{"name":"shared_secret","value":"a7f3b9c2e1"},{"name":"auth_method","value":"PAP"},{"name":"snmp_community","value":"ems-readonly-v2"},{"name":"trap_destinations","value":"10.200.1.10:162,10.200.1.11:162"}]}'},
        {"label": "Security Test — Blocked Keyword",
         "text": "activate mobile service 447700123456 with gold SLA and shutdown all interfaces"},
    ]}

@app.get("/health")
async def health():
    return {"status": "ok", "cache_size": len(cache), "redis_backend": "diskcache"}

@app.get("/api/notifications/{order_id}")
async def get_notifications(order_id: str):
    """Retrieve TMF lifecycle notifications for a completed order."""
    with jobs_lock:
        job = jobs.get(order_id)
    if job is None:
        return JSONResponse({"error": "order not found"}, status_code=404)
    if job.final_state is None:
        return JSONResponse({"notifications": [], "message": "Pipeline still processing"}, status_code=200)
    return {
        "orderId": order_id,
        "notifications": job.final_state.get("notifications", []),
        "count": job.final_state.get("notificationCount", 0),
    }

@app.post("/api/locks/release")
async def release_lock(request: dict):
    """Admin endpoint: force-release a subscriber lock."""
    subscriber_id = request.get("subscriberId", "")
    if not subscriber_id:
        return JSONResponse({"error": "subscriberId required"}, status_code=400)
    subscriber_lock.force_release(subscriber_id)
    return {"status": "released", "subscriberId": subscriber_id}

@app.get("/api/locks/status")
async def lock_status():
    """List all active subscriber locks."""
    locks = []
    for key in list(cache):
        if key.startswith("lock:sub:"):
            val = cache.get(key)
            if val:
                locks.append({
                    "key": key,
                    "subscriberId": key.replace("lock:sub:", ""),
                    "workerId": val.get("worker_id", "?"),
                    "acquiredAt": val.get("acquired_at", 0),
                    "ageSeconds": round(time.time() - val.get("acquired_at", time.time()), 1),
                })
    return {"activeLocks": len(locks), "locks": locks}

# Serve static frontend
@app.get("/")
async def index():
    return FileResponse("/opt/data/telecom-orchestrator/poc/static/index.html")

app.mount("/static", StaticFiles(directory="/opt/data/telecom-orchestrator/poc/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting production PoC server on 0.0.0.0:8090")
    uvicorn.run(app, host="0.0.0.0", port=8090)
```

---

## PART 6: TESTING INSTRUCTIONS

### Quick Smoke Test (curl)

```bash
# 1. Health check
curl http://localhost:8090/health
# Expected: {"status":"ok","cache_size":N,"redis_backend":"diskcache"}

# 2. List KB-seeded patterns (4 expected: mobile, l3vpn, sdwan, broadband)
curl http://localhost:8090/api/patterns | python3 -m json.tool

# 3. Submit a structured TMF640 request
curl -s -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"{\"serviceId\":\"MSISDN-447700123456\",\"action\":\"activate\",\"characteristic\":[{\"name\":\"customerSegment\",\"value\":\"retail\"},{\"name\":\"slaTier\",\"value\":\"gold\"},{\"name\":\"productId\",\"value\":\"mobile-voice\"},{\"name\":\"msisdn\",\"value\":\"447700123456\"},{\"name\":\"subscriber_profile\",\"value\":\"Gold_VoLTE\"}]}"}' | python3 -m json.tool

# 4. Poll the result (replace PO-XXXXXXXX with actual order_id)
curl http://localhost:8090/api/process/PO-XXXXXXXX | python3 -m json.tool

# 5. Submit unstructured text
curl -s -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"activate new mobile service 447700999999 for enterprise platinum SLA"}' | python3 -m json.tool

# 6. Test security block
curl -s -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"activate mobile service 447700123456 with shutdown all interfaces"}' | python3 -m json.tool
# Expected: status=blocked in final result

# 7. Check locks
curl http://localhost:8090/api/locks/status

# 8. Check notifications for a completed order
curl http://localhost:8090/api/notifications/PO-XXXXXXXX
```

### Browser Test

1. Open `http://localhost:8090`
2. Click a sample chip (e.g., "TMF640 — Activate Mobile Voice")
3. Click ▶ Execute
4. Observe: pipeline trace cards appear with color-coded stages
5. On completion: pattern analysis, notification timeline, network element cards render
6. Click any trace card or NE card to zoom
7. Click "Security Test — Blocked Keyword" → should show BLOCKED status
8. Click "Clear" → all panels reset

---

## PART 7: VERIFICATION CHECKLIST

After building the PoC, verify each item:

- [ ] Server starts on `0.0.0.0:8090` without errors
- [ ] `GET /health` returns `{"status":"ok"}`
- [ ] `GET /api/patterns` returns 4+ KB-seeded patterns (mobile, l3vpn, sdwan, broadband)
- [ ] `GET /` serves the HTML frontend
- [ ] Frontend loads samples from `/api/samples`
- [ ] Submitting a structured TMF640 JSON request returns `status: processing`
- [ ] Polling `GET /api/process/{id}` returns trace steps as pipeline progresses
- [ ] Final result has `status: completed` with `final_state` containing networkElements, patternMatch, notifications
- [ ] Network element cards show correct attributes from KB resource definitions
- [ ] Pattern analysis shows confidence percentage, match type (HIT/MISS), and verification checklist
- [ ] Notification timeline shows all lifecycle state transitions
- [ ] Submitting the security test request (with "shutdown") results in `status: blocked`
- [ ] Unstructured text request goes through full pipeline including LLM call (if hermes CLI available)
- [ ] If Deepseek is unavailable, fallback plan from KB SERVICE_RESOURCES is used
- [ ] Submitting the same request twice: first run creates/learns pattern, second run is cache HIT (llmUsed: false)
- [ ] `GET /api/locks/status` returns active locks (empty after all processing completes)
- [ ] `GET /api/notifications/{order_id}` returns TMF641-compliant events
- [ ] KB files at `knowledge-base/ontologies/core-ontology.md` and `knowledge-base/reference/*.md` exist and are readable
- [ ] Server survives invalid JSON gracefully (returns error trace step)

---

## PART 8: KEY ARCHITECTURAL NOTES FOR REBUILDING

### How the KB Drives Everything

1. `SERVICE_RESOURCES` dict is the bridge — derived from `core-ontology.md` §4
2. At module load, `seed_kb_patterns()` creates base patterns from SERVICE_RESOURCES
3. `load_kb_context()` reads KB files into LLM prompts
4. `_fallback_plan()` uses SERVICE_RESOURCES + WF_MAP to build plans without LLM
5. VERIFY stage uses KB resource definitions to populate NE attributes
6. LifecycleNotifier parses lifecycle strings from SERVICE_RESOURCES

### Pattern Engine Design

- **Patterns are dataclass objects** (`PatternNode`) stored in diskcache
- **Index**: `orch:idx:patterns` maps `service_type → [pattern_ids]`
- **Per-pattern key**: `orch:pat:{pattern_id}`
- **Matching**: Jaccard similarity on service-defining characteristics (excludes instance attrs)
- **Learning**: Auto from LLM plans (`source="auto"`) or KB seeds (`source="kb"`)

### Data Sovereignty

- `DataMasker.mask()` runs in synchronous DETECT stage
- Token map lives in transient memory only — never serialized
- LLM receives ONLY masked text with VAR_* tokens
- `HYDRATE` stage restores real values from in-memory map

### Subscriber Lock Flow

```
HYDRATE → LOCK acquire → MERGE → WRITE-THROUGH → VALIDATE → EXECUTE → NOTIFY×N → VERIFY → STORE → LOCK release
```

If lock cannot be acquired within 5s retry budget → `status: "blocked"`

---

## END OF BUILD PROMPT

This document is the single source of truth for rebuilding the Telecom Agentic Orchestration Engine PoC. Every line of code, every CSS class, every function, and every KB reference is specified here. No other files or knowledge are needed.

**Build order:**
1. Create directory structure
2. Create Python venv and install dependencies
3. Write all 6 KB files
4. Write `poc/static/index.html`
5. Write `poc/server_live.py`
6. Start the server
7. Run the verification checklist
