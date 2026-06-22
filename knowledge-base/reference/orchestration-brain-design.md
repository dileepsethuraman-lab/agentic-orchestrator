# Orchestration Brain — Solution Design

> Owner: Orchestration Team | Consumes: Workflow Team's MCP
> Northbound: TMF640 Service Activation / TMF641 Service Ordering
> Southbound: Workflow MCP (dynamic workflow execution)
> Version: 1.0

## 1. What the Orchestration Brain IS and IS NOT

### IS
- A reasoning engine that accepts TMF640/TMF641 requests
- A pattern-matching system that searches a knowledge base for similar past orchestrations
- A context-aware planner that uses request characteristics (customer segment, SLA tier, product type) to derive expected service state and required network attributes
- A workflow selector that determines which workflows the downstream MCP must execute, in what order, with what parameters
- A continuous learner that updates its knowledge base after every request

### IS NOT
- It does NOT execute workflows — that's the Workflow Team's MCP
- It does NOT push device configuration — that's inside the workflows
- It does NOT manage resource inventory — it calls the MCP, which does
- It does NOT handle the CRM integration or webhook delivery — that's the Order Manager

---

## 2. Architecture

```
══════════════════════════════════════════════════════════════════════════
                          INBOUND
══════════════════════════════════════════════════════════════════════════

   TMF641 ServiceOrder (or TMF640 ServiceActivation)
   │
   │  {
   │    "id": "so-l3vpn-0042",
   │    "externalId": "CRM-ORDER-12345",
   │    "category": "VPN",
   │    "action": "add",
   │    "relatedParty": [
   │      {"role": "customer", "id": "CUST-0042"},
   │      {"role": "channel", "name": "wholesale"}      ← customer segment
   │    ],
   │    "characteristic": [
   │      {"name": "customerSegment",  "value": "wholesale"},
   │      {"name": "slaTier",         "value": "platinum"},
   │      {"name": "productId",       "value": "prod-l3vpn-01"},
   │      {"name": "bandwidth",       "value": "1000"},
   │      {"name": "sites",           "value": "3"},
   │      {"name": "routingProtocol", "value": "BGP"},
   │      ...
   │    ]
   │  }
   │
   ▼
══════════════════════════════════════════════════════════════════════════
                    ORCHESTRATION BRAIN
══════════════════════════════════════════════════════════════════════════

   ┌─────────────────────────────────────────────────────────────┐
   │                     STAGE 1: PARSE                          │
   │                                                             │
   │  Extract from the TMF640/641 request:                      │
   │    - Customer segment  (wholesale | retail | enterprise)   │
   │    - SLA tier          (platinum | gold | silver | bronze) │
   │    - Product ID        (prod-l3vpn-01)                     │
   │    - Action            (add | modify | delete | suspend)    │
   │    - All characteristics as key-value pairs                │
   │    - Related parties   (customer, channel, requester)      │
   │                                                             │
   │  Output: Structured ParseResult                             │
   └────────────────────────────┬────────────────────────────────┘
                                │
   ┌────────────────────────────▼────────────────────────────────┐
   │                     STAGE 2: MATCH                          │
   │                                                             │
   │  Search knowledge base for similar patterns:               │
   │                                                             │
   │  Exact match:                                               │
   │    "product=prod-l3vpn-01 + segment=wholesale + sla=platinum"│
   │    → If found: reuse the exact plan, skip to validation    │
   │                                                             │
   │  Partial match:                                             │
   │    "product=prod-l3vpn-01 + segment=wholesale"              │
   │    → Found 12 past patterns, SLA tier differs               │
   │    → Adapt the plan using SLA-specific overrides            │
   │                                                             │
   │  No match:                                                  │
   │    → Decompose from first principles using product template │
   │    → This is a novel orchestration — flag for review        │
   │                                                             │
   │  Output: MatchedPattern (exact | adapted | novel)           │
   │  + Confidence score                                          │
   └────────────────────────────┬────────────────────────────────┘
                                │
   ┌────────────────────────────▼────────────────────────────────┐
   │                     STAGE 3: REASON                         │
   │                                                             │
   │  Derive expected service state from context:               │
   │                                                             │
   │  Customer Segment → affects:                               │
   │    wholesale:                                              │
   │      - CE device: customer-managed (not in our scope)      │
   │      - Handoff: VLAN subinterface on PE, BGP peering      │
   │      - QoS: customer marks, we trust/transparent          │
   │      - IP addressing: customer provides WAN IPs (or /30)  │
   │      - MTU: 9100 (jumbo for MPLS)                         │
   │      - State target: PE side only, CE is customer's       │
   │                                                             │
   │    retail:                                                  │
   │      - CE device: provider-managed CPE                    │
   │      - Handoff: LAN interface on CPE, default route       │
   │      - QoS: provider-applied shaping/policing             │
   │      - IP addressing: provider-managed DHCP or static     │
   │      - MTU: 1500 (standard Ethernet)                      │
   │      - State target: end-to-end including CPE             │
   │                                                             │
   │    enterprise:                                             │
   │      - CE device: customer-managed but with managed handoff│
   │      - Handoff: physical cross-connect or ENNI            │
   │      - QoS: agreed CoS profile, 5-class model             │
   │      - IP addressing: provider /30, customer /29 behind   │
   │      - State target: PE side + L2 handoff verification    │
   │                                                             │
   │  SLA Tier → affects:                                       │
   │    platinum: dual PE, diverse paths, <50ms failover       │
   │    gold:     dual PE, shared diverse, <200ms failover     │
   │    silver:   single PE, best-effort failover              │
   │    bronze:   single PE, no redundancy                     │
   │                                                             │
   │  Output: ExpectedServiceState                              │
   │    {                                                       │
   │      "targetState": "active",                              │
   │      "ceModel": "customer_managed",                        │
   │      "handoffType": "vlan_subinterface",                   │
   │      "qosProfile": "trust_customer",                       │
   │      "ipScheme": "provider_assigned_p2p",                  │
   │      "mtu": 9100,                                          │
   │      "redundancy": "dual_pe_diverse",                      │
   │      "failoverTarget": 50,   // ms                         │
   │      "verificationScope": "pe_only"                        │
   │    }                                                       │
   └────────────────────────────┬────────────────────────────────┘
                                │
   ┌────────────────────────────▼────────────────────────────────┐
   │                     STAGE 4: PLAN                           │
   │                                                             │
   │  Given: ParseResult + MatchedPattern + ExpectedServiceState │
   │                                                             │
   │  Determine the WORKFLOWS needed from the MCP:              │
   │                                                             │
   │  1. Look up product template → yields REQUIRED workflows   │
   │     e.g., product "prod-l3vpn-01" requires:                │
   │       - ResourceAllocation (VRF, IP, RD/RT)               │
   │       - DeviceConfiguration (PE router)                   │
   │       - PeeringConfiguration (BGP)                        │
   │       - ServiceVerification (ping, BGP state, traceroute) │
   │       - StateActivation (update inventory)                │
   │                                                             │
   │  2. Apply segment/SLA overrides → adds/removes workflows   │
   │     e.g., wholesale:                                       │
   │       + QoSConfiguration (if not "trust")                 │
   │       - CPEDeployment (CE is customer-managed)            │
   │     e.g., platinum:                                        │
   │       + RedundancyConfiguration (dual PE)                 │
   │       + FastFailoverConfiguration (BFD, <50ms)            │
   │                                                             │
   │  3. Derive workflow PARAMETERS from characteristics       │
   │     e.g., bandwidth=1000 → QoS policer 1000Mbps            │
   │     e.g., sites=3 → 3x ResourceAllocation + 3x Config     │
   │                                                             │
   │  4. Order workflows respecting dependencies               │
   │     ResourceAllocation BEFORE DeviceConfiguration          │
   │     DeviceConfiguration BEFORE PeeringConfiguration        │
   │     PeeringConfiguration BEFORE ServiceVerification        │
   │                                                             │
   │  Output: OrchestrationPlan                                 │
   │    [                                                       │
   │      { "workflow": "ResourceAllocation",                   │
   │        "params": {                                         │
   │          "resources": [                                    │
   │            {"type": "VRF", "namingConvention": "CUST-{site}-CORP", ...},│
   │            {"type": "BGP_PEERING", "asn": 65001, ...},    │
   │            {"type": "IP_SUBNET", "pool": "SJC-CE", ...}   │
   │          ]                                                 │
   │        }                                                   │
   │      },                                                    │
   │      { "workflow": "DeviceConfiguration", ... },           │
   │      { "workflow": "QoSConfiguration", ... },             │
   │      { "workflow": "PeeringConfiguration", ... },         │
   │      { "workflow": "ServiceVerification", ... },          │
   │      { "workflow": "StateActivation", ... }               │
   │    ]                                                       │
   └────────────────────────────┬────────────────────────────────┘
                                │
   ┌────────────────────────────▼────────────────────────────────┐
   │                     STAGE 5: DELEGATE                       │
   │                                                             │
   │  Call the Workflow Team's MCP with the OrchestrationPlan:  │
   │                                                             │
   │  For each workflow in the plan (sequential, respecting     │
   │  dependencies, or parallel when independent):              │
   │                                                             │
   │    mcp_execute_workflow(                                   │
   │      workflowName: "ResourceAllocation",                   │
   │      params: { ... },                                      │
   │      context: { serviceOrderId, customerSegment, ... }     │
   │    )                                                        │
   │                                                             │
   │  Wait for result. On success → next workflow.              │
   │  On failure → check if rollback workflows exist.           │
   │                                                             │
   │  The MCP's job: translate the workflow name into actual    │
   │  actions (NetBox API calls, Ansible playbooks, device      │
   │  commands). The brain doesn't know or care how.            │
   └────────────────────────────┬────────────────────────────────┘
                                │
   ┌────────────────────────────▼────────────────────────────────┐
   │                     STAGE 6: VERIFY & LEARN                 │
   │                                                             │
   │  Compare actual result against ExpectedServiceState:       │
   │                                                             │
   │  Did all workflows succeed?                                │
   │    YES → Service state = ACTIVE                            │
   │    NO  → Rollback or hold, log failure                     │
   │                                                             │
   │  Does the actual state match the expected state?           │
   │    e.g., for wholesale: was CE correctly excluded?         │
   │    e.g., for platinum: are both PEs configured?            │
   │    Mismatch → flag for human review, possible KB error     │
   │                                                             │
   │  LEARN:                                                     │
   │    Save the full orchestration trace:                      │
   │      - Request hash (characteristics)                      │
   │      - Matched pattern (exact | adapted | novel)           │
   │      - Customer segment + SLA tier used                    │
   │      - Workflows selected + parameters                     │
   │      - Success/failure, timings, any adaptations made      │
   │                                                             │
   │    Update the pattern store:                               │
   │      - New exact match? Add it.                            │
   │      - Existing pattern refined? Update it.                │
   │      - Novel pattern worked? Promote it as a template.     │
   │      - Pattern failed? Record why, decrease confidence.    │
   │                                                             │
   │  Output: OrchestrationResult                               │
   │    {                                                       │
   │      "orderId": "so-l3vpn-0042",                           │
   │      "status": "completed",                                │
   │      "serviceId": "svc-acme-sjc-l3vpn",                    │
   │      "workflowsExecuted": 6,                               │
   │      "totalDurationMs": 42000,                             │
   │      "patternMatch": "adapted",                            │
   │      "confidenceAfter": 0.94                               │
   │    }                                                       │
   └─────────────────────────────────────────────────────────────┘
```

---

## 3. Customer Segment → Expected State Mapping

This is the core reasoning table. The brain uses request characteristics to derive what the finished service must look like before it even asks the MCP for workflows.

```
CHARACTERISTIC    WHOLESALE              RETAIL                  ENTERPRISE
─────────────────────────────────────────────────────────────────────────────
CE ownership      Customer-managed       Provider-managed        Customer-managed
                                        (CPE deployed by us)    (managed handoff)

Handoff type      VLAN subinterface      LAN port on CPE         Physical cross-
                  on PE router           (RJ45/SFP)              connect or ENNI

IP addressing     Provider /30 p2p       Provider DHCP or        Provider /30 p2p
                  (customer may bring    static LAN block        + customer /29
                   their own)                                    routed block

Routing           eBGP (customer ASN)    Static default route    eBGP (customer ASN)
                                        or eBGP (if managed)    or static

QoS model         Trust customer DSCP    Provider shapes at      Agreed CoS profile
                  (transparent)          CIR, remarks exceeding  (5-class model)

MTU               9100 (jumbo MPLS)      1500 (standard Eth)     9100 or 9000

Redundancy        Depends on SLA tier    Silver+: dual CPE       Depends on SLA tier
                  (gold+: dual PE)       (VRRP/HSRP to PE)

NAT/Firewall      Customer-managed       Provider-managed        Customer-managed
                                        (CPE does NAT/ACL)

Verification      PE side only           End-to-end (CPE + PE)   PE + handoff L2
scope             (BGP, VRF route tbl)   (LAN ping, speed test)  (light levels, BGP)

Monitoring        Port/interface only    Full CPE + PE           PE + handoff
                                                                 interface

Ordered as        "MPLS access circuit"  "Managed Internet"      "Enterprise VPN"
```

---

## 4. Knowledge Base Structure

The brain's knowledge base is a versioned store of orchestration patterns:

```
/opt/data/orchestration-brain/knowledge-base/
│
├── patterns/
│   └── pattern-store.db          SQLite — the core pattern database
│       │
│       ├── patterns table:
│       │   id, pattern_hash (sha256 of characteristics),
│       │   product_id, customer_segment, sla_tier,
│       │   workflow_plan (JSON), expected_state (JSON),
│       │   success_count, failure_count, last_used_at,
│       │   confidence (0.0–1.0), status (active|deprecated|experimental)
│       │
│       ├── pattern_adaptations table:
│       │   id, base_pattern_id, adaptation_reason,
│       │   added_workflows (JSON), removed_workflows (JSON),
│       │   parameter_overrides (JSON), created_by_order_id
│       │
│       └── orchestration_traces table:
│           id, order_id, request_hash, matched_pattern_id,
│           match_type (exact|adapted|novel), workflows_executed (JSON),
│           execution_timings (JSON), success, error_message,
│           reviewed (boolean), created_at
│
├── templates/
│   └── product-templates/         Product → required workflows + defaults
│       ├── prod-l3vpn-01.yaml
│       ├── prod-sdwan-01.yaml
│       ├── prod-dia-01.yaml
│       └── ...
│
├── segments/
│   └── segment-overrides.yaml     Customer segment → state/attribute overrides
│
├── sla/
│   └── sla-overrides.yaml         SLA tier → redundancy/QoS/schedule overrides
│
└── lessons/
    └── lessons.yaml               Human-reviewed corrections and refinements
```

### Pattern Store Schema

```sql
CREATE TABLE patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_hash    TEXT NOT NULL UNIQUE,     -- SHA256 of normalized characteristics
    product_id      TEXT NOT NULL,
    customer_segment TEXT NOT NULL,          -- wholesale | retail | enterprise
    sla_tier        TEXT NOT NULL,            -- platinum | gold | silver | bronze
    action          TEXT NOT NULL DEFAULT 'add',  -- add | modify | delete
    workflow_plan   TEXT NOT NULL,            -- JSON array of {workflow, params}
    expected_state  TEXT NOT NULL,            -- JSON of derived state expectations
    success_count   INTEGER DEFAULT 0,
    failure_count   INTEGER DEFAULT 0,
    confidence      REAL DEFAULT 0.5,         -- 0.0 to 1.0
    status          TEXT DEFAULT 'active',    -- active | deprecated | experimental
    created_at      TEXT DEFAULT (datetime('now')),
    last_used_at    TEXT
);

CREATE TABLE orchestration_traces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT NOT NULL,
    request_hash    TEXT NOT NULL,
    matched_pattern_id INTEGER REFERENCES patterns(id),
    match_type      TEXT NOT NULL,            -- exact | adapted | novel
    workflow_plan   TEXT NOT NULL,            -- Actual plan used (JSON)
    expected_state  TEXT NOT NULL,            -- Expected state derived (JSON)
    actual_state    TEXT,                     -- Actual state achieved (JSON)
    execution_timings TEXT,                  -- JSON [{workflow, duration_ms, status}]
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    reviewed        BOOLEAN DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);
```

---

## 5. Matching Algorithm

```
FUNCTION findBestPattern(request):
    characteristics = normalize(request.characteristics)
    hash = sha256(characteristics)

    // STAGE A: Exact match
    exact = SELECT * FROM patterns
            WHERE pattern_hash = hash
              AND status = 'active'
            ORDER BY confidence DESC
            LIMIT 1
    IF exact:
        exact.success_count += 1
        exact.confidence = min(1.0, exact.confidence + 0.01)
        RETURN { matchType: "exact", pattern: exact, confidence: exact.confidence }

    // STAGE B: Product + Segment + SLA match (ignore other characteristics)
    similar = SELECT * FROM patterns
              WHERE product_id = product
                AND customer_segment = segment
                AND sla_tier = sla
                AND action = action
                AND status = 'active'
              ORDER BY confidence DESC, success_count DESC

    IF similar.length > 0:
        best = similar[0]
        // Check if adaptation exists
        adaptation = SELECT * FROM pattern_adaptations
                     WHERE base_pattern_id = best.id
        IF adaptation:
            plan = merge(best.workflow_plan, adaptation)
        ELSE:
            plan = best.workflow_plan

        RETURN { matchType: "adapted", pattern: best, confidence: best.confidence * 0.9 }

    // STAGE C: Product + Segment only (different SLA)
    relaxed = SELECT * FROM patterns
              WHERE product_id = product
                AND customer_segment = segment
                AND action = action
                AND status = 'active'
              ORDER BY confidence DESC
              LIMIT 1

    IF relaxed:
        plan = relaxed.workflow_plan
        // Apply SLA overrides from sla/sla-overrides.yaml
        plan = applySLAOverrides(plan, sla_tier)
        RETURN { matchType: "adapted", pattern: relaxed, confidence: relaxed.confidence * 0.7 }

    // STAGE D: Product only (novel segment)
    bare = SELECT * FROM patterns
           WHERE product_id = product
             AND action = action
             AND status = 'active'
           ORDER BY confidence DESC
           LIMIT 1

    IF bare:
        plan = bare.workflow_plan
        plan = applySegmentOverrides(plan, segment)   // from segments/segment-overrides.yaml
        plan = applySLAOverrides(plan, sla_tier)       // from sla/sla-overrides.yaml
        RETURN { matchType: "adapted", pattern: bare, confidence: bare.confidence * 0.5 }

    // STAGE E: No match — use product template from first principles
    template = loadProductTemplate(product)
    plan = buildPlanFromTemplate(template, segment, sla, characteristics)
    RETURN { matchType: "novel", pattern: null, confidence: 0.3 }
```

---

## 6. Learning Loop

After every orchestration, successful or not:

```
FUNCTION learn(request, matchResult, executionResult):

    trace = INSERT INTO orchestration_traces (
        order_id, request_hash, matched_pattern_id,
        match_type, workflow_plan, expected_state,
        actual_state, execution_timings, success, error_message
    )

    IF executionResult.success:
        IF matchResult.matchType == "exact":
            // Reinforce existing pattern
            UPDATE patterns
            SET success_count = success_count + 1,
                confidence = min(1.0, confidence + 0.01),
                last_used_at = now()
            WHERE id = matchResult.pattern.id

        ELIF matchResult.matchType == "adapted":
            // Was the adaptation significant?
            diff = computeDiff(matchResult.pattern.workflow_plan, executionResult.plan_used)

            IF diff is significant:
                // This adaptation might be worth saving as its own pattern
                INSERT INTO pattern_adaptations (
                    base_pattern_id, adaptation_reason,
                    added_workflows, removed_workflows,
                    parameter_overrides, created_by_order_id
                ) VALUES (...)

                // If same adaptation seen 3+ times, promote to a new pattern
                similar_adaptations = COUNT pattern_adaptations with same diff
                IF similar_adaptations >= 3:
                    new_hash = sha256(normalized characteristics for this adapted case)
                    INSERT INTO patterns (
                        pattern_hash, product_id, customer_segment, sla_tier,
                        workflow_plan, expected_state, confidence, status
                    ) VALUES (new_hash, ..., 0.6, 'experimental')

                    // After 10 successful uses, promote to 'active'
            ELSE:
                // Minor adaptation, just reinforce the base pattern
                UPDATE patterns
                SET confidence = min(1.0, confidence + 0.005)
                WHERE id = matchResult.pattern.id

        ELIF matchResult.matchType == "novel":
            // New pattern discovered!
            new_hash = sha256(normalized characteristics)
            INSERT INTO patterns (
                pattern_hash, product_id, customer_segment, sla_tier,
                workflow_plan, expected_state, confidence, status
            ) VALUES (new_hash, ..., 0.4, 'experimental')
            // Flag for human review

    ELSE:
        // Failure: don't reinforce, record why
        UPDATE patterns
        SET failure_count = failure_count + 1,
            confidence = max(0.1, confidence - 0.05)
        WHERE id = matchResult.pattern.id

        // If pattern fails 3 times consecutively, deprecate it
        recent_failures = SELECT failure_count FROM patterns WHERE id = ...
        IF recent_failures >= 3 AND last 3 traces all failed:
            UPDATE patterns SET status = 'deprecated'
            ALERT: "Pattern {id} deprecated after 3 consecutive failures"
```

---

## 7. Interface Contract with the Workflow Team

The orchestration brain calls the Workflow MCP. Here's the contract:

### MCP Tools the Brain Expects

```
1. list_workflows()
   → Returns: [{name, description, required_params, optional_params, version}]
   Used during Stage 4 (Plan) to validate available workflows.

2. execute_workflow(workflowName, params, context)
   → Returns: {status, workflowRunId, output, duration_ms}
   Used during Stage 5 (Delegate).

3. get_workflow_status(workflowRunId)
   → Returns: {status (running|completed|failed), output, duration_ms}
   For long-running workflows.

4. rollback_workflow(workflowRunId)
   → Returns: {status, rolledBackWorkflowRunId}
   If a later workflow fails, roll back earlier ones.

5. validate_workflow_params(workflowName, params)
   → Returns: {valid, errors: [{field, message}]}
   Pre-flight validation before execution.
```

### What the Brain Passes to the MCP

```json
{
  "workflowName": "ResourceAllocation",
  "params": {
    "customerSegment": "wholesale",
    "productId": "prod-l3vpn-01",
    "resources": [
      {
        "type": "VRF",
        "name": "CUST-SJC-CORP",
        "routeDistinguisher": "65001:1001",
        "routeTargetImport": "65001:1001",
        "routeTargetExport": "65001:1001",
        "targetDevice": "sfo-pe-01"
      },
      {
        "type": "IP_SUBNET",
        "pool": "SJC-CE-IPV4",
        "prefixLength": 30,
        "purpose": "ce_wan_link"
      }
    ]
  },
  "context": {
    "serviceOrderId": "so-l3vpn-0042",
    "customerId": "CUST-0042",
    "requestCharacteristics": { ... }
  }
}
```

### What the Brain Does NOT Pass

- Device credentials (workflow MCP manages its own vault)
- Specific CLI commands (the workflow builds those)
- Inventory database connection strings (MCP handles its own state)

---

## 8. Continuous Learning Cadence

```
IMMEDIATE (within the request):
  - Update pattern success/failure counts
  - Adjust confidence score
  - Save orchestration trace

DAILY (cron):
  - Review 'experimental' patterns with 5+ successes → promote to 'active'
  - Review 'active' patterns with 3+ recent failures → flag for deprecation
  - Generate pattern health report

WEEKLY (human-in-the-loop):
  - Review novel patterns (matchType=novel) awaiting approval
  - Review deprecated patterns — should they be deleted?
  - Analyse adaptation clusters — should N adaptations become a new pattern?
  - Prune traces older than 90 days (keep aggregate stats)
```

---

## 9. Deployment

The orchestration brain is a single Hermes agent, not a cluster. It doesn't need multiple workers because its job is pure reasoning — no device interaction, no long-running tasks. The MCP handles the heavy lifting.

```
┌─────────────────────────────────────────────┐
│          ORCHESTRATION BRAIN                 │
│                                              │
│  Single Hermes agent process                 │
│  Loaded with:                                │
│    - orchestration-brain skill (this design) │
│    - Knowledge base (SQLite pattern store +  │
│      YAML product templates + overrides)     │
│    - MCP connection to Workflow Team's MCP   │
│                                              │
│  Receives requests one at a time.            │
│  Each request: parse→match→reason→plan→      │
│                delegate→verify→learn.         │
│  Stateless between requests.                 │
│  Learns continuously via the KB.             │
└─────────────────────────────────────────────┘

Invoked by the Order Manager:
  hermes chat -q "Orchestrate this TMF641 ServiceOrder:
  {
    \"id\": \"so-l3vpn-0042\",
    ...full TMF641 JSON...
  }"
  -s orchestration-brain
  -p orchestration-brain
```

The Order Manager (separate component, built by a third team perhaps) handles HTTP, queues, webhooks. The Brain handles reasoning.

---

## 10. What Differentiates a Wholesale L3VPN from a Retail L3VPN

Same product (prod-l3vpn-01). Same fundamental network action (create VRF, peer BGP, assign IP). But different expected state:

```
                         WHOLESALE                     RETAIL
                         ─────────                     ──────
CE device                Customer's Juniper MX204      Our Cisco ISR 1111
CE config scope          Out of scope                  In scope (CPE workflow)
PE-CE subnet             /30, customer provides IP     /30, we provide both IPs
BGP                      Customer ASN 65002            Our private ASN 65000
                         We peer, they announce        We announce default only
                         We accept full routes         We accept nothing from CE
QoS on PE-CE link        Transparent (trust DSCP)      Shape to CIR, remark excess
Verification             BGP Established               BGP + LAN port up
                         VRF route table populated     + speed test to CPE LAN
                         MPLS LSP reachable            + CPE management reachable
Service state "active"   PE side green                 End-to-end green (CPE+PE)
```

The brain knows this because `customerSegment=wholesale` triggers the wholesale column of the segment mapping table, which drops the CPEDeployment workflow and changes the QoSConfiguration parameters from "shape" to "trust". Same product. Different plan. All derived from one field in the request.

---

## 11. Summary

The orchestration brain:

1. Receives TMF640/641 with characteristics INCLUDING customer segment
2. Matches against pattern store (exact → adapted → novel)
3. Reasons expected state from segment + SLA + product rules
4. Plans which workflows to request from the MCP
5. Delegates execution to the Workflow Team's MCP
6. Verifies actual vs expected state
7. Learns — updates pattern store, adjusts confidence, promotes/deprecates patterns

It is one Hermes agent. It does not execute. It reasons, plans, delegates, verifies, learns.
