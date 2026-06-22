# Building the Agentic Service-Resource Orchestrator on Hermes + Hostinger VPS

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hermes Agent Framework                        │
│  (Hostinger VPS — Ubuntu 24.04 LTS, 4 vCPU, 8 GB RAM)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ SKILLS   │  │ MEMORY   │  │ CRON     │  │ MCP SERVERS  │   │
│  │ Library  │  │ Store    │  │ Scheduler│  │ (ext. tools) │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│       │              │              │               │           │
│  ┌────▼──────────────▼──────────────▼───────────────▼───────┐   │
│  │              AGENT CORE LOOP (run_agent.py)              │   │
│  │  1. Query Intent → 2. Recall Patterns → 3. Research KB  │   │
│  │  4. Reason Strategy → 5. Query MCP → 6. Execute → 7. Save│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    KNOWLEDGE BASE LAYER                          │
│  /opt/data/telecom-orchestrator/knowledge-base/                 │
│                                                                 │
│  ┌───────────┐ ┌───────────┐ ┌────────────┐ ┌─────────────┐   │
│  │ ontologies│ │standards  │ │products    │ │workflows    │   │
│  │ (domain   │ │(protocols │ │(what can   │ │(how-to      │   │
│  │  model)   │ │ +specs)   │ │ be sold)   │ │ provision)  │   │
│  └─────┬─────┘ └─────┬─────┘ └──────┬─────┘ └──────┬──────┘   │
│        │              │              │               │          │
│  ┌─────▼──────────────▼──────────────▼───────────────▼──────┐   │
│  │            RESOURCE & SERVICE INVENTORY (SQLite)         │   │
│  │  Services (id, type, customer, state, CFS/RFS map)      │   │
│  │  Resources (id, type, device, config, state, service map)│   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                    INTEGRATION LAYER (MCP)                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────┐  │
│  │NetBox MCP  │ │Ansible MCP │ │Cisco NSO   │ │OSM / ONAP   │  │
│  │(inventory) │ │(config)    │ │MCP (svc    │ │MCP (NFV     │  │
│  │            │ │            │ │activation) │ │orchestra.)  │  │
│  └────────────┘ └────────────┘ └────────────┘ └─────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Hostinger VPS Setup (Day 1)

### 1.1 Provision the VPS

```
Hostinger VPS KVM-4 or higher:
- Ubuntu 24.04 LTS (or 22.04)
- 4 vCPU, 8 GB RAM, 100 GB NVMe SSD
- Static IPv4 + IPv6
- SSH key-based auth only (disable password login)
```

### 1.2 Initial System Hardening

```bash
ssh root@<vps-ip>

# Update + essentials
apt update && apt upgrade -y
apt install -y curl git python3 python3-pip python3-venv \
  build-essential tmux nginx certbot python3-certbot-nginx \
  ufw sqlite3 jq net-tools

# Firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Non-root user
adduser hermes-agent
usermod -aG sudo hermes-agent
su - hermes-agent
```

### 1.3 Install Hermes Agent

```bash
# Install Hermes
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Configure model provider (e.g. DeepSeek, Anthropic, or OpenRouter)
hermes setup model
# Pick your provider, paste API key

# Verify
hermes doctor
hermes chat -q "Hello, world. Confirm you are running."
```

---

## Phase 2: Knowledge Base Bootstrap (Day 1-2)

### 2.1 Create the Directory Structure

```bash
mkdir -p /opt/data/telecom-orchestrator/{
    knowledge-base/{ontologies,standards,products,resources,services,workflows,reference},
    skills,
    templates,
    scripts,
    inventory
}
```

### 2.2 Seed Core Ontology (already done — see knowledge-base/ontologies/core-ontology.md)

### 2.3 Create Product Catalog Template

Create `/opt/data/telecom-orchestrator/knowledge-base/products/product-catalog.md`:

```yaml
# Example product entry
- id: "prod-l3vpn-01"
  name: "Enterprise MPLS L3VPN"
  category: "VPN"
  description: "RFC 4364-compliant MPLS Layer 3 VPN with BGP/MPLS control plane"
  service_template: "templates/l3vpn-tosca.yaml"
  required_resources:
    - type: "VRF"
      count: 1
    - type: "BGP_PEERING"
      count: 2
    - type: "IP_SUBNET"
      count: 1
    - type: "INTERFACE"
      count: 1
  provisioning_workflow: "workflows/provision-l3vpn.md"
  assurance_workflow: "workflows/assure-l3vpn.md"
  supported_devices: ["cisco-ios-xr", "cisco-ios-xe", "juniper-junos", "nokia-sros"]
```

### 2.4 Create Seed Workflows

Each workflow is a markdown file in `knowledge-base/workflows/` with:

```markdown
# Workflow: Provision MPLS L3VPN

## Trigger
User: "Create MPLS L3VPN for customer {customer_name} at site {site}"

## Prerequisites
- Customer exists in CRM / inventory
- Target PE router is reachable and has capacity
- IP addressing plan available
- BGP ASN/RD/RT scheme defined

## Steps

### 1. PRE-FLIGHT: Feasibility Check
- Query NetBox for target PE router capacity (available VRFs, interfaces, memory)
- Validate customer address space doesn't conflict with existing allocations
- Check BGP route-target uniqueness
- Return: PASS/BLOCK with reason

### 2. ALLOCATE: Resource Reservation
- Allocate VRF name from naming convention: CUST-{site_code}-{vrf_role}
- Allocate Route Distinguisher: {ASN}:{next_available_id}
- Allocate Route Target (import + export): {ASN}:{next_available_id}
- Allocate CE-facing IP subnet from pool
- Reserve PE interface or subinterface

### 3. CONFIGURE: Device-Level Provisioning
- Push VRF definition on PE router(s) via NETCONF/Ansible:
  - vrf definition CUST-SJC-CORP
  - rd 65001:1001
  - route-target import 65001:1001
  - route-target export 65001:1001
- Configure CE-facing interface/subinterface:
  - interface GigabitEthernet0/0/0.1001
  - encapsulation dot1q 1001
  - vrf forwarding CUST-SJC-CORP
  - ip address 10.1.1.1 255.255.255.252
- Configure BGP peering with CE:
  - router bgp 65001
  - address-family ipv4 vrf CUST-SJC-CORP
  - neighbor 10.1.1.2 remote-as 65002
  - neighbor 10.1.1.2 activate

### 4. VERIFY: Post-Provisioning Checks
- Ping CE interface from PE VRF
- Verify BGP session state (Established)
- Verify route table has CE prefixes
- Run MPLS traceroute through LSP
- Log all verification output

### 5. ACTIVATE: State Transition
- Update service state: PROVISIONING → ACTIVE
- Update resource states: CONFIGURING → IN_SERVICE
- Notify customer (or ticketing system)
- Log completion with all resource IDs

## Rollback
- Remove BGP neighbor config
- Remove interface IP and VRF assignment
- Delete VRF definition
- Release IP subnet, RD, RT back to pools
- Update service state: PROVISIONING → TERMINATED
```

---

## Phase 3: Hermes Skills (Day 2-3)

### 3.1 Skill Structure

Each skill lives under `~/.hermes/skills/` or project `skills/` directory:

```
telecom-orchestrator/skills/
├── orchestrator-bootstrap.md     # Master skill: loads all others, defines agent persona
├── service-provisioning.md       # Create/fulfil a new service
├── resource-provisioning.md      # Configure a single resource
├── inventory-query.md            # Query NetBox / resource inventory via MCP
├── network-config-push.md        # Push config to devices via Ansible/NAPALM
├── feasibility-check.md          # Pre-provisioning validation
└── service-assurance.md          # Health check, fault correlation
```

### 3.2 Example Skill: service-provisioning

```markdown
---
name: telecom-service-provisioning
description: "End-to-end service provisioning for telecom products on Hermes"
tags: [telecom, provisioning, orchestration, l3vpn, sdwan]
---

# Telecom Service Provisioning

## Trigger
When the user asks to create, provision, or deploy a telecom service for a customer.

## Workflow

### Step 1: Parse Intent
Extract from the user request:
- Service type (L3VPN, SD-WAN, Internet, CloudConnect, Voice, etc.)
- Customer name / ID
- Service parameters (bandwidth, sites, addressing, etc.)

### Step 2: Check Memory for Similar Patterns
```
session_search(query="<service_type> provision <similar_parameters>")
memory_search for service pattern matches
```

### Step 3: Research Knowledge Base
```
search_files in /opt/data/telecom-orchestrator/knowledge-base/products/ for matching product
read_file the matching service template and provisioning workflow
```

### Step 4: Feasibility Check
Run feasibility workflow:
```
Check resource availability in inventory
Validate no conflicts
Return PASS/BLOCK with reasoning
```

### Step 5: Generate Orchestration Plan
Create a step-by-step orchestration plan with:
- Resources to allocate
- Configurations to push
- Order of operations
- Verification steps
- Rollback procedure

### Step 6: Execute via MCP
Dispatch each step to the appropriate MCP server:
- NetBox MCP for IPAM/inventory operations
- Ansible MCP for device configuration
- NSO MCP for service activation (if available)

### Step 7: Verify and Activate
- Verify all resources are IN_SERVICE
- Update service state to ACTIVE
- Log the orchestration result

### Step 8: Persist Pattern
Save successful orchestration pattern to memory:
- Service type, resources used, config patterns, device models
- Update the knowledge base with any new learnings

## Verification
- Service state = ACTIVE in inventory
- All child resources state = IN_SERVICE
- Verification checks passed (ping, BGP, trace)
```

---

## Phase 4: MCP Server Integration (Day 3-4)

### 4.1 NetBox MCP Server

NetBox is your source of truth for IPAM, DCIM, and circuit management.

```bash
# Install NetBox on same VPS or separate
# Then create MCP server that wraps NetBox API

# Add to Hermes:
hermes mcp add netbox --command "python3 /opt/data/telecom-orchestrator/mcp-servers/netbox_mcp.py"
hermes mcp test netbox
hermes mcp configure netbox  # Toggle which tools are exposed
```

The MCP server exposes tools like:
- `netbox_get_device(name)` — Query device details, interfaces, status
- `netbox_allocate_ip(prefix_id)` — Allocate next available IP
- `netbox_create_vlan(vid, name, site)` — Create VLAN
- `netbox_create_circuit(cid, provider, type, bandwidth)` — Create circuit
- `netbox_assign_ip(interface_id, address)` — Assign IP to interface

### 4.2 Ansible MCP Server

Wraps ansible-runner for push-button config deployment.

```bash
hermes mcp add ansible --command "python3 /opt/data/telecom-orchestrator/mcp-servers/ansible_mcp.py"
```

Exposes:
- `ansible_run_playbook(playbook, inventory, limit, extra_vars)`
- `ansible_get_facts(device)`
- `ansible_validate_config(device, config_type)`

### 4.3 Device-Specific MCP Servers

For direct device interaction without Ansible:

```bash
hermes mcp add netmiko-router --command "python3 /opt/data/telecom-orchestrator/mcp-servers/device_mcp.py"
```

Exposes:
- `device_show_command(device, command)` — Run show command
- `device_configure(device, config_lines)` — Push configuration
- `device_validate_state(device, expected_state)` — Validate config state

---

## Phase 5: Cron Jobs for Autonomous Operation (Day 4-5)

### 5.1 Resource Discovery (Daily)

```bash
hermes cron create "0 2 * * *" \
  --name "resource-discovery" \
  --prompt "Run resource discovery: sync all network devices' actual configuration and state into the inventory database. Compare against known state and flag discrepancies. Update /opt/data/telecom-orchestrator/inventory/ with findings." \
  --deliver local
```

### 5.2 Service Assurance (Every 30 minutes)

```bash
hermes cron create "30m" \
  --name "service-assurance" \
  --prompt "Run service health check on all ACTIVE services. For each: verify BGP sessions are Established, ping CE loopback, check interface counters for errors, verify QoS policy hit counts. Flag any service with failures and log to /opt/data/telecom-orchestrator/assurance/alerts.md." \
  --deliver local
```

### 5.3 Capacity Trending (Weekly)

```bash
hermes cron create "0 8 * * 1" \
  --name "capacity-trending" \
  --prompt "Analyze resource utilisation trends from inventory history. Identify pools below 20% remaining capacity (VRFs per PE, IP subnets, interface slots, BGP sessions). Generate a capacity report at /opt/data/telecom-orchestrator/reports/capacity-{date}.md with recommendations." \
  --deliver local
```

---

## Phase 6: Multi-Profile for Multi-Tenant (Day 5)

If you serve multiple customers or environments:

```bash
# Production orchestrator
hermes profile create prod
hermes profile use prod
hermes setup model

# Staging / test orchestrator
hermes profile create staging --clone-from prod

# Customer-specific knowledge bases (if needed)
hermes profile create cust-acme --clone-from prod
```

---

## Phase 7: Gateway & Multi-Platform Access (Day 5-6)

```bash
# Expose orchestrator on Telegram for operator queries
hermes gateway setup
# Follow prompts for Telegram bot token, etc.

hermes gateway install
hermes gateway start
```

Operators can then query from their phones:
- "What's the status of Acme Corp's L3VPN service?"
- "Create an SD-WAN service for Beta Inc with 3 sites"

---

## The Agentic Query Flow (End-to-End Example)

When someone asks: "Create a 100 Mbps MPLS L3VPN for Acme Corp at their San Jose site"

```
STEP 1: PARSE INTENT
  ├─ Extract: type=L3VPN, customer=Acme Corp, site=San Jose, bandwidth=100Mbps
  └─ Agent: "I need to provision an MPLS L3VPN"

STEP 2: RECALL PATTERNS
  ├─ session_search("L3VPN provision") → finds 3 prior similar services
  ├─ memory → retrieves L3VPN ontology: VRF, BGP peer, interface, IP subnet
  └─ Agent: "I've done this before. Standard pattern: VRF + BGP + CE interface"

STEP 3: RESEARCH KB
  ├─ read_file knowledge-base/products/product-catalog.md → L3VPN product spec
  ├─ read_file knowledge-base/workflows/provision-l3vpn.md → step-by-step workflow
  └─ Agent: "Product requires: 1x VRF, 1x BGP peering, 1x IP subnet, 1x interface"

STEP 4: FEASIBILITY CHECK
  ├─ Terminal: query NetBox MCP for PE router "sfo-pe-01" capacity
  ├─ Validate: VRF count ok, interface slot available, no IP conflict
  ├─ Result: PASS ✓
  └─ Agent: "PE router sfo-pe-01 has capacity. Proceeding."

STEP 5: ALLOCATE RESOURCES
  ├─ VRF: CUST-SJC-CORP (allocated)
  ├─ RD: 65001:1001 (next available)
  ├─ RT import/export: 65001:1001
  ├─ CE subnet: 10.1.0.0/30 (from SJC-CE pool)
  ├─ Interface: GigabitEthernet0/0/0.1001 (next available subint)
  └─ Agent: "Resources allocated. Pushing configuration."

STEP 6: PUSH CONFIGURATION
  ├─ Ansible MCP → cisco-ios-xr L3VPN playbook with vars
  ├─ VRF definition → COMMITTED
  ├─ Interface config → COMMITTED
  ├─ BGP neighbor config → COMMITTED
  └─ Agent: "Configuration deployed to sfo-pe-01."

STEP 7: VERIFY
  ├─ Ping 10.1.0.2 from VRF CUST-SJC-CORP → SUCCESS (4.2ms)
  ├─ BGP state → ESTABLISHED, 12 prefixes received
  ├─ MPLS traceroute → 2 hops, valid LSP
  └─ Agent: "All checks passed."

STEP 8: ACTIVATE & PERSIST
  ├─ Update service state → ACTIVE
  ├─ Update resource states → IN_SERVICE
  ├─ memory("L3VPN provisioned for Acme/SJC: PE=sfo-pe-01, VRF=CUST-SJC-CORP, pattern=...")
  ├─ Update knowledge base if new learnings
  └─ Agent: "Service ACTIVE. Pattern saved for future reference."
```

---

## Technology Stack Summary

| Layer               | Technology                                   | Purpose                                      |
|---------------------|----------------------------------------------|----------------------------------------------|
| Agent Framework     | Hermes Agent (Nous Research)                 | Core reasoning, tool orchestration           |
| LLM                 | DeepSeek v4 / Claude Sonnet 4 / GPT-4o       | Natural language understanding, planning     |
| Memory              | Hermes built-in memory                       | Pattern persistence, ontology accumulation  |
| Skills              | Hermes SKILL.md                              | Reusable procedural knowledge                |
| Knowledge Base      | Markdown files + SQLite                      | Domain reference, product catalog, workflows |
| MCP                 | Hermes native MCP client                     | External tool integration (NetBox, Ansible)  |
| Cron                | Hermes cron scheduler                        | Autonomous assurance, discovery, capacity    |
| Source of Truth     | NetBox (DCIM/IPAM)                           | Device inventory, IP addressing, circuits    |
| Config Automation   | Ansible + NAPALM + Netmiko                   | Device configuration push                    |
| NFV Orchestrator    | OSM / OpenStack Tacker (optional)            | VNF lifecycle management                     |
| SDN Controller      | ONOS / ODL / Cisco NSO (optional)            | Centralised network control                  |
| Messaging           | Hermes Gateway (Telegram/Discord/Slack)      | Operator interaction                         |
| Hosting             | Hostinger VPS (KVM-4+)                       | Runtime environment                          |
| Transport Security  | WireGuard / Tailscale (if multi-site)        | Secure agent-to-device connectivity          |

---

## Getting Started: Minimum Viable Orchestrator (Week 1)

```bash
# 1. Bootstrap Hermes
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup
hermes doctor

# 2. Clone the knowledge base
mkdir -p /opt/data/telecom-orchestrator
cd /opt/data/telecom-orchestrator
# Copy the knowledge-base/ structure created above

# 3. Create the bootstrap skill
hermes skill create telecom-orchestrator-bootstrap
# Paste the master skill content

# 4. Create a test product + workflow
# Add a simple "Test Loopback Service" product to product-catalog.md
# Add a minimal workflow that creates a loopback interface on a test router

# 5. Wire up a test device
# Set up a CSR1000v or Juniper vMX in a lab
# Add it to NetBox inventory
# Create Ansible MCP bridge

# 6. Test the end-to-end flow
hermes -s telecom-service-provisioning
> "Create a test loopback service on lab-router-01 for TestCustomer"
```

---

## Key Design Principles

1. **Knowledge-first**: The KB is the source of truth. Every orchestration decision traces back to documented product specs and workflows.
2. **Pattern memory**: Every successful provisioning is persisted in memory. The ontology grows with use.
3. **MCP bridge**: Never hardcode device interaction. Every external system is an MCP server — swappable, testable, versionable.
4. **Idempotent workflows**: Every workflow must be safe to re-run. Check state before acting.
5. **Rollback built-in**: Every provisioning workflow has a corresponding rollback section.
6. **Autonomous assurance**: Cron jobs keep services healthy without human intervention. Agent only flags what needs attention.
