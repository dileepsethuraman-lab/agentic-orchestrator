# Pattern Store — How Patterns Are Learned and Used

> **Live data source:** Python PoC cache at `172.16.1.2:8090` (diskcache, SQLite-backed)  
> **Engine:** `PatternEngine` in `poc/server_live.py` (lines 425–661) / `PatternStore.java` in `java-poc/`

---

## 1. Overview

The Pattern Store is the **cache-first decision engine** of the Telecom Orchestrator. Instead of calling the cloud LLM (Deepseek) for every request, the system first queries the pattern store for a matching orchestration pattern. A successful match skips the LLM entirely — providing a **0ms AI-latency fast path**.

Patterns are modeled as **RDF-inspired named graphs of triples** `(subject, predicate, object)`. Each pattern captures:
- **Service-defining characteristics** (customer segment, SLA tier, product type)
- **Required resources** (network elements like HLR, PCRF, PE routers)
- **Workflow mappings** (which provisioning workflow runs against which device)
- **Attribute bindings** (actual configuration values per resource)

---

## 2. Pattern Sources and Confidence Lifecycle

Patterns enter the store through three channels, each with a different initial confidence:

| Source | Code | Initial Confidence | How Created |
|--------|------|-------------------|-------------|
| **KB-seeded** | `"kb"` | 0.25 | Automatically on startup from `SERVICE_RESOURCES` definitions |
| **Auto-learned** | `"auto"` | 0.30 | After a cache miss → LLM generates a plan → plan is persisted |
| **Manually taught** | `"teach"` | 0.90 | Via `POST /api/patterns/teach` with explicit RDF triples |

### Confidence Reinforcement

Every time a pattern matches a request (cache HIT), its confidence increases:

```
PATTERN HIT → use_count++
               if confidence < 0.90:  confidence += 0.05  (cap 0.90)
               if confidence ≥ 0.90:  confidence += 0.005 (cap 0.98)
```

The diminishing returns above 0.90 prevent over-confidence. A mature, frequently-used pattern can reach 0.98 but never 1.0 — there's always room for a better match.

---

## 3. Live Example: Auto-Learned Pattern

The most mature pattern in the current cache is `pat:mobile:23d6e6a718f8`, learned from repeated TMF640 mobile voice activations:

### 3.1 Pattern Identity
```
ID:          pat:mobile:23d6e6a718f8
Service:     mobile
Label:       mobile | retail/gold
Source:      auto
Confidence:  0.98
Use count:   28
Triples:     48
Created:     First request for retail/gold mobile voice
Last used:   2026-06-23T02:42:32Z
```

### 3.2 How It Was Learned

**Step 1 — First request (cache MISS):**
A TMF640 JSON payload arrived with `customerSegment: "retail"`, `slaTier: "gold"`, and 17 mobile characteristics (msisdn, imsi, subscriber_profile, roaming_profile, volte_enabled, codec_profile, apn, qos_profile, charging_rule, bandwidth_limit, routing, validity_period, location_area, tac, sip_domain, codec_list, media_handling).

The Pattern Engine found no matching pattern → flagged `llm_used = true`. Deepseek generated an orchestration plan with 6 devices (HLR/HSS, IMS-Core, PCRF/PCF, SMSC, MSC/MME, SBC) and 6 workflows. After successful validation and verification, the plan was persisted as a new pattern with `confidence = 0.30`, `source = "auto"`.

**Step 2 — Subsequent requests (cache HIT):**
The next 27 identical requests matched this pattern via Jaccard similarity. Each hit incremented `use_count` and boosted confidence:
- Hit 1–12: +0.05 each → 0.90
- Hit 13–27: +0.005 each → 0.98

Now any `mobile + retail + gold` request hits the cache instantly with 0ms LLM latency.

### 3.3 Service-Defining Characteristics

These are the characteristics that define the pattern identity (instance identifiers like `msisdn` and `imsi` are excluded):

```
customerSegment:        retail
slaTier:                gold
subscriber_profile:     Gold_VoLTE_IntlRoam
roaming_profile:        WorldZone1
volte_enabled:          true
codec_profile:          EVS_AMR-WB
apn:                    ims.gold.test.mnc015.mcc234.gprs
qos_profile:            QCI-1_VoLTE
charging_rule:          Gold_Postpaid_VoLTE
bandwidth_limit:        unlimited
sip_domain:             ims.test.mnc015.mcc234.3gppnetwork.org
codec_list:             EVS,AMR-WB,AMR-NB
media_handling:         rtp-proxy
```

### 3.4 RDF Triple Structure (Excerpt)

Each pattern is represented as a set of RDF-like assertions. Here are the first 14 triples:

| Subject | Predicate | Object |
|---------|-----------|--------|
| `pat:mobile:23d6e6a718f8` | `rdf:type` | `service:MobileVoice` |
| `pat:mobile:23d6e6a718f8` | `orch:hascustomerSegment` | `retail` |
| `pat:mobile:23d6e6a718f8` | `orch:hasslaTier` | `gold` |
| `pat:mobile:23d6e6a718f8` | `orch:hassubscriber_profile` | `Gold_VoLTE_IntlRoam` |
| `pat:mobile:23d6e6a718f8` | `orch:hasroaming_profile` | `WorldZone1` |
| `pat:mobile:23d6e6a718f8` | `orch:hasvolte_enabled` | `true` |
| `pat:mobile:23d6e6a718f8` | `orch:hascodec_profile` | `EVS_AMR-WB` |
| `pat:mobile:23d6e6a718f8` | `orch:requiresResource` | `res:HLR-HSS` |
| `res:HLR-HSS` | `orch:provisionedBy` | `wf:hlr_provision` |
| `res:HLR-HSS` | `orch:hasAttribute` | `msisdn=447799000001` |
| `res:HLR-HSS` | `orch:hasAttribute` | `imsi=234159900000001` |
| `res:HLR-HSS` | `orch:hasAttribute` | `subscriber_profile=Gold_VoLTE_IntlRoam` |
| `res:HLR-HSS` | `orch:hasAttribute` | `roaming_profile=WorldZone1` |

The full pattern has **48 triples** covering all 6 network elements and their attributes.

### 3.5 Resource Bindings

The pattern maps 6 network elements to their workflows and attributes:

| Network Element | Workflow | Role | Key Attributes |
|----------------|----------|------|---------------|
| HLR/HSS | `hlr_provision` | Subscriber registry | msisdn, imsi, subscriber_profile, roaming_profile |
| IMS-Core | `ims_register` | VoLTE/VoWiFi call control | msisdn, imsi, volte_enabled, codec_profile |
| PCRF/PCF | `pcrf_configure` | Policy & charging rules | apn, qos_profile, charging_rule, bandwidth_limit |
| SMSC | `smsc_provision` | SMS store-and-forward | msisdn, routing, validity_period |
| MSC/MME | `msc_provision` | Mobility management | msisdn, imsi, location_area, tac |
| SBC | `sbc_configure` | Session border control | sip_domain, codec_list, media_handling |

---

## 4. KB-Seeded Pattern — The Bootstrap Mechanism

### 4.1 What It Is

On system startup, the `seed_kb_patterns()` function creates one pattern per service type using the knowledge base's resource definitions. These patterns have **empty characteristics** — they match any request for that service type at a low confidence of 0.25.

### 4.2 Example: KB Mobile Seed

```
ID:          pat:mobile:44136fa355b3
Service:     mobile
Label:       mobile | ?/?
Source:      kb
Confidence:  0.60
Use count:   8
```

This pattern started at 0.25 confidence. Every cache HIT on this wildcard pattern boosted its confidence — it's now at 0.60 after 8 uses. It acts as a safety net: even the first-ever request for a new mobile service variant will get KB-correct attribute names (not `default_*` placeholders).

### 4.3 Wildcard Matching Logic

When the pattern's characteristics are empty (KB-seeded), the similarity scoring returns a fixed 0.25 instead of the Jaccard formula. This means:

- It will match **any** mobile request
- But if a more specific pattern exists (e.g., `retail/gold` with confidence 0.98), the specific one wins
- The wildcard only activates when no specific pattern matches

### 4.4 Current KB-Seeded Patterns

| Pattern ID | Service | Confidence | Uses | Last Used |
|-----------|---------|------------|------|-----------|
| `pat:mobile:44136fa355b3` | mobile | 0.60 | 8 | 2026-06-23T03:33 |
| `pat:l3vpn:44136fa355b3` | l3vpn | 0.25 | 1 | 2026-06-22T12:23 |
| `pat:sdwan:44136fa355b3` | sdwan | 0.25 | 1 | 2026-06-22T12:23 |
| `pat:broadband:44136fa355b3` | broadband | 0.25 | 1 | 2026-06-22T12:23 |

---

## 5. How Patterns Are Used — The Matching Algorithm

### 5.1 Pipeline Integration

When a request arrives, the CACHE stage (STAGE 2) runs the pattern matching:

```
Request → detect_service_type() → "mobile"
       → extract characteristics (exclude msisdn, imsi, ip)
       → patterns.lookup("mobile", chars)
            │
            ├─ HIT  → reinforce() confidence
            │         → build plan from pattern.resources
            │         → cascade current request chars into plan
            │         → skip LLM entirely
            │
            └─ MISS → flag llm_used = true
                      → LLM generates plan
                      → patterns.learn() persists new pattern
```

### 5.2 Jaccard Similarity Scoring

The matching algorithm computes a Jaccard similarity between the request's service-defining characteristics and each candidate pattern's characteristics:

```
score = |intersection| / |union|

intersection = keys present in BOTH whose values match (string equality)
union = all distinct keys across both sets
```

**Special cases:**
- Empty pattern characteristics (KB wildcard) → fixed score 0.25
- Empty request characteristics → score 1.0 (match anything)
- Candidates sorted by `(-score, -confidence)` → best match wins

### 5.3 Instance vs. Service Attributes

A critical design element is the separation of **instance attributes** from **service attributes**:

**Instance attributes** (excluded from matching — identify specific subscribers/devices):
`msisdn`, `imsi`, `imei`, `pe_ip`, `hostname`, `serviceid`, `serial`, `loopback`, `management_ip`

**Service attributes** (used for matching — define the service pattern):
`customerSegment`, `slaTier`, `productId`, `subscriber_profile`, `roaming_profile`, `volte_enabled`, `codec_profile`, `apn`, `qos_profile`, `charging_rule`, `bandwidth_limit`, etc.

This separation means two subscribers with different phone numbers but identical service characteristics hit the same pattern.

### 5.4 Cascade Merge

On a cache HIT, the current request's **all_chars** (including instance attributes) are cascaded into the cached plan's parameters. This ensures:

- The plan reflects the **current subscriber's** values (msisdn, imsi)
- Not stale values from the subscriber that created the pattern
- The pattern stores the *template*; the MERGE stage applies the *instance*

### 5.5 Match Detail in the UI

Every cache lookup produces a `patternMatch` structure visible in the web UI's Pattern Analysis panel:

```
result: "HIT"
patternId: "pat:mobile:23d6e6a718f8"
confidence: 0.98
useCount: 28
score: 1.0  (Jaccard — all 13 keys matched)
matchedKeys: [customerSegment, slaTier, subscriber_profile, ...]
mismatchedKeys: []
extraKeys: []
excludedInstanceAttrs: [msisdn, imsi]
compareLogic: "Jaccard similarity on service-defining characteristics"
```

---

## 6. Pattern Lifecycle

### 6.1 Creation

```
KB-SEED (startup)         AUTO-LEARN (cache miss)     TEACH (manual API)
      │                          │                          │
      ▼                          ▼                          ▼
 confidence = 0.25        confidence = 0.30          confidence = 0.90
 source = "kb"            source = "auto"            source = "teach"
 chars = {}               chars = svc-defining      chars = from triples
                          triples from plan          triples from request body
```

### 6.2 Reinforcement

```
Every cache HIT:
  use_count += 1
  confidence += 0.05  (if < 0.90)
  confidence += 0.005 (if ≥ 0.90)
  last_used = now()
```

### 6.3 Deletion

Patterns are automatically deleted at load time if they fail validation:
- **Unreadable data** — deserialization error
- **Empty resources** — no network elements defined
- **Skeleton pattern** — fewer than 3 triples
- **`default_*` contamination** — kept but logged as warning

---

## 7. How to Manually Teach Patterns

Use the API to inject domain knowledge with high confidence:

```
POST /api/patterns/teach
{
  "triples": [
    ["pattern:enterprise-l3vpn", "rdf:type", "service:L3VPN"],
    ["pattern:enterprise-l3vpn", "orch:hascustomerSegment", "enterprise"],
    ["pattern:enterprise-l3vpn", "orch:hasslaTier", "platinum"],
    ["pattern:enterprise-l3vpn", "orch:requiresResource", "res:PE-Router"],
    ["res:PE-Router", "orch:provisionedBy", "wf:PE_Configuration"]
  ]
}
```

Taught patterns enter with confidence 0.90 and can override auto-learned patterns for the same characteristics.

---

## 8. Summary

| Aspect | Detail |
|--------|--------|
| **Data model** | RDF-inspired triples (subject, predicate, object) |
| **Matching** | Jaccard similarity on service-defining characteristics |
| **Instance separation** | msisdn/imsi/ip excluded from cache keys |
| **Confidence lifecycle** | 0.25 (kb) → 0.30 (auto) → 0.98 (mature) |
| **Bootstrap** | 4 KB-seeded wildcard patterns on startup |
| **Learning** | Every cache-MISS creates a new pattern |
| **Fast path** | Cache HIT → 0ms LLM latency |
| **Self-healing** | Corrupted patterns auto-deleted on load |
| **Teaching** | Manual injection via API at confidence 0.90 |

> **Current state (live):** 5 patterns in cache — 1 mature auto-learned (0.98), 1 reinforced KB-seed (0.60), 3 fresh KB-seeds (0.25)
