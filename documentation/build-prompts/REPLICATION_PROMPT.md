# Telecom Agentic Orchestration Engine — Generic Replication Prompt

> **For any AI agent:** This document describes a Proof-of-Concept system in precise behavioral terms. It specifies WHAT the system must do, not HOW to build it. You are free to choose programming languages, frameworks, libraries, and architectural patterns that best satisfy these requirements. Every behavioral detail is described so that an independent implementation will produce identical observable results.

---

## 1. SYSTEM IDENTITY

### 1.1 What This System IS

A **cache-first, data-sovereign telecom service orchestration engine** with the following defining characteristics:

| Characteristic | Description |
|---------------|-------------|
| **Multi-format Ingress** | Accepts TMF640 Service Activation JSON, TMF641 Service Order JSON, AND unstructured natural language text (e.g., "activate new mobile service for retail customer with gold SLA") |
| **Async Pipeline** | Every request flows through a multi-stage pipeline. Early stages return synchronously; compute-intensive stages run asynchronously. A polling endpoint lets clients retrieve results. |
| **Cache-First** | Before invoking any LLM, the system checks a pattern store for a matching orchestration pattern. A cache HIT skips the LLM entirely (0ms AI latency). A MISS invokes reasoning, then persists the result for future hits. |
| **KB-Driven** | All network element definitions, required attributes, workflow names, and lifecycle state machines derive from a structured knowledge base — never from hardcoded lists. |
| **Data Sovereignty** | All sensitive identifiers (phone numbers, IMSI, IP addresses, hostnames) are replaced with anonymous tokens BEFORE any data leaves the local perimeter for cloud AI. The token-to-real mapping exists only in transient memory and is never persisted or transmitted. |
| **Pattern Learning** | Successful orchestrations are persisted as RDF-inspired graphs of triples (subject, predicate, object). Future requests are matched using Jaccard similarity on service-defining characteristics. |
| **Lifecycle Notifications** | The system emits TMF641-compliant events: ServiceOrderMilestoneEvent for intermediate provisioning states and ServiceOrderStateChangeEvent upon completion. |
| **Web Trace Viewer** | A browser-based UI shows every pipeline stage as color-coded, collapsible trace cards with detailed goal/input/expected/actual/output annotations. |

### 1.2 What This System IS NOT

- It does NOT execute real device configuration — the EXECUTE stage logs the dispatch plan but does not connect to physical hardware.
- It does NOT manage a resource inventory database — it constructs network element state from the knowledge base and the orchestration plan.
- It does NOT handle CRM integration or TMF622 Product Order decomposition.
- It does NOT perform real-time network monitoring, alarm correlation, or service assurance.
- It is a Proof of Concept demonstrating the pipeline concept, not a production deployment.

---

## 2. FUNCTIONAL REQUIREMENTS

### 2.1 Ingress: Request Acceptance

The system MUST accept requests at a single HTTP endpoint. The request body is a JSON object with a single field named `"prompt"` containing the full request text.

The `prompt` value can be one of three formats:

**Format A — TMF640 Service Activation JSON:**
```json
{
  "serviceId": "MSISDN-447700123456",
  "action": "activate",
  "characteristic": [
    {"name": "customerSegment", "value": "retail"},
    {"name": "slaTier", "value": "gold"},
    {"name": "msisdn", "value": "447700123456"},
    ...
  ]
}
```

**Format B — TMF641 Service Order JSON:**
```json
{
  "externalId": "CRM-98765",
  "category": "Broadband",
  "action": "add",
  "characteristic": [...]
}
```

**Format C — Unstructured Natural Language Text:**
```
activate new mobile voice service for retail customer with gold SLA:
MSISDN 447700123456, IMSI 234151234567890, enable VoLTE with EVS codec,
international roaming WorldZone1...
```

### 2.2 Format Detection (STAGE 0)

The system MUST inspect the first character of the prompt:
- If the prompt starts with `{`, classify as structured JSON (format = `"tmf640"`).
- Otherwise, classify as unstructured text (format = `"unstructured"`).
- If classified as JSON but `json.loads()` / equivalent parsing fails, return an immediate error response with status `"error"` and a trace step indicating "JSON Parse Error". Do NOT proceed to further stages.

### 2.3 Sensitive Data Masking (STAGE 1)

Before any cloud AI call, the system MUST replace all phone numbers and IP addresses with anonymous tokens.

**Phone number pattern:** 5 to 15 consecutive digits, optionally with a leading `+`.

**IPv4 address pattern:** Four octets (1-3 digits each) separated by dots, bounded by word boundaries.

**Token format:** `VAR_MSISDN_N` for phone numbers, `VAR_IP_N` for IP addresses, where N is a monotonically incrementing counter.

**Bidirectional mapping:** Create a dictionary that maps both `token → real_value` and `real_value → token`. The same real value encountered multiple times MUST receive the same token (de-duplication).

**Critical constraint:** The token-to-real mapping MUST exist ONLY in the local process memory. It MUST NOT be written to disk, persisted to a database, included in any log message, or transmitted over the network. It exists solely for the reverse-hydration step later in the pipeline.

### 2.4 Service Type Detection

The system MUST classify the request into exactly one of four service domains using keyword heuristics on the lowercased text:

| Service Domain | Detection Keywords |
|---------------|-------------------|
| `"mobile"` | mobile, msisdn, sim, activate, voice, sms |
| `"l3vpn"` | l3vpn, mpls, vpn, bgp, vrf (must NOT contain "sd") |
| `"sdwan"` | sd-wan, sdwan, sd wan |
| `"broadband"` | broadband, ftth, fiber, ont, olt |

If no keywords match, default to `"mobile"`.

### 2.5 Characteristic Extraction

**From JSON requests:** Iterate over the `characteristic` array. For each entry, extract `name` (or `key`) and `value`. Build two dictionaries:
- `all_chars`: Contains ALL characteristics including instance identifiers (msisdn, imsi, pe_ip, hostname, etc.)
- `chars`: Contains only service-defining characteristics, EXCLUDING instance identifiers.

**Instance identifiers** are: `msisdn`, `imsi`, `imei`, `pe_ip`, `hostname`, `serviceid`, `serial`, `loopback`, `management_ip`.

**From unstructured requests:** Since there is no structured characteristic array, use a hash of the masked text as a characteristic key so that different intents produce different cache keys. Also populate `all_chars` by scanning the token map for the first MSISDN token to anchor subscriber identity.

### 2.6 Subscriber Identity Resolution

Extract a stable identifier for the subscriber:
1. If JSON: use `data["serviceId"]` or `data["externalId"]`.
2. If those are absent, check `all_chars` for `"msisdn"` and return `"MSISDN-{value}"`.
3. If no MSISDN exists, compute `SHA-256(prompt)` and return `"SUB-{first 12 hex chars uppercase}"`.

### 2.7 Pattern Store (STAGE 2 — CACHE)

#### 2.7.1 Pattern Node Structure

A pattern is a data object with these fields:
- `id`: unique string identifier (e.g., `pat:mobile:abc123def456`)
- `service_type`: one of `"mobile"`, `"l3vpn"`, `"sdwan"`, `"broadband"`
- `label`: human-readable label like `"mobile | retail/gold"`
- `characteristics`: dictionary of service-defining characteristics (excludes instance IDs)
- `triples`: list of 3-element arrays `[subject, predicate, object]` representing RDF-like assertions
- `resources`: list of resource objects, each with `name`, `workflow`, `role`, and `attributes` dictionary
- `confidence`: float from 0.0 to 0.98
- `use_count`: integer tracking how many times this pattern matched
- `created_at`: ISO 8601 timestamp
- `last_used`: ISO 8601 timestamp
- `source`: `"auto"` (learned from LLM), `"teach"` (manually injected), or `"kb"` (seeded from knowledge base)

#### 2.7.2 Pattern Matching Algorithm

1. Retrieve all pattern IDs for the detected service type from an index.
2. For each candidate pattern, compute a Jaccard similarity score between the pattern's characteristics and the request's service-defining characteristics.
3. The score is: `|intersection| / |union|` where intersection counts keys that exist in both sets AND have identical values (compared as strings), and union is the total distinct keys across both sets.
4. If the pattern has empty characteristics (KB-seeded wildcard), assign a fixed score of 0.25.
5. If the request has no service-defining characteristics, assign a score of 1.0 (match anything).
6. Select the candidate with the highest score (ties broken by highest confidence).
7. If no candidate scores above 0, return a MISS.

#### 2.7.3 Cache HIT Behavior

When a pattern matches:
1. Increment the pattern's `use_count`.
2. Boost its confidence: `+0.05` if below 0.9, `+0.005` if between 0.9 and 0.98 (diminishing returns). Cap at 0.98.
3. Update `last_used` timestamp.
4. Build an orchestration plan from the pattern's resources: extract `workflow` names, `attributes` as parameters, and `name` values as devices.
5. Cascade the current request's characteristics (`all_chars`) into the plan parameters, overwriting any matching keys. This ensures the plan reflects the current request's values, not stale values from a previous subscriber. Skip values starting with `"default_"` or `"<"`.
6. Set `llm_used = false`.
7. Build a detailed match comparison structure showing which keys matched, which mismatched, and which were extra.

#### 2.7.4 Cache MISS Behavior

When no pattern matches:
1. Build a detailed miss structure showing total patterns in store and patterns for this service type.
2. Set `llm_used = true` and `plan = null`.
3. The LLM stage will generate the plan, and a subsequent WRITE-THROUGH stage will learn the new pattern.

#### 2.7.5 Pattern Learning

When creating a new pattern from a cache miss:
1. Derive service-defining characteristics by filtering out instance identifiers from the characteristics dictionary.
2. Generate a pattern ID from `"pat:{service_type}:" + SHA-256(sorted characteristics JSON)[:12]`.
3. Build RDF triples from the orchestration plan:
   - A `rdf:type` triple mapping the pattern to a service type URI.
   - One `orch:has{key}` triple per service-defining characteristic.
   - One `orch:requiresResource` triple per device.
   - One `orch:provisionedBy` triple per resource-to-workflow mapping.
   - One `orch:hasAttribute` triple per resource attribute.
4. Build resource entries by matching device names against the knowledge base to infer attribute names and roles. Populate attribute values from plan params, falling back to `"<attribute_name>"` placeholders when values are unknown.
5. Set initial confidence to 0.30, `use_count` to 1, `source` to `"auto"`.
6. Persist the new pattern and update the service-type index.

#### 2.7.6 Pattern Teaching (Manual Injection)

The system MUST provide an API endpoint for manually teaching patterns. A taught pattern:
1. Receives a list of RDF triples from the request.
2. Extracts characteristics from triples with `orch:has*` predicates (excluding `orch:hasResource`).
3. Extracts service type from `rdf:type` triples (normalizing e.g., `MobileVoice` → `mobile`).
4. Is created with confidence 0.90, `source` `"teach"`.
5. Overrides any auto-learned pattern for the same characteristics.

#### 2.7.7 Pattern Index

Maintain a service-type index: a dictionary mapping each service type to a list of pattern IDs. This index must be persisted alongside the pattern data.

#### 2.7.8 KB Pattern Seeding

On system startup, the knowledge base service definitions MUST be used to pre-populate the pattern store:
1. For each service type, use the KB's required resources to build a skeleton plan with device names, workflow mappings, and attribute placeholders (`"<attribute_name>"`).
2. Learn this plan as a KB-seeded pattern with empty characteristics (matches any request at 0.25 confidence).
3. This ensures even the first-ever request for a service type hits the cache and receives KB-correct attribute names.

### 2.8 Knowledge Base Context Loading (STAGE 3 — RAG)

For the detected service type, load structured domain knowledge:
1. From a domain ontology document, extract the Service Taxonomy and Resource Taxonomy sections.
2. From a standards reference document, extract lines mentioning the service type, mobile, voice, 3GPP, or related keywords.
3. From the KB service resource definitions, extract: domain name, all required network element types with their roles and attributes, and the service lifecycle.
4. Assemble these into a context string for LLM prompt injection.

### 2.9 LLM Plan Generation (STAGE 4)

This stage runs ONLY if `llm_used = true` (cache miss).

1. Construct a prompt containing:
   - Domain knowledge context (truncated to ~4000 characters).
   - The masked request text (truncated to ~2000 characters).
   - Instructions to return ONLY valid JSON with the structure `{"workflows": [...], "params": {...}, "devices": [...]}`.
   - Instructions to use the masked tokens as-is without inventing real values.

2. Call the cloud LLM (Deepseek or equivalent) with this prompt. Use a timeout of ~90 seconds.

3. Parse the response as JSON. If JSON parsing fails, attempt regex extraction of the first JSON block (`/\{[\s\S]*\}/`). If that also fails, fall back to a KB-derived plan.

4. If the LLM does not respond (timeout, error, empty), use a KB-derived fallback plan built from the service type's required resources: each resource type becomes a device name (replacing `/` with `-`), each mapped to a workflow name, with all KB-defined attributes as `"<attribute_name>"` placeholders.

5. On cache HIT, skip this stage entirely and emit a trace step indicating "LLM Skipped (Cache Hit)".

### 2.10 Parameter Flattening

LLMs sometimes produce nested parameters keyed by workflow name:
```json
{"params": {"HLR_Provisioning": {"msisdn": "...", "imsi": "..."}, "IMS_Registration": {...}}}
```

The system MUST flatten this into a single-level dictionary:
```json
{"params": {"msisdn": "...", "imsi": "...", "codec_profile": "..."}}
```

This operation must be idempotent — if parameters are already flat, return unchanged.

### 2.11 Token Hydration (STAGE 5)

Reverse the masking by string-replacing every `VAR_*` token in the plan with its original real value using the local token map. After hydration:
- If the request was unstructured, harvest real characteristics from the now-hydrated plan parameters and add them to `all_chars` (skip values starting with `"default_"`).

### 2.12 Subscriber Advisory Lock (STAGE 6)

Before modifying any subscriber service model, acquire an exclusive advisory lock:

1. Lock key format: `lock:sub:{subscriber_id}`.
2. Lock value: `{worker_id, acquired_at_timestamp}`.
3. TTL: 30 seconds (auto-expires to prevent dead workers holding locks forever).
4. Acquisition: non-blocking with retry. Poll every 100ms for up to 50 attempts (5 seconds total).
5. Re-entrancy: if the lock is already held by the same worker_id, return true immediately.
6. Expired lock stealing: if `now - acquired_at > 30s`, the lock is considered abandoned and may be stolen.
7. If the lock cannot be acquired within the retry budget, set the job status to `"blocked"`, add an error trace step, and abort.

### 2.13 Characteristic Merge (STAGE 7)

Within the lock-protected critical section, cascade request characteristics into the plan parameters:

1. Always cascade all entries from `all_chars` into the plan params, skipping values starting with `"default_"` or `"<"`.
2. If a previous service model exists for this subscriber:
   - For any characteristic present in the previous model but NOT in the current request or plan params, copy it over (gap-filling). Skip `"default_"` values.
3. Emit a trace step indicating how many characteristics were merged from the request and how many gaps were filled from the previous model.

### 2.14 Pattern Write-Through (STAGE 6a)

If `llm_used = true`, learn a new pattern from the orchestration plan (see Pattern Learning above). If `llm_used = false`, log that the pattern was reinforced by the cache hit.

### 2.15 Security Validation (STAGE 8)

Before any execution, scan the concatenation of `json.dumps(plan) + masked_text` (lowercased) for destructive keywords:

**Blocked keywords:** `erase`, `reload`, `format`, `shutdown`, `no switchport`, `write erase`, `delete startup-config`, `boot system flash`.

If ANY keyword is found:
1. Add a trace step with status `"blocked"`, color `"red"`, detailing which keywords were detected.
2. Set the job status to `"blocked"`.
3. Abort immediately — do NOT execute, do NOT touch any devices.
4. This validates AI-generated plans as untrusted payloads.

If no keywords are found, emit a "Security Gateway — PASSED" trace step.

### 2.16 Execution (STAGE 9)

Log the workflows and devices from the plan as if dispatching them. In the PoC, no actual device commands are sent. The trace step should list the workflow count and device names.

### 2.17 Network Element Construction (STAGE 11 — VERIFY)

Build detailed network element objects from the plan and KB:
1. For each device in the plan, match it against the KB's required resources using substring matching on the device name.
2. For each matched KB resource, infer attributes: check plan params, then `all_chars`, then `chars`, then the previous model's network element attributes, and finally fall back to `"default_{attribute_name}"`.
3. Set status to `"Configured"` for KB-matched resources.
4. Each network element object contains: `name`, `type`, `workflow`, `role`, and `attributes` dictionary.

### 2.18 Service Model Persistence

#### 2.18.1 Service Model Structure

A service model represents a subscriber's provisioned state:
```json
{
  "subscriber_id": "MSISDN-447700123456",
  "service_type": "mobile",
  "characteristics": {"msisdn": "447700123456", "imsi": "234151234567890", ...},
  "network_elements": [
    {"name": "HLR-HSS", "type": "HLR/HSS", "attributes": {"msisdn": "...", ...}},
    ...
  ],
  "version": 3,
  "last_updated": "2026-06-22T12:00:00"
}
```

#### 2.18.2 Build Model

Merge NE attributes into the top-level characteristics (excluding `"status"` and `"default_"`/`"<"` values) so the MERGE stage has complete context for gap-filling.

#### 2.18.3 Compute Diff

Compare the incoming characteristics and network elements against the previous model:
1. For characteristics: detect changed values and removed keys. Normalize NE names by stripping suffixes (`/HSS`, `/PCF`, `/MME`) for fuzzy matching.
2. For network elements: compare attributes per device. An attribute is "changed" if the previous value differs from the current value (compared as strings).
3. Return a diff structure: `{hasPrevious, isFirstRun, hasChanges, changedAttributes, networkElementDiffs}`.

#### 2.18.4 Save Model

Increment the version number, set `last_updated` to the current ISO 8601 timestamp, and persist.

#### 2.18.5 Runtime Corruption Detection

On every model read, check for corruption:
- Count characteristics with values starting with `"default_"`.
- Count characteristics with values starting with `"<"` (unresolved placeholders).
- Count network element attributes with values starting with `"default_"`.
- If the model is partially corrupt (has at least 3 real NE attributes and not all characteristics are corrupt): strip corrupted characteristics, log a warning, and return the salvaged model.
- If fully corrupt: delete the model entry and return null, forcing the pipeline to treat this as a fresh provisioning.

### 2.19 Lifecycle Notifications (STAGE 10)

Walk the KB-defined lifecycle for the service type (e.g., `"DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE"`):

1. For each state EXCEPT the last: emit a ServiceOrderMilestoneEvent with:
   - `eventType`: `"ServiceOrderMilestoneEvent"`
   - Order state remains `"inProgress"`
   - Milestone object with `name`, `status: "achieved"`, and `milestoneDate`
   - A unique `eventId` and shared `correlationId`

2. For the final state (ACTIVE): emit a ServiceOrderStateChangeEvent with:
   - `eventType`: `"ServiceOrderStateChangeEvent"`
   - Order state transitions to `"completed"`
   - `completionDate` set

3. All events share the same `correlationId` for traceability.

4. Buffer all notifications and expose them via an API endpoint.

### 2.20 Final State Assembly

After all stages complete, assemble a final state object containing:
- `serviceId`: a generated service identifier (e.g., `"SVC-XXXXXX"`)
- `state`: `"ACTIVE"`
- `workflowsExecuted`: count from the plan
- `resourcesProvisioned`: count from the plan params
- `networkElements`: the constructed NE list
- `patternId` and `patternConfidence`: from the matched or learned pattern
- `llmUsed`: boolean
- `patternMatch`: the detailed match or miss structure
- `subscriberId` and `subscriberDiff`
- `notificationCount` and `notifications` array

Set the job status to `"completed"` and record the total elapsed time.

---

## 3. PIPELINE STAGE SUMMARY

| # | Stage | Sync/Async | Branch Logic |
|---|-------|-----------|-------------|
| 0 | DETECT | Sync (foreground) | Invalid JSON → return error immediately |
| 1 | MASK | Sync | Always runs |
| 2 | CACHE | Sync | HIT → skip LLM; MISS → flag llm_used=true |
| 3 | RAG | Async (background) | Always runs |
| 4 | LLM | Async | Only if llm_used=true; fallback plan on failure |
| 5 | HYDRATE | Async | Always runs |
| 6 | LOCK | Async | Timeout → set status blocked + abort |
| 7 | MERGE | Async | Within lock; always runs |
| 6a | WRITE-THROUGH | Async | Only if llm_used=true (learn new pattern) |
| 8 | VALIDATE | Async | Blocked keyword → set status blocked + abort |
| 9 | EXECUTE | Async | Always runs (stubbed) |
| 10 | NOTIFY | Async | Always runs |
| 11 | VERIFY | Async | Always runs; saves model + assembles final state |

The sync stages (0-2) run in the API request thread and return immediately with a `"processing"` status. The async stages (3-11) run in a background worker. Clients poll a status endpoint to retrieve the completed result.

---

## 4. KNOWLEDGE BASE CONTENT

The system requires a knowledge base defining the telecom domain. This is NOT code — it is structured reference data that the pipeline reads at runtime.

### 4.1 Service Resource Definitions

For each service type (`mobile`, `l3vpn`, `sdwan`, `broadband`), define:

- `domain`: Human-readable domain name
- `standards`: List of relevant industry standards (3GPP specs, RFCs, MEF standards, TR specs)
- `required_resources`: Array of resource objects, each with:
  - `type`: Network element type (e.g., `"HLR/HSS"`, `"PE Router"`, `"OLT"`)
  - `role`: What this element does
  - `attributes`: Array of attribute names this element requires (e.g., `["msisdn", "imsi", "subscriber_profile"]`)
- `lifecycle`: Arrow-separated state machine string (e.g., `"DESIGNED → FEASIBILITY_CHECKED → ... → ACTIVE"`)

### 4.2 Mobile Voice Resources

| Type | Role | Attributes |
|------|------|-----------|
| HLR/HSS | Subscriber registry | msisdn, imsi, subscriber_profile, roaming_profile |
| IMS-Core | VoLTE/VoWiFi call control | msisdn, imsi, volte_enabled, codec_profile |
| PCRF/PCF | Policy & charging rules | apn, qos_profile, charging_rule, bandwidth_limit |
| SMSC | SMS store-and-forward | msisdn, routing, validity_period |
| MSC/MME | Mobility management | msisdn, imsi, location_area, tac |
| SBC | Session border control | sip_domain, codec_list, media_handling |

Mobile lifecycle: `DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE`

Standards: `3GPP TS 29.002 (MAP/HLR)`, `3GPP TS 23.040 (SMS)`, `GSMA IR.92 (VoLTE)`, `3GPP TS 23.401 (EPC)`, `3GPP TS 29.274 (GTPv2-C)`

### 4.3 L3VPN Resources

| Type | Role | Attributes |
|------|------|-----------|
| PE Router | Provider Edge — VRF termination | vrf_name, rd, rt_import, rt_export, bgp_peer |
| Route Reflector | BGP route distribution | cluster_id, peer_group, asn |
| VRF Instance | Virtual routing table | vrf_name, rd, route_targets, interfaces |
| NMS | Monitoring & assurance | snmp_community, syslog_server, netflow_collector |

Lifecycle: `DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE`

### 4.4 SD-WAN Resources

| Type | Role | Attributes |
|------|------|-----------|
| vCPE/uCPE | Edge device | transport_links, encryption, app_policy, wan_interfaces |
| SD-WAN Controller | Centralized policy & orchestration | policy_set, site_list, template |
| Orchestrator | Zero-touch provisioning | ztp_url, bootstrap_config, license_key |

Lifecycle: `DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE`

### 4.5 Broadband Resources

| Type | Role | Attributes |
|------|------|-----------|
| OLT | Optical line terminal | ont_model, vlan, speed_profile, dba_profile |
| BNG/BRAS | Broadband network gateway | ip_pool, subscriber_profile, qos_policy |
| RADIUS | AAA server | nas_identifier, shared_secret, auth_method |
| EMS | Element management | snmp_community, trap_destinations |

Lifecycle: `DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE`

### 4.6 Workflow Name Mapping

Each network element core type maps to a workflow name:

| NE Core Type | Workflow Name |
|-------------|---------------|
| HLR, HSS | HLR_Provisioning |
| IMS-Core | IMS_Registration |
| PCRF, PCF | APN_Configuration |
| SMSC | Charging_Rule_Setup |
| MSC, MME | Mobility_Configuration |
| SBC | SBC_Configuration |
| PE Router | PE_Configuration |
| Route Reflector | BGP_Peering |
| VRF Instance | VRF_Allocation |
| NMS | Monitoring_Setup |
| vCPE | CPE_Deployment |
| SD-WAN Controller | Controller_Setup |
| Orchestrator | ZTP_Bootstrap |
| OLT | ONT_Provisioning |
| BNG | IP_Pool_Allocation |
| RADIUS | AAA_Configuration |
| EMS | EMS_Setup |

### 4.7 Domain Ontology

The knowledge base should include a core ontology document covering:
- Domain entity hierarchy (Customer → ProductOrder → Service → Resource → PhysicalResource/LogicalResource/VirtualResource)
- Key relationship types (instantiates, composes, realised_by, hosts, connects_to, depends_on, provisioned_by)
- Service lifecycle state machine
- Resource lifecycle state machine
- Service taxonomy (L3VPN, SD-WAN, Internet Access, Cloud Connect, Voice/UC, Mobile Backhaul, Security, Transport/Wavelength)
- Resource taxonomy down to network level
- Workflow categories (Fulfillment, Assurance, Provisioning, Discovery, Capacity, Modification, Termination)
- Descriptor format references (TOSCA, YANG, NSD, VNFD, Helm, Ansible)

### 4.8 Standards Reference

Include an index of industry standards bodies and key specifications:
- TM Forum (eTOM, SID, TAM, Open APIs)
- MEF (LSO, Network Resource Management, SD-WAN attributes)
- ETSI NFV (MANO, SOL specifications)
- IETF (YANG, NETCONF, RESTCONF, L3VPN/L2VPN YANG models)
- 3GPP (5G MANO, Network Resource Model)
- ONF (TAPI, CIM)
- OASIS TOSCA (NFV profile)

### 4.9 TMF Notification Schemas

Document the TMF641 v4.1.0 notification schemas:
- ServiceOrderStateChangeEvent structure (eventId, eventTime, eventType, correlationId, event.serviceOrder with id, href, state, externalId, category, completionDate)
- ServiceOrderMilestone structure (id, name, description, message, milestoneDate, status)
- State enumerations for ServiceOrderStateType, ServiceOrderItemStateType, ServiceStateType
- Mapping from KB lifecycle states to TMF events (intermediate → milestone + inProgress, final → stateChange + completed)

---

## 5. API SPECIFICATION

### 5.1 Request Processing

**POST /api/process**

Request body: `{"prompt": "<request text>"}`

Response (immediate, synchronous):
```json
{
  "order_id": "PO-XXXXXXXX",
  "format": "tmf640" | "unstructured",
  "status": "processing",
  "trace": [ /* stages 0-2 completed */ ],
  "total_ms": 12,
  "started_at": "2026-06-22T12:00:00"
}
```

**GET /api/process/{order_id}**

Response (polling, returns current state):
```json
{
  "order_id": "PO-XXXXXXXX",
  "format": "tmf640",
  "status": "processing" | "completed" | "blocked" | "error",
  "trace": [ /* all completed stages */ ],
  "total_ms": 35000,
  "final_state": { /* null if still processing */ }
}
```

### 5.2 Pattern Management

**GET /api/patterns** — List all learned patterns with metadata (id, service_type, label, confidence, use_count, triples_count, source, last_used). Sorted by confidence descending, use_count descending.

**GET /api/patterns/{pattern_id}** — Full pattern details including all triples and resources. Returns 404 if not found.

**POST /api/patterns/teach** — Manual pattern injection. Request body: `{"triples": [[subject, predicate, object], ...]}`. Returns the created pattern. Returns 400 if triples array is empty.

### 5.3 Sample Requests

**GET /api/samples** — Return an array of sample request payloads for demo purposes:
1. TMF640 — Activate Mobile Voice (Gold)
2. TMF640 — Activate Mobile Data (Platinum)
3. Unstructured — Mobile Voice Activation
4. TMF640 — Activate L3VPN (Enterprise Platinum)
5. TMF640 — Activate SD-WAN (Dual Transport)
6. TMF641 — ServiceOrder Broadband (FTTH Silver)
7. Security Test — Blocked Keyword

Each sample has a `label` and `text` field.

### 5.4 Lock Management

**GET /api/locks/status** — List all active subscriber locks with subscriber ID, worker ID, acquisition time, and age in seconds.

**POST /api/locks/release** — Admin force-release a subscriber lock. Request body: `{"subscriberId": "..."}`. Returns 400 if subscriberId is missing.

### 5.5 Notifications

**GET /api/notifications/{order_id}** — Retrieve TMF lifecycle notifications for a completed order. Returns 404 if order not found. Returns `{"notifications": [], "message": "Pipeline still processing"}` if still in progress.

### 5.6 Health

**GET /health** — Return `{"status": "ok", "cache_size": <int>, "redis_backend": "diskcache"}` (or equivalent for your backend).

### 5.7 Static Files / Frontend

Serve a static HTML frontend at `/`. Serve static assets (CSS, JS, images, fonts) from a `/static/` path.

---

## 6. FRONTEND SPECIFICATION

### 6.1 Layout

A two-panel layout filling the viewport:
- **Left panel** (fixed width ~420px): Service request textarea, Execute/Clear buttons, sample request chips.
- **Right panel** (flexible): Pipeline trace display area.

### 6.2 Header

Fixed header bar with:
- Animated pulsing dot (cyan, 2s pulse animation)
- Title: "Telecom Agentic Orchestration Engine"
- Badge: "PoC Demo"
- Subtitle: "Cache-First · Data-Sovereign · Cloud-Reasoned"

### 6.3 Left Panel Components

**Textarea:** Dark themed, monospace font, minimum 160px height, border highlights cyan on focus. Placeholder text shows example request.

**Execute button:** Primary style (cyan), triggers submission. Disables during processing with "Submitting..." text.

**Clear button:** Secondary style (slate), clears textarea and trace display.

**Sample requests section:** Label "Sample Requests" above a list of clickable chips. Each chip displays the sample label. Clicking populates the textarea. Chips highlight on hover.

### 6.4 Right Panel — Trace Display

**Empty state:** Centered gear icon with "Submit a service request on the left to see the orchestration pipeline."

**Processing state:** Shows a "Submitting — dispatching pipeline..." card with loading animation. Polls `GET /api/process/{order_id}` every 2 seconds for up to 120 attempts. Displays elapsed seconds counter.

**Trace header:** Shows "Pipeline Trace", the order ID, and a status badge.

**Trace steps:** Each pipeline stage renders as a color-coded card with:
- Header row: icon + title + elapsed ms
- Body row (collapsible on header click): Formatted detail text with labeled fields (Goal:, Input:, Expected:, Actual:, Output:)
- Cards animate in with staggered slide-in (80ms delay per card)
- Running stages have a pulsing glow animation
- Completed/blocked stages show appropriate status badges

**Color coding:**

| Color | Stages | Meaning |
|-------|--------|---------|
| Cyan | DETECT, NOTIFY | Detection, notifications |
| Violet | MASK, HYDRATE, MERGE, LOCK | Data sovereignty, parameter operations |
| Green | CACHE (hit), VALIDATE (pass), VERIFY, WRITE-THROUGH | Success, storage |
| Amber | CACHE (miss), EXECUTE | System state transitions |
| Blue | RAG, LLM | Cloud AI, knowledge base |
| Red | VALIDATE (block), ERROR | Security block, failures |

### 6.5 Final Output Sections

When a job completes (`status = "completed"`), display these sections below the trace:

**Notification Timeline:** Horizontal track showing each lifecycle state as a connected dot with state name below. Active/completed dots are green, connectors between them are green. Last dot shows a checkmark icon.

**Pattern Analysis Panel:** Grid showing:
- Confidence score with colored progress bar (green ≥70%, amber 40-69%, red <40%)
- Tag indicating "Cache Hit" or "LLM Learned"
- Pattern ID, match type, comparison logic
- Verification checklist (security, schema, resource binding, LLM reasoning, pattern learning)
- Contextual suggestion based on confidence level

**Final Summary Card:** Green-bordered card showing:
- Service ID, state (ACTIVE), workflow count, resource count
- Subscriber ID with indicator: "First provisioning — model v1 saved" (green) or "UPDATED — N attrs changed, M NEs modified" (amber)

**Network Elements Grid:** Responsive grid of NE cards, each showing:
- Icon (per NE type), name, workflow name
- MODIFIED badge (amber) if this NE has changes from previous model
- Attribute list: key on left, value on right
- Changed attributes show new value (amber) with struck-through old value (red)
- Status attribute with green highlight for active/provisioned/configured states

### 6.6 Zoom Feature

Clicking a step card or NE card opens a full-screen zoom overlay with:
- Dark backdrop with blur
- Enlarged card with larger fonts and padding
- Close on backdrop click or Escape key
- "Click anywhere outside to close · Esc" hint

### 6.7 Theme

- Background: near-black (#020617)
- Font: JetBrains Mono (monospace), loaded from Google Fonts
- No external CSS frameworks — all styles inline
- No JavaScript frameworks — vanilla JS only
- No build step — single self-contained HTML file
- Custom scrollbar styling (dark, thin)

### 6.8 Error States

- **Tunnel/connection error:** Red card showing the error message
- **Timeout (130s):** Red card indicating request timed out
- **Status "blocked":** Trace ends at VALIDATE with red blocked card
- **Status "error":** Trace ends with red error card

---

## 7. CACHE STARTUP INTEGRITY CHECK

On system startup, perform a cross-item integrity scan of all persisted data:

1. **Subscriber models:** Validate each model using the runtime corruption guard. Track MSISDNs to detect duplicates.

2. **Duplicate detection:** If two models share the same real MSISDN, keep the one with the highest version, delete the others.

3. **Pattern index integrity:** For each service type in the index, verify each pattern ID still resolves. Remove stale entries. Delete empty service type keys.

4. **Orphan patterns:** Find patterns stored in the cache but missing from the index. If they pass validation, re-index them.

5. Log all repairs performed. If no issues, log "Cache integrity: OK".

---

## 8. ACCEPTANCE CRITERIA — TEST SCENARIOS

### 8.1 TMF640 JSON — Cache Miss → Full Pipeline

**Given:** A structured JSON request with characteristic array including `customerSegment: "retail"`, `slaTier: "gold"`, `msisdn: "447700123456"`, `imsi: "234151234567890"`, and all 19 mobile characteristics.
**When:** POST to `/api/process`.
**Then:**
- Response status is `"processing"`, format is `"tmf640"`.
- Trace includes DETECT → MASK → CACHE (MISS) → pipeline dispatched.
- After polling, final status is `"completed"`.
- `llmUsed` is `true`.
- `final_state.state` is `"ACTIVE"`.
- 6 network elements are present (HLR/HSS, IMS-Core, PCRF/PCF, SMSC, MSC/MME, SBC).
- Each NE has correct KB-derived attributes.
- Subscriber diff shows `isFirstRun: true`.
- 6 lifecycle notifications are emitted (5 milestone + 1 state change).
- A new pattern is learned (confidence 0.30, source "auto").

### 8.2 TMF640 JSON — Cache HIT

**Given:** The same request as 8.1, submitted a second time after the first completed.
**When:** POST to `/api/process`.
**Then:**
- DETECT → MASK → CACHE (HIT).
- Pattern confidence increases (from 0.30 to 0.35).
- `llmUsed` is `false`.
- LLM stage trace shows "Skipped (Cache Hit)".
- Subscriber diff shows `hasPrevious: true`, `isFirstRun: false`.
- If characteristics unchanged: `hasChanges: false`.

### 8.3 Unstructured Text

**Given:** Natural language prompt: "activate new mobile voice service for retail customer with gold SLA: MSISDN 447700123456, IMSI 234151234567890, enable VoLTE with EVS codec..."
**When:** POST to `/api/process`.
**Then:**
- Format is `"unstructured"`.
- MASK stage tokenizes the MSISDN and IMSI.
- Cache stage misses (text_hash won't match).
- LLM is invoked with MASKED text — Deepseek never sees real identifiers.
- HYDRATE restores real values from the local token map.
- All subsequent stages proceed identically to the structured path.
- A new pattern is learned.

### 8.4 Security Block

**Given:** A prompt containing a blocked keyword: "activate mobile service 447700123456 and shutdown all interfaces".
**When:** POST to `/api/process`.
**Then:**
- DETECT → MASK → CACHE → RAG → LLM → HYDRATE → LOCK → MERGE → VALIDATE.
- VALIDATE stage status is `"blocked"`, color is `"red"`.
- Job status is `"blocked"`.
- Trace ends at VALIDATE — no EXECUTE, NOTIFY, or VERIFY stages.
- No devices touched, no MCP calls made.
- No service model is saved.

### 8.5 Pattern Store Query

**Given:** The system has been running and several patterns have been learned.
**When:** GET `/api/patterns`.
**Then:**
- Returns array of patterns sorted by confidence descending.
- Each pattern includes id, service_type, label, confidence, use_count, triples_count, source, last_used.

### 8.6 Pattern Detail

**Given:** A known pattern ID.
**When:** GET `/api/patterns/{pattern_id}`.
**Then:**
- Returns full pattern with triples array and resources array.
- Triples are 3-element arrays [subject, predicate, object].
- Resources include name, workflow, role, and attributes.

### 8.7 Pattern Teaching

**Given:** Manual triples for a new pattern.
**When:** POST to `/api/patterns/teach` with `{"triples": [...]}`.
**Then:**
- A new pattern is created with confidence 0.90, source "teach".
- Returns the created pattern.
- Return 400 if triples array is empty.

### 8.8 Notifications Retrieval

**Given:** A completed order ID.
**When:** GET `/api/notifications/{order_id}`.
**Then:**
- Returns array of TMF641 notification events.
- Each event has eventId, eventType, eventTime, correlationId, and event.serviceOrder.
- Milestone events have milestone array inside serviceOrder.
- State change events have state and completionDate.

### 8.9 Lock Management

**Given:** A pipeline is processing a subscriber.
**When:** GET `/api/locks/status`.
**Then:**
- Returns active locks with subscriberId, workerId, acquiredAt, and ageSeconds.
- POST `/api/locks/release` with `{"subscriberId": "..."}` releases the lock.

### 8.10 Health Check

**Given:** The server is running.
**When:** GET `/health`.
**Then:**
- Returns `{"status": "ok"}`.
- Includes cache size or equivalent backend info.

### 8.11 JSON Parse Error

**Given:** A prompt starting with `{` but containing malformed JSON.
**When:** POST to `/api/process`.
**Then:**
- Returns immediately with status `"error"`, format `"invalid"`.
- Trace has a single DETECT step with status `"error"`.
- No background processing is spawned.

### 8.12 Lock Contention

**Given:** Two concurrent requests for the same subscriber_id.
**When:** Both are processed simultaneously.
**Then:**
- The first acquires the lock and proceeds.
- The second times out after 5 seconds (50 retries × 100ms).
- The second sets status to `"blocked"` with an error trace step about lock timeout.
- The subscriber model is not corrupted by concurrent modification.

### 8.13 Startup Cache Repair

**Given:** The cache contains a corrupted subscriber model (all characteristics are `default_*` values).
**When:** The system starts up.
**Then:**
- The startup integrity check runs.
- The corrupted model is deleted.
- A log message indicates the deletion.
- A subsequent request for that subscriber treats it as a fresh provisioning.

### 8.14 KB Pattern Seeding

**Given:** A fresh system with an empty pattern store.
**When:** The system starts up.
**Then:**
- 4 KB-seeded patterns are created (mobile, l3vpn, sdwan, broadband).
- Each has confidence 0.25, source "kb".
- Each has empty characteristics (wildcard — matches any request).
- GET `/api/patterns` shows these 4 patterns.

---

## 9. DESIGN CONSTRAINTS & PHILOSOPHY

### 9.1 Data Sovereignty Is Non-Negotiable

The token map MUST exist only in process memory. It MUST NOT be:
- Written to any persistent store
- Included in any log statement
- Transmitted to any external service
- Serialized in any API response
- Accessible after the pipeline completes and the request object is garbage-collected

### 9.2 AI Outputs Are Untrusted

Every LLM-generated plan MUST pass through the validation gateway. The system treats the LLM as an untrusted component that may hallucinate destructive commands.

### 9.3 KB Is the Single Source of Truth

No network element type, attribute name, or workflow mapping should be hardcoded. Everything derives from the knowledge base definitions. If you add a new service type by adding its definition to the KB, the system should support it without code changes.

### 9.4 Cache-First Architecture

The pattern store is the primary decision engine. The LLM is a fallback for novel situations. The system should maximize cache hits to minimize cloud AI latency and cost.

### 9.5 Concurrent Safety

Subscriber model modifications are protected by per-subscriber advisory locks. The lock TTL prevents dead workers from holding locks forever. The lock is re-entrant within the same worker.

### 9.6 Self-Healing Data

The system should detect and recover from data corruption at runtime. Corrupted subscriber models are automatically repaired (partial) or deleted (full). Corrupted patterns are deleted and their index entries removed.

---

## 10. IMPLEMENTATION GUIDANCE

This section is deliberately non-prescriptive. You may implement the system using any:

- **Programming language:** Python, Go, Node.js, Rust, etc.
- **Web framework:** FastAPI, Flask, Express, Gin, Actix, etc.
- **Storage backend:** SQLite, diskcache, Redis, PostgreSQL, LevelDB, etc.
- **LLM integration:** Direct API calls, CLI subprocess, SDK library
- **Frontend:** Vanilla HTML/CSS/JS, React, Vue, Svelte, HTMX, etc.
- **Message queue:** Thread pool, Redis, RabbitMQ, in-process channels

The ONLY requirement is that the system produces identical observable behavior to the specification above. All acceptance criteria in Section 8 must pass.

### 10.1 Suggested Architecture (Not Required)

A common approach that satisfies all requirements:
- **Language:** Python 3.10+ with type hints
- **Framework:** FastAPI (async support, automatic OpenAPI docs, Pydantic validation)
- **Storage:** diskcache (Redis-compatible API over SQLite — zero system dependencies)
- **Frontend:** Single HTML file with vanilla JavaScript (no build step, no npm)
- **Async:** ThreadPoolExecutor with background task submission
- **LLM:** Subprocess call or HTTP client to cloud AI API

### 10.2 Minimum Viable Dependencies

- HTTP server framework
- JSON parser
- Regular expression engine
- SHA-256 hash function
- Key-value store (persistent)
- Thread/async execution capability
- HTTP client for LLM API calls

---

> **End of Specification.** If you build a system that passes all 14 acceptance criteria in Section 8, you have successfully replicated the Telecom Agentic Orchestration Engine Proof of Concept.
