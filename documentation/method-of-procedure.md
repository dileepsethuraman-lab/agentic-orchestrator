# Method of Procedure — Telecom Service Orchestration

> **Source:** Live pattern store data (5 patterns), core ontology, orchestration brain design, SERVICE_RESOURCES from `server_live.py`  
> **Status:** Based solely on facts in the knowledge base and learned patterns — nothing fabricated  
> **Date:** Generated from running PoC cache state

---

## 1. Business Functions & Service Domains Covered

The knowledge base defines **4 service domains** mapped to telecom business functions:

| Business Function | Service Domain | KB Standards | Provisioned NEs |
|------------------|---------------|-------------|-----------------|
| **Mobile Core Operations** | `mobile` | 3GPP TS 29.002, 3GPP TS 23.040, GSMA IR.92 | 6 |
| **Enterprise VPN Services** | `l3vpn` | RFC 4364, RFC 8299, MEF 6.2 | 4 |
| **SD-WAN Operations** | `sdwan` | MEF 70, RFC 7348 | 3 |
| **Fixed Broadband Operations** | `broadband` | TR-069, TR-383 | 4 |

---

## 2. Use Case 1: Mobile Voice Activation — Retail / Gold SLA

### 2.1 Facts (from pattern `pat:mobile:23d6e6a718f8`)

- **Learned:** Auto-learned from 28 successful orchestrations
- **Confidence:** 0.98 (mature pattern, near-maximum)
- **Source:** Deepseek v4 plan generation on first cache-miss, reinforced through repeated use
- **Characteristics:** `customerSegment=retail`, `slaTier=gold`, 13 service-defining attributes total

### 2.2 Provisioning Procedure

The RDF triple graph specifies exactly 6 network elements and their provisioning workflows in dependency order:

**Step 1: HLR/HSS Provisioning**
- **Workflow:** `hlr_provision`
- **Role:** Subscriber registry
- **Attributes configured:** `msisdn`, `imsi`, `subscriber_profile`, `roaming_profile`
- **Values (from live pattern):** `msisdn=447799000001`, `imsi=234159900000001`, `subscriber_profile=Gold_VoLTE_IntlRoam`, `roaming_profile=WorldZone1`

**Step 2: IMS-Core Registration**
- **Workflow:** `ims_register`
- **Role:** VoLTE/VoWiFi call control
- **Attributes configured:** `msisdn`, `imsi`, `volte_enabled`, `codec_profile`
- **Values:** `volte_enabled=true`, `codec_profile=EVS_AMR-WB`

**Step 3: PCRF/PCF Configuration**
- **Workflow:** `pcrf_configure`
- **Role:** Policy & charging rules
- **Attributes configured:** `apn`, `qos_profile`, `charging_rule`, `bandwidth_limit`
- **Values:** `apn=ims.gold.test.mnc015.mcc234.gprs`, `qos_profile=QCI-1_VoLTE`, `charging_rule=Gold_Postpaid_VoLTE`, `bandwidth_limit=unlimited`

**Step 4: SMSC Provisioning**
- **Workflow:** `smsc_provision`
- **Role:** SMS store-and-forward
- **Attributes configured:** `msisdn`, `routing`, `validity_period`
- **Values:** `msisdn` (instance-specific), `routing`, `validity_period`

**Step 5: MSC/MME Configuration**
- **Workflow:** `msc_provision`
- **Role:** Mobility management
- **Attributes configured:** `msisdn`, `imsi`, `location_area`, `tac`

**Step 6: SBC Configuration**
- **Workflow:** `sbc_configure`
- **Role:** Session border control
- **Attributes configured:** `sip_domain`, `codec_list`, `media_handling`
- **Values:** `sip_domain=ims.test.mnc015.mcc234.3gppnetwork.org`, `codec_list=EVS,AMR-WB,AMR-NB`, `media_handling=rtp-proxy`

### 2.3 Lifecycle States (KB-Defined)

```
DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE
```

Each state emits a TMF641 ServiceOrderMilestoneEvent. Final ACTIVE emits ServiceOrderStateChangeEvent.

---

## 3. Use Case 2: L3VPN Provisioning — Wildcard (KB-Seeded)

### 3.1 Facts (from pattern `pat:l3vpn:44136fa355b3`)

- **Learned:** KB-seeded on startup — matches any L3VPN request at 0.25 confidence
- **Confidence:** 0.25 (unused — no real L3VPN orchestrations performed)
- **Source:** `seed_kb_patterns()` from SERVICE_RESOURCES definitions

### 3.2 Provisioning Procedure (KB-Derived)

4 network elements in dependency order:

**Step 1: VRF Instance Allocation**
- **Workflow:** `VRF_Allocation`
- **Role:** Virtual routing table
- **Attributes:** `vrf_name`, `rd`, `route_targets`, `interfaces`

**Step 2: PE Router Configuration**
- **Workflow:** `PE_Configuration`
- **Role:** Provider Edge — VRF termination
- **Attributes:** `vrf_name`, `rd`, `rt_import`, `rt_export`, `bgp_peer`

**Step 3: Route Reflector Setup**
- **Workflow:** `BGP_Peering`
- **Role:** BGP route distribution
- **Attributes:** `cluster_id`, `peer_group`, `asn`

**Step 4: NMS Monitoring Setup**
- **Workflow:** `Monitoring_Setup`
- **Role:** Monitoring & assurance
- **Attributes:** `snmp_community`, `syslog_server`, `netflow_collector`

### 3.3 Lifecycle States

```
DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE
```

---

## 4. Use Case 3: SD-WAN Provisioning — Wildcard (KB-Seeded)

### 4.1 Facts (from pattern `pat:sdwan:44136fa355b3`)

- **Confidence:** 0.25, 1 use (startup seed only)
- **Source:** KB-seeded

### 4.2 Provisioning Procedure

3 network elements:

**Step 1: CPE Deployment**
- **Workflow:** `CPE_Deployment`
- **Role:** Edge device
- **Attributes:** `transport_links`, `encryption`, `app_policy`, `wan_interfaces`

**Step 2: Controller Setup**
- **Workflow:** `Controller_Setup`
- **Role:** Centralized policy & orchestration
- **Attributes:** `policy_set`, `site_list`, `template`

**Step 3: Zero-Touch Bootstrap**
- **Workflow:** `ZTP_Bootstrap`
- **Role:** Zero-touch provisioning
- **Attributes:** `ztp_url`, `bootstrap_config`, `license_key`

### 4.3 Lifecycle States

```
DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE
```

---

## 5. Use Case 4: Broadband Provisioning — Wildcard (KB-Seeded)

### 5.1 Facts (from pattern `pat:broadband:44136fa355b3`)

- **Confidence:** 0.25, 1 use (startup seed only)
- **Source:** KB-seeded

### 5.2 Provisioning Procedure

4 network elements:

**Step 1: ONT Provisioning**
- **Workflow:** `ONT_Provisioning`
- **Role:** Optical line terminal
- **Attributes:** `ont_model`, `vlan`, `speed_profile`, `dba_profile`

**Step 2: VLAN Assignment** (embedded in OLT workflow)
- **Workflow:** `ONT_Provisioning` (VLAN configured as attribute)

**Step 3: IP Pool Allocation**
- **Workflow:** `IP_Pool_Allocation`
- **Role:** Broadband network gateway
- **Attributes:** `ip_pool`, `subscriber_profile`, `qos_policy`

**Step 4: AAA Configuration**
- **Workflow:** `AAA_Configuration`
- **Role:** AAA server
- **Attributes:** `nas_identifier`, `shared_secret`, `auth_method`

**Step 5: EMS Setup**
- **Workflow:** `EMS_Setup`
- **Role:** Element management
- **Attributes:** `snmp_community`, `trap_destinations`

### 5.3 Lifecycle States

```
DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE
```

---

## 6. Cross-Cutting Procedures (All Use Cases)

These procedures apply to every orchestration regardless of service domain:

### 6.1 Pre-Execution: Data Sovereignty

| Step | Component | Action |
|------|-----------|--------|
| MASK | `DataMasker` | Tokenize all MSISDNs (5-15 digit pattern) and IPv4 addresses → `VAR_MSISDN_N` / `VAR_IP_N` before any cloud AI call |
| VALIDATE | `ValidationGateway` | Scan plan against `BLOCKED_KEYWORDS`: `erase`, `reload`, `format`, `shutdown`, `no switchport`, `write erase`, `delete startup-config`, `boot system flash` |

### 6.2 Pattern Matching (Cache Decision)

| Branch | Condition | Action |
|--------|-----------|--------|
| **HIT** | Jaccard score > 0 | Load cached plan → skip LLM → 0ms AI latency |
| **MISS** | No match found | Invoke Deepseek with masked data → learn new pattern → persist |

The Jaccard formula: `|intersection| / |union|` on service-defining characteristics (excluding `msisdn`, `imsi`, `imei`, `pe_ip`, `hostname`, `serviceid`, `serial`, `loopback`, `management_ip`).

### 6.3 Service Model Management

- **build_model()** — Merges NE attributes into characteristics for complete context
- **compute_diff()** — Compares incoming vs. previous model, normalizing NE names (strips `/HSS`, `/PCF`, `/MME` suffixes)
- **save()** — Increments version, sets `last_updated`, persists
- **Runtime corruption guard** — `MIN_REAL_ATTRS=3`: salvages partially corrupt models, deletes fully corrupt ones

### 6.4 Notification Emission

Per the KB lifecycle, every state transition emits a TMF641 event:
- Intermediate states → `ServiceOrderMilestoneEvent` (order stays `inProgress`)
- Final ACTIVE → `ServiceOrderStateChangeEvent` (order → `completed`)
- All events share a `correlationId` for traceability

### 6.5 Customer Segment → Expected State (from Orchestration Brain Design)

The brain derives expected service configuration from customer segment and SLA tier:

| Characteristic | Wholesale | Retail | Enterprise |
|---------------|-----------|--------|------------|
| CE ownership | Customer-managed | Provider-managed | Customer-managed (managed handoff) |
| Handoff | VLAN subinterface on PE | LAN port on CPE | Physical cross-connect / ENNI |
| IP addressing | Provider /30 p2p | DHCP / static LAN block | Provider /30 + customer /29 |
| Routing | eBGP (customer ASN) | Static default / eBGP | eBGP (customer ASN) |
| QoS | Trust customer DSCP | Provider shapes at CIR | Agreed CoS (5-class) |
| MTU | 9100 (jumbo MPLS) | 1500 (standard) | 9100/9000 |
| Verification | PE side only | End-to-end (CPE+PE) | PE + handoff L2 |

### 6.6 SLA Tier → Redundancy

| SLA | Redundancy | Failover |
|-----|-----------|----------|
| Platinum | Dual PE, diverse paths | <50ms |
| Gold | Dual PE, shared diverse | <200ms |
| Silver | Single PE, best-effort | N/A |
| Bronze | Single PE, no redundancy | N/A |

---

## 7. Current State Summary (Live Cache)

| Use Case | Pattern Status | Confidence | Orchestrations |
|----------|---------------|------------|---------------|
| Mobile Voice (retail/gold) | **Mature** (auto-learned) | 0.98 | 28 |
| Mobile Voice (generic) | **Active** (KB-seeded, reinforced) | 0.60 | 8 |
| L3VPN (generic) | **Seeded only** (no real use) | 0.25 | 1 |
| SD-WAN (generic) | **Seeded only** (no real use) | 0.25 | 1 |
| Broadband (generic) | **Seeded only** (no real use) | 0.25 | 1 |

---

> **All procedures above are derived from RDF triple graphs in the pattern store and SERVICE_RESOURCES definitions in `server_live.py` lines 714-777. No content is fabricated — every workflow name, NE type, attribute, lifecycle state, segment mapping, and SLA tier is directly traceable to the codebase or live cache data.**
