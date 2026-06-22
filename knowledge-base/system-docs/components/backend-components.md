# Backend Components Specification

> **Source file:** `poc/server_live.py` (1848 lines)  
> **Framework:** FastAPI + diskcache  
> **Generated:** 2026-06-22

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Models (Pydantic)](#data-models-pydantic)
3. [Core Classes](#core-classes)
4. [Pipeline Stages](#pipeline-stages)
5. [Helper Functions](#helper-functions)
6. [Constants & Configuration](#constants--configuration)
7. [API Routes](#api-routes)
8. [Cross-Component Integration Map](#cross-component-integration-map)
9. [Error Handling Summary](#error-handling-summary)

---

## Architecture Overview

The Telecom Orchestration Engine processes service provisioning requests through a multi-stage pipeline. The **foreground** (synchronous) path runs DETECT → MASK → CACHE and returns immediately. The **background** path (dispatched via `ThreadPoolExecutor`) completes RAG → LLM → HYDRATE → LOCK → MERGE → WRITETHROUGH → VALIDATE → EXECUTE → NOTIFY → VERIFY.

```
┌──────────┐   ┌──────────┐   ┌───────────┐
│  DETECT  │ → │   MASK   │ → │   CACHE   │  ← foreground (start_pipeline)
└──────────┘   └──────────┘   └─────┬─────┘
                                    │ dispatch to background thread
           ┌────────────────────────┼────────────────────────┐
           ▼            ▼           ▼           ▼            ▼
       ┌──────┐   ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌───────┐
       │ RAG  │ → │   LLM    │ →│ HYDRATE │→│   LOCK   │→│ MERGE │
       └──────┘   └──────────┘ └─────────┘ └──────────┘ └───┬───┘
           ▼            ▼           ▼           ▼            ▼
       ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
       │WRITETHR│→│VALIDATE│→│ EXECUTE  │→│ NOTIFY │→│  VERIFY  │
       └────────┘ └────────┘ └──────────┘ └────────┘ └──────────┘
```

---

## Data Models (Pydantic)

| Model | Lines | Purpose | Fields |
|-------|-------|---------|--------|
| `ProcessRequest` | 319–320 | Inbound request schema | `prompt: str` (min_length=1) |
| `TraceStep` | 322–324 | Single pipeline stage entry | `stage, status, title, detail, color, icon, elapsed_ms` |
| `ProcessResponse` | 326–330 | Full job response | `order_id, format, status, trace, total_ms, final_state?, started_at` |

**Integration Point:** `start_pipeline()` returns a `ProcessResponse`. Background stages append `TraceStep` objects via `jobs_lock`-guarded mutations to `jobs[order_id].trace`. The frontend polls `GET /api/process/{order_id}` to read incremental trace and `final_state`.

---

## Core Classes

### 1. `DataMasker` (Lines 338–357)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Strip sensitive identifiers (MSISDN, IP) before data leaves the local perimeter for cloud AI. |
| **Responsibility** | Replace phone numbers with `VAR_MSISDN_N` and IP addresses with `VAR_IP_N` tokens. Build bidirectional mapping. |
| **Key Methods** | `mask(text: str) → tuple[str, dict]` |

**Method `mask(text)`**
- **Signature:** `def mask(self, text: str) -> tuple[str, dict]`
- **Input:** Raw prompt string (may contain real MSISDNs and IPs)
- **Output:** `(masked_text, token_map)` where `token_map` is `{VAR_XXX: original_value, original_value: VAR_XXX, ...}` — bidirectional for hydration
- **Regex patterns:** `MSISDN_RE = r'\+?\d{5,15}'`, `IP_RE = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'`
- **Error handling:** None explicit — regex-safe substitution; duplicates reuse existing tokens via dictionary check

**Integration Points:**
- **Called by:** `start_pipeline()` STAGE 1 (MASK) — line 1162
- **Feeds:** `token_map` stored in `bg_state` and passed to `_run_background_inner` STAGE 5 (HYDRATE) — line 1473

---

### 2. `PatternNode` (Lines 400–422)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Data class representing a learned orchestration pattern as an RDF-like graph. |
| **Responsibility** | Hold pattern identity, triples, resources, confidence, and usage metadata. |

**Fields:**

| Field | Type | Purpose |
|-------|------|---------|
| `id` | `str` | Unique pattern ID (e.g., `pat:mobile:abc123`) |
| `service_type` | `str` | Service domain (`mobile`, `l3vpn`, `sdwan`, `broadband`) |
| `label` | `str` | Human-readable label |
| `characteristics` | `dict` | Service-defining characteristics (excludes instance IDs) |
| `triples` | `list` | RDF-like assertions `[subject, predicate, object]` |
| `resources` | `list` | Derived resource bindings with `{name, workflow, role, attributes}` |
| `confidence` | `float` | Confidence score (0.0–0.98), boosts on cache hits |
| `use_count` | `int` | Times pattern matched |
| `created_at` | `str` | ISO 8601 creation timestamp |
| `last_used` | `str` | ISO 8601 last match timestamp |
| `source` | `str` | `"auto"`, `"teach"`, or `"kb"` |

**Method `to_dict()`** (line 415): Serializes all fields to dict for JSON responses.

**Integration Points:**
- **Created by:** `PatternEngine.learn()`, `PatternEngine.teach()`
- **Read by:** `PatternEngine.lookup()`, `PatternEngine._load()`, `start_pipeline()` (CACHE stage)
- **Serialized by:** diskcache `cache.set()` / `cache.get()` with the key `orch:pat:{id}`

---

### 3. `PatternEngine` (Lines 425–661)

| Aspect | Detail |
|--------|--------|
| **Purpose** | RDF-inspired pattern store with learning, confidence scoring, and query matching. |
| **Responsibility** | Store, index, query, and reinforce orchestration patterns. Validate pattern integrity on load. |

**Key Constants:**
- `INSTANCE_ATTRS` (line 428): `{"msisdn", "imsi", "imei", "pe_ip", "hostname", "serviceid", "serial", "loopback", "management_ip"}` — excluded from cache keys

**Key Methods:**

| Method | Lines | Signature | Purpose |
|--------|-------|-----------|---------|
| `__init__` | 431–434 | `(cache: diskcache.Cache)` | Init with diskcache backend, load index |
| `_load_index` | 436–437 | `()` | Load `orch:idx:patterns` from cache |
| `_save_index` | 439–440 | `()` | Persist index to cache |
| `_key` | 442–443 | `(pid: str) → str` | Generate cache key `orch:pat:{pid}` |
| `lookup` | 447–460 | `(service_type, characteristics) → PatternNode\|None` | Find best-matching pattern |
| `_match_score` | 462–476 | `(pat_chars, req_chars) → float` | Jaccard similarity on service-defining chars |
| `learn` | 480–545 | `(svc, chars, plan, all_chars?, source?) → PatternNode` | Create new pattern from cache miss |
| `reinforce` | 547–556 | `(pattern: PatternNode) → PatternNode` | Boost confidence on cache hit |
| `teach` | 558–583 | `(triples, source?) → PatternNode` | Manual knowledge injection |
| `list_all` | 587–600 | `() → list[dict]` | List all patterns with metadata |
| `get` | 602–604 | `(pid: str) → dict\|None` | Get full pattern details |
| `_save` | 608–609 | `(node: PatternNode)` | Persist pattern to cache |
| `_load` | 611–644 | `(pid: str) → PatternNode\|None` | Load with runtime validation |
| `_unindex` | 646–654 | `(pid: str)` | Remove pattern from index and cache |
| `_index_pattern` | 656–661 | `(node: PatternNode)` | Add pattern to type index |

**Input/Output for Key Methods:**

**`lookup(service_type, characteristics)`**
- **Input:** `service_type: str`, `characteristics: dict` (service-defining only, instance attrs excluded)
- **Output:** `PatternNode` if match found, `None` otherwise
- **Scoring:** `_match_score()` uses Jaccard similarity: `|intersection| / |union|`. Wildcard (empty pat_chars) matches at 0.25. Empty req_keys returns 1.0.

**`learn(service_type, characteristics, plan, all_chars, source)`**
- **Input:** service type, service-defining chars, plan dict `{workflows, params, devices}`, full chars (with instance IDs), source label
- **Output:** New `PatternNode` with derived RDF triples and resource entries
- **Triple structure:** `[pid, "rdf:type", "service:..."], [pid, "orch:has{k}", v], [pid, "orch:requiresResource", rid], [rid, "orch:provisionedBy", wf], [rid, "orch:hasAttribute", "k=v"]`

**`_load(pid)` — Runtime Validation (lines 611–644):**
1. Catches `Exception` from `cache.get()` → unindexes and returns `None`
2. Rejects patterns with no `resources` → unindex + delete
3. Rejects patterns with `< 3` triples → unindex + delete
4. Logs warning (but keeps) patterns with `default_*` contamination

**Error Handling:**
- Unreadable cache entries: caught by try/except, logged, pattern unindexed
- Empty/skeleton patterns: detected via attribute checks, deleted from index
- `default_*` contamination: logged as warning but pattern remains usable (attribute names are still correct)

**Integration Points:**
- **Global instance:** `patterns = PatternEngine(cache)` (line 665)
- **Called by:** `start_pipeline()` (CACHE stage — `lookup`, `reinforce`), `_run_background_inner` (WRITETHROUGH — `learn`), routes (`list_all`, `get`, `teach`)
- **Feeds:** `seed_kb_patterns()` via `learn()`

---

### 4. `ServiceModelStore` (Lines 34–193)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Persistent flat representation of a subscriber service, keyed by `subscriber_id`. |
| **Responsibility** | Store/load/compare subscriber models. Runtime corruption detection. Change detection for repeat requests. |

**Key Methods:**

| Method | Lines | Signature | Purpose |
|--------|-------|-----------|---------|
| `__init__` | 44–45 | `(cache: diskcache.Cache)` | Init with diskcache |
| `_key` | 47–48 | `(subscriber_id) → str` | Cache key `orch:sub:{id}` |
| `get` | 50–104 | `(subscriber_id) → dict\|None` | Load with runtime corruption check |
| `save` | 106–109 | `(subscriber_id, model: dict)` | Persist model, bump version |
| `delete` | 111–114 | `(subscriber_id)` | Remove model from cache |
| `compute_diff` | 116–168 | `(previous, incoming_chars, new_nes) → dict` | Compare models for change detection |
| `build_model` | 170–193 | `(subscriber_id, svc, all_chars, nes, version) → dict` | Construct model dict |

**`get(subscriber_id)` — Runtime Corruption Check (lines 50–104):**
1. `None` return if key missing
2. Non-dict values: logged + deleted → `None`
3. Scans for `default_*` and `<placeholder>` contamination in characteristics and NE attributes
4. **Partially corrupt:** if `real_nes >= MIN_REAL_ATTRS` and not all chars corrupted → salvages by stripping corrupted characteristics
5. **Fully corrupt:** deletes entry, returns `None` → pipeline treats as fresh provisioning

**`compute_diff(previous, incoming_chars, new_network_elements)`**
- **Input:** Previous model dict (or `None`), incoming characteristics, new NE list
- **Output:** `{hasPrevious, isFirstRun, hasChanges, changedAttributes, networkElementDiffs}`
- **NE matching:** Normalizes names by stripping `/HSS`, `/PCF`, `/MME` suffixes for fuzzy matching (e.g., `PCRF` matches `PCRF/PCF`)

**`build_model(subscriber_id, svc, all_chars, network_elements, version)`**
- **Input:** Subscriber identity, service type, characteristics, NE list, version
- **Output:** Model dict with merged characteristics (NE attributes merged into top-level chars, excluding `status` and `default_*`/`<placeholder>` values) plus `version` and `last_updated`

**Integration Points:**
- **Global instance:** `service_models = ServiceModelStore(cache)` (line 195)
- **Called by:** `start_pipeline()` (CACHE — loads previous model), `_run_background_inner` (VERIFY — `compute_diff` + `build_model` + `save`), `validate_and_repair_cache()` (startup scan)
- **Feeds:** `previous_model` into `bg_state`, `subscriber_diff` into `final_state`

---

### 5. `SubscriberLock` (Lines 200–249)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Per-subscriber advisory lock to prevent concurrent modification race conditions. |
| **Responsibility** | Acquire/release locks with TTL-based deadlock prevention. Re-entrant within same worker. |

**Key Constants:**
- `LOCK_TTL = 30` (seconds) — auto-expiry prevents dead worker locks
- `RETRY_DELAY = 0.1` (seconds) — spin-wait interval
- `MAX_RETRIES = 50` — 5-second total budget

**Key Methods:**

| Method | Lines | Signature | Purpose |
|--------|-------|-----------|---------|
| `__init__` | 215–217 | `(cache: diskcache.Cache)` | Init with diskcache + thread-local |
| `acquire` | 219–221 | `(subscriber_id, worker_id) → _LockContext` | Returns context manager |
| `_try_acquire` | 223–240 | `(lock_key, worker_id) → bool` | Non-blocking acquire with retry |
| `_release` | 242–245 | `(lock_key, worker_id)` | Release if owned by this worker |
| `force_release` | 247–249 | `(subscriber_id)` | Admin force-release |

**Lock Key Format:** `lock:sub:{subscriber_id}`  
**Lock Value:** `{worker_id, acquired_at}` with `expire=LOCK_TTL`

**`_try_acquire` — State Machine:**
1. Lock is `None` → acquire (new lock)
2. Lock expired (`now - acquired_at > LOCK_TTL`) → steal (dead worker)
3. Lock held by same `worker_id` → re-entrant, return True
4. Otherwise → sleep `RETRY_DELAY`, retry up to `MAX_RETRIES`

**Integration Points:**
- **Global instance:** `subscriber_lock = SubscriberLock(cache)` (line 270)
- **Used by:** `_run_background_inner` (LOCK stage — wraps MERGE through VERIFY in critical section)
- **Admin endpoints:** `POST /api/locks/release`, `GET /api/locks/status`
- **On lock timeout:** Pipeline sets status to `"blocked"` and returns without modifying model

---

### 6. `_LockContext` (Lines 252–267)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Context manager wrapper for `SubscriberLock.acquire()`. |
| **Responsibility** | Handle `__enter__`/`__exit__` protocol; release on scope exit. |

**Key Methods:**

| Method | Lines | Signature |
|--------|-------|-----------|
| `__init__` | 254–258 | `(lock: SubscriberLock, subscriber_id, worker_id)` |
| `__enter__` | 260–262 | Attempts `_try_acquire()`; returns `bool` |
| `__exit__` | 264–267 | If acquired, calls `_release()` |

**Integration Points:**
- **Created by:** `SubscriberLock.acquire()` (line 221)
- **Used by:** `with subscriber_lock.acquire(...) as lock_acquired:` in `_run_background_inner` (line 1516)

---

### 7. `LifecycleNotifier` (Lines 785–943)

| Aspect | Detail |
|--------|--------|
| **Purpose** | Emits TMF641-compliant ServiceOrderMilestoneEvent and ServiceOrderStateChangeEvent. |
| **Responsibility** | Track lifecycle state transitions per KB-defined lifecycle. Buffer and flush notifications. |

**Key Constants:**
- `ORDER_IN_PROGRESS = "inProgress"` — canonical order state during provisioning
- `ORDER_COMPLETED = "completed"` — final state
- `ORDER_FAILED = "failed"` — error state (reserved)

**Key Methods:**

| Method | Lines | Signature | Purpose |
|--------|-------|-----------|---------|
| `__init__` | 802–803 | `()` | Init with empty notifications list |
| `parse_lifecycle` | 805–810 | `(svc: str) → list[str]` | Parse `"STATE1 → STATE2 → ..."` from KB |
| `_base_event` | 812–825 | `(event_type, order_id, correlation_id, domain?, priority?) → dict` | Build TMF notification envelope |
| `emit_milestone` | 827–860 | `(state, svc, order_id, correlation_id, description?, status?) → dict` | Emit milestone event |
| `emit_state_change` | 862–885 | `(to_state, svc, order_id, correlation_id, description?) → dict` | Emit state change event |
| `flush` | 887–891 | `() → list[dict]` | Return and clear notification buffer |
| `build_notification_trace` | 893–942 | `(order_id, svc, subscriber_id, t0, step_fn) → int` | Walk lifecycle, emit all notifications, return count |

**`build_notification_trace` — Logic:**
- Iterates through KB lifecycle states (e.g., `["DESIGNED", "FEASIBILITY_CHECKED", ..., "ACTIVE"]`)
- All but last state → `ServiceOrderMilestoneEvent` (order stays `inProgress`)
- Last state (ACTIVE) → `ServiceOrderStateChangeEvent` (order → `completed`)
- Each notification calls `step_fn("NOTIFY", "done", ...)` to append trace step

**Event Schema** (TMF641 v4.1.0):
- **Milestone:** `{eventId, eventTime, eventType: "ServiceOrderMilestoneEvent", correlationId, domain, priority, event: {serviceOrder: {id, href, state, externalId, category, milestone: [{id, name, description, message, milestoneDate, status}]}}}`
- **State Change:** `{eventId, eventTime, eventType: "ServiceOrderStateChangeEvent", correlationId, domain, priority, event: {serviceOrder: {id, href, state, externalId, category, completionDate?}}}`

**Integration Points:**
- **Global instance:** `lifecycle_notifier = LifecycleNotifier()` (line 945)
- **Called by:** `_run_background_inner` (NOTIFY stage — `build_notification_trace`)
- **Feeds:** Notifications embedded in `final_state["notifications"]`, exposed via `GET /api/notifications/{order_id}`

---

## Pipeline Stages

### Stage Table (Quick Reference)

| # | Stage | Location | Lines | Foreground/Background | Key Input | Key Output |
|---|-------|----------|-------|-----------------------|-----------|------------|
| 0 | **DETECT** | `start_pipeline` | 1137–1158 | Foreground | `prompt: str` | `fmt` ("tmf640"/"unstructured"), `is_json` |
| 1 | **MASK** | `start_pipeline` | 1160–1182 | Foreground | Raw prompt | `masked_text`, `token_map`, `n_tokens` |
| 2 | **CACHE** | `start_pipeline` | 1184–1313 | Foreground | `svc`, `chars`, `all_chars` | `plan`, `llm_used`, `pattern_hit`, `pattern_match`, `previous_model`, `subscriber_id` |
| 3 | **RAG** | `_run_background_inner` | 1390–1403 | Background | `svc` | `sr` (service resources), NE count/list |
| 4 | **LLM** | `_run_background_inner` | 1405–1467 | Background | `masked_text`, `kb_context` | `plan` (from Deepseek or fallback) |
| 5 | **HYDRATE** | `_run_background_inner` | 1472–1489 | Background | `plan`, `token_map` | Hydrated `plan` with real identifiers |
| 6 | **LOCK** | `_run_background_inner` | 1508–1540 | Background | `subscriber_id`, `order_id` | `lock_acquired: bool` |
| 7 | **MERGE** | `_run_background_inner` | 1542–1574 | Background | `plan_params`, `all_chars`, `previous_model` | `plan["params"]` enriched |
| 8 | **WRITETHROUGH** | `_run_background_inner` | 1576–1589 | Background | `llm_used`, `plan`, `all_chars` | `learned` PatternNode (if LLM used) |
| 9 | **VALIDATE** | `_run_background_inner` | 1591–1609 | Background | `plan`, `masked_text` | Pass/block decision |
| 10 | **EXECUTE** | `_run_background_inner` | 1611–1618 | Background | `plan["workflows"]`, `plan["devices"]` | Completion trace (mock execution) |
| 11 | **NOTIFY** | `_run_background_inner` | 1683–1688 | Background | `order_id`, `svc`, `subscriber_id` | TMF641 notifications in buffer |
| 12 | **VERIFY** | `_run_background_inner` | 1620–1709 | Background | `plan`, `all_chars`, `previous_model` | `final_state` dict, model saved |

### Detailed Stage Descriptions

#### STAGE 0: DETECT (Lines 1137–1158)
- **Purpose:** Classify incoming request as structured (TMF640/TMF641 JSON) or unstructured text.
- **Logic:** Check if `prompt.strip().startswith("{")`. If JSON, validate with `json.loads()` — on `JSONDecodeError`, return error response immediately.
- **Error handling:** Invalid JSON → early return with `status="error"`, no background thread spawned.

#### STAGE 1: MASK (Lines 1160–1182)
- **Purpose:** Replace all sensitive identifiers (MSISDN, IP) with `VAR_*` tokens before any data reaches cloud AI.
- **Logic:** Instantiate `DataMasker()`, call `masker.mask(prompt)`. Token map is bidirectional (`token→real` and `real→token`).
- **Error handling:** None needed — regex-safe; if no matches, returns unmasked text.

#### STAGE 2: CACHE (Lines 1184–1313)
- **Purpose:** Query the RDF pattern store. On HIT, skip LLM. On MISS, flag LLM needed and learn afterward.
- **Logic:**
  1. `detect_service_type(prompt)` → svc
  2. Build `chars` (service-defining) and `all_chars` (includes instance attrs)
  3. `extract_subscriber_id()` → load `previous_model` via `service_models.get()`
  4. `patterns.lookup(svc, chars)` → if hit, `reinforce()` and build plan from pattern resources
  5. On cache hit: cascade `all_chars` into plan params (sync-phase merge)
  6. Build `pattern_match` dict for UI comparison table
- **Integration:** Populates `bg_state` dict with all stage outputs for background thread.

#### STAGE 3: RAG (Lines 1390–1403)
- **Purpose:** Load domain knowledge from in-memory `SERVICE_RESOURCES` dict.
- **Logic:** Look up service type, log NE count and names, emit trace step.
- **No I/O impact** — just constructs trace metadata.

#### STAGE 4: LLM (Lines 1405–1467)
- **Purpose:** Call Deepseek v4 for orchestration plan generation (only if `llm_used=True`).
- **Logic:**
  1. Build prompt from `kb_context` (truncated to 4000 chars) + `masked_text` (truncated to 2000 chars)
  2. Call `call_deepseek(llm_prompt, timeout=90)`
  3. Parse JSON response; on `JSONDecodeError`, try regex extraction (`re.search(r'\{[\s\S]*\}', ...)`)
  4. If all parsing fails, use `_fallback_plan(svc)`
  5. On cache hit: skip entirely, emit "Skipped (Cache Hit)" trace
- **Prompt format:** Instructs model to return `{workflows, params, devices}` using KB knowledge and masked tokens.

#### STAGE 5: HYDRATE (Lines 1472–1489)
- **Purpose:** Restore real identifiers by replacing `VAR_*` tokens in the plan.
- **Logic:** String-replace in `json.dumps(plan)` for each token→real mapping, then `json.loads()`.
- **Error handling:** If `token_map` is empty, skip (no-op).

#### STAGE 6: LOCK (Lines 1508–1540)
- **Purpose:** Acquire exclusive subscriber lock before modifying the service model.
- **Logic:** `with subscriber_lock.acquire(subscriber_id, order_id) as lock_acquired:`
- **Error handling:** If `lock_acquired` is `False` after 5s retry budget → set status to `"blocked"`, return without modification.

#### STAGE 7: MERGE (Lines 1542–1574)
- **Purpose:** Cascade request characteristics and previous model values into the plan params.
- **Logic:**
  1. Always cascade `all_chars` into `plan_params` (skip `default_*` and `<placeholder>` values)
  2. If `previous_model` exists, fill gaps with non-default values from previous characteristics
- **Protected by:** Subscriber lock (runs inside `with` block)

#### STAGE 8: WRITETHROUGH (Lines 1576–1589)
- **Purpose:** Persist newly learned patterns to diskcache.
- **Logic:** If `llm_used`, call `patterns.learn(svc, chars, plan, all_chars=all_chars)`. Otherwise, log that pattern was reinforced by cache hit.
- **Output:** `learned` (PatternNode or None)

#### STAGE 9: VALIDATE (Lines 1591–1609)
- **Purpose:** Security gateway — block destructive commands.
- **Logic:** Concatenate `json.dumps(plan)` + `masked_text`, check against `BLOCKED_KEYWORDS`. If any keyword found → status `"blocked"`, return.
- **Error handling:** Early return on block; no devices touched.

#### STAGE 10: EXECUTE (Lines 1611–1618)
- **Purpose:** Dispatch validated plan to infrastructure (mock execution in PoC).
- **Logic:** Reads `plan["workflows"]` and `plan["devices"]`, emits trace step. No actual device interaction in PoC.

#### STAGE 11: NOTIFY (Lines 1683–1688)
- **Purpose:** Emit TMF641 lifecycle notifications.
- **Logic:** `lifecycle_notifier.build_notification_trace()` walks KB lifecycle, emits milestone + state change events. Calls `flush()` to collect all notifications.

#### STAGE 12: VERIFY (Lines 1620–1709)
- **Purpose:** Build network element details, compute subscriber diff, save service model, assemble final state.
- **Logic:**
  1. Build `network_elements` list from KB resource definitions + plan params + previous model gap-filling
  2. `service_models.compute_diff(previous_model, all_chars, network_elements)`
  3. `service_models.build_model()` + `service_models.save()`
  4. Assemble `final_state` dict with all outputs
  5. Set `jobs[order_id].status = "completed"`, set `final_state`

---

## Helper Functions

### Quick Reference Table

| Function | Lines | Signature | Purpose |
|----------|-------|-----------|---------|
| `extract_subscriber_id` | 273–288 | `(prompt, is_json, all_chars) → str` | Derive stable subscriber identifier |
| `flatten_plan_params` | 291–313 | `(plan: dict) → dict` | Un-nest workflow-keyed params to flat dict |
| `seed_kb_patterns` | 668–708 | `()` | Pre-seed pattern store from KB on module load |
| `validate_and_repair_cache` | 948–1035 | `()` | Startup cache integrity scan |
| `load_kb_context` | 1041–1081 | `(svc: str) → str` | Load domain knowledge from KB files |
| `call_deepseek` | 1086–1112 | `(prompt, timeout=120) → str` | Invoke Deepseek via hermes CLI |
| `detect_service_type` | 1115–1121 | `(text: str) → str` | Classify service type from keywords |
| `_fallback_plan` | 1721–1733 | `(svc: str) → dict` | Generate plan from SERVICE_RESOURCES |

### Detailed Descriptions

#### `extract_subscriber_id(prompt, is_json, all_chars)` (Lines 273–288)
- **Purpose:** Extract stable subscriber identity for service model persistence.
- **Logic:**
  1. If JSON: try `data.get("serviceId")` or `data.get("externalId")`
  2. Fallback: `all_chars.get("msisdn")` → `"MSISDN-{value}"`
  3. Last resort: `"SUB-{sha256(prompt)[:12]}"` (hash-based, stable for identical requests)
- **Error handling:** Try/except around `json.loads()` — silently falls through to fallbacks
- **Integration:** Called in `start_pipeline()` CACHE stage (line 1213)

#### `flatten_plan_params(plan)` (Lines 291–313)
- **Purpose:** Flatten nested workflow-keyed params (common LLM output pattern) into single flat dict.
- **Input:** Plan dict where `params` may be `{"HLR_Provisioning": {...}, "IMS_Registration": {...}}`
- **Output:** Plan dict where `params` is `{"msisdn": ..., "imsi": ..., "codec_profile": ...}`
- **Idempotent:** If params are already flat (no sub-dict values), returns unchanged.
- **Integration:** Called after LLM stage (line 1470) and after HYDRATE

#### `seed_kb_patterns()` (Lines 668–708)
- **Purpose:** Pre-populate pattern store from `SERVICE_RESOURCES` on module load.
- **Logic:** For each service type in `SERVICE_RESOURCES`, builds a plan from KB resource definitions using `WF_MAP` for workflow names and `<attr>` placeholders, then calls `patterns.learn()` with `source="kb"`, resetting confidence to 0.25.
- **Called at:** Line 780 (module-level, after `SERVICE_RESOURCES` and `WF_MAP` definitions)
- **Error handling:** Checks if patterns already exist for service type before seeding (idempotent)

#### `validate_and_repair_cache()` (Lines 948–1035)
- **Purpose:** Startup cross-item cache integrity scan.
- **Scans:**
  1. **Subscriber models:** Delegate per-model validation to `service_models.get()`; track MSISDNs for dedup
  2. **Duplicate subscribers:** Merge duplicates (keep highest version, delete others)
  3. **Pattern index integrity:** Remove stale index entries pointing to deleted patterns; delete empty service type keys
  4. **Orphan patterns:** Re-index patterns in cache but missing from index
- **Called at:** Line 1038 (module-level, after `LifecycleNotifier` and `service_models`)
- **Error handling:** Delegates per-item validation to runtime guards (`service_models.get()`, `patterns._load()`). Logs all repairs.

#### `load_kb_context(svc)` (Lines 1041–1081)
- **Purpose:** Load domain knowledge text from KB files for LLM context.
- **Sources:** `core-ontology.md` (Service/Resource Taxonomy sections, first 1500 chars), `standards-index.md` (filtered for service-relevant lines), and in-memory `SERVICE_RESOURCES`.
- **Output:** Concatenated string with structured resource knowledge (NE types, roles, attributes, lifecycle).
- **Error handling:** All file operations wrapped in try/except — falls back to `KB_DOCS` string if file reads fail.

#### `call_deepseek(prompt, timeout=120)` (Lines 1086–1112)
- **Purpose:** Invoke Deepseek v4 via `hermes chat` CLI.
- **Command:** `hermes chat -q "{prompt}" --quiet -m deepseek-v4-pro --provider deepseek`
- **Working directory:** `/opt/data`
- **Error handling:**
  - `subprocess.TimeoutExpired` → logged, returns `""`
  - General `Exception` → logged, returns `""`
  - Empty stdout → logged with stderr preview, returns `""`
  - Strips `session_id:` line from output
- **Integration:** Called by LLM stage with `timeout=90` (line 1427)

#### `detect_service_type(text)` (Lines 1115–1121)
- **Purpose:** Keyword-based service type classification.
- **Mapping:** `mobile` ← msisdn, sim, activate, voice, sms; `l3vpn` ← mpls, vpn, bgp, vrf (excluding "sd"); `sdwan` ← sd-wan, sdwan; `broadband` ← ftth, fiber, ont, olt. Default: `"mobile"`.
- **Integration:** Called in `start_pipeline()` CACHE stage (line 1185)

#### `_fallback_plan(svc)` (Lines 1721–1733)
- **Purpose:** Generate orchestration plan from `SERVICE_RESOURCES` when Deepseek is unavailable.
- **Logic:** Maps KB resource types to devices and workflows via `WF_MAP`, creates `<attr>` placeholder params.
- **Integration:** Called in LLM stage when `call_deepseek()` returns empty or parse fails (lines 1438, 1440, 1452)

---

## Constants & Configuration

| Constant | Lines | Type | Purpose |
|----------|-------|------|---------|
| `BLOCKED_KEYWORDS` | 362–363 | `list[str]` | Destructive commands blocked by VALIDATE |
| `KB_DOCS` | 365–370 | `dict[str, str]` | Short standards references per service type |
| `KB_DIR` | 372 | `str` | Path to knowledge base directory |
| `SERVICE_RESOURCES` | 714–761 | `dict` | Complete KB-derived resource definitions per service type |
| `WF_MAP` | 765–777 | `dict[str, str]` | Network Element type → workflow name mapping |

### `SERVICE_RESOURCES` Structure (Lines 714–761)
```python
{
    "mobile": {
        "domain": "Voice / Mobile Core",
        "standards": ["3GPP TS 29.002 ...", ...],
        "required_resources": [
            {"type": "HLR/HSS", "role": "Subscriber registry", "attributes": ["msisdn", "imsi", ...]},
            ...
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → ... → ACTIVE",
    },
    "l3vpn": {...}, "sdwan": {...}, "broadband": {...}
}
```

### `WF_MAP` (Lines 765–777)
Maps NE type → workflow name. Shared by `seed_kb_patterns()` and `_fallback_plan()`. Example: `"HLR" → "HLR_Provisioning"`, `"PE Router" → "PE_Configuration"`.

### `BLOCKED_KEYWORDS` (Lines 362–363)
```python
["erase", "reload", "format", "shutdown", "no switchport",
 "write erase", "delete startup-config", "boot system flash"]
```
Checked case-insensitively in VALIDATE stage against `json.dumps(plan) + masked_text`.

---

## API Routes

| Method | Path | Lines | Handler | Purpose |
|--------|------|-------|---------|---------|
| `POST` | `/api/process` | 1738–1740 | `process()` | Submit provisioning request |
| `GET` | `/api/process/{order_id}` | 1743–1750 | `get_process()` | Poll pipeline result + trace |
| `GET` | `/api/patterns` | 1752–1755 | `list_patterns()` | List all learned patterns |
| `GET` | `/api/patterns/{pattern_id}` | 1757–1763 | `get_pattern()` | Full pattern details with triples |
| `POST` | `/api/patterns/teach` | 1765–1772 | `teach_pattern()` | Manual pattern injection |
| `GET` | `/api/samples` | 1774–1791 | `get_samples()` | Sample request payloads |
| `GET` | `/health` | 1793–1795 | `health()` | Health check + cache stats |
| `GET` | `/api/notifications/{order_id}` | 1797–1810 | `get_notifications()` | TMF641 notifications for completed order |
| `POST` | `/api/locks/release` | 1812–1819 | `release_lock()` | Admin force-release subscriber lock |
| `GET` | `/api/locks/status` | 1821–1836 | `lock_status()` | List all active subscriber locks |

**Error Responses:**
- `GET /api/process/{id}`: 404 `{"error": "order not found"}`
- `GET /api/patterns/{id}`: 404 `{"error": "pattern not found"}`
- `POST /api/patterns/teach`: 400 `{"error": "triples required"}`
- `GET /api/notifications/{id}`: 404 `{"error": "order not found"}`; 200 `{"notifications": [], "message": "Pipeline still processing"}` if not yet complete
- `POST /api/locks/release`: 400 `{"error": "subscriberId required"}`

**Static Files:** Frontend served at `/` → `static/index.html` (line 1840); `/static/*` mounted via `StaticFiles` (line 1843).

---

## Cross-Component Integration Map

```
┌──────────────────────────────────────────────────────────────────────┐
│                        start_pipeline()                              │
│  ┌─────────┐    ┌──────────┐    ┌────────────┐    ┌──────────────┐  │
│  │ DETECT  │───→│  MASK    │───→│   CACHE    │───→│  Dispatch    │  │
│  │         │    │DataMasker│    │PatternEng. │    │  (executor)  │  │
│  └─────────┘    └──────────┘    │SvcModelStr.│    └──────┬───────┘  │
│                                 └────────────┘           │          │
└──────────────────────────────────────────────────────────┼──────────┘
                                                           │
                                      ┌────────────────────┘
                                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     _run_background_inner()                           │
│  ┌──────┐  ┌──────┐  ┌────────┐  ┌──────────┐  ┌───────┐          │
│  │ RAG  │→ │ LLM  │→ │HYDRATE │→ │  LOCK    │→ │ MERGE │          │
│  │      │  │Deepsk│  │(unmask)│  │SubscrLock│  │       │          │
│  └──────┘  └──┬───┘  └────────┘  └──────────┘  └───┬───┘          │
│               │                                     │               │
│               ▼                                     ▼               │
│         _fallback_plan()  ┌────────────┐  ┌───────────┐           │
│           (on failure)    │WRITETHROUGH│  │ VALIDATE  │           │
│                           │PatternEng. │  │BLOCKED_KW │           │
│                           │  .learn()  │  └─────┬─────┘           │
│                           └────────────┘        │                 │
│                                                 ▼                 │
│                           ┌──────────┐  ┌──────────────┐         │
│                           │ EXECUTE  │→ │   NOTIFY     │         │
│                           │ (mock)   │  │LifecycleNotif│         │
│                           └──────────┘  └──────┬───────┘         │
│                                                ▼                 │
│                           ┌──────────────────────────────┐       │
│                           │          VERIFY              │       │
│                           │  ServiceModelStore:          │       │
│                           │    compute_diff()            │       │
│                           │    build_model()             │       │
│                           │    save()                    │       │
│                           └──────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Error Handling Summary

| Component | Error Scenario | Handling |
|-----------|---------------|----------|
| **DataMasker** | No sensitive data found | No-op; unmasked text returned |
| **PatternEngine._load** | Unreadable cache entry | Catch `Exception`, unindex, return `None` |
| **PatternEngine._load** | Pattern with no resources | Unindex + delete, return `None` |
| **PatternEngine._load** | Pattern with < 3 triples | Unindex + delete, return `None` |
| **PatternEngine._load** | `default_*` contamination | Log warning, keep pattern (attribute names still valid) |
| **ServiceModelStore.get** | Non-dict value in cache | Log + delete, return `None` |
| **ServiceModelStore.get** | Partial corruption | Strip corrupted chars, return salvaged model |
| **ServiceModelStore.get** | Full corruption | Delete entry, return `None` → fresh provisioning |
| **SubscriberLock._try_acquire** | Lock held by another worker | Retry up to 50× (5s), return `False` |
| **SubscriberLock._try_acquire** | Dead worker (expired lock) | Steal lock, set new owner |
| **start_pipeline (DETECT)** | Invalid JSON | Return error response immediately, no background thread |
| **_run_background** | Any unhandled exception | Log full traceback, set job status to `"error"`, append ERROR trace step |
| **_run_background_inner (LLM)** | Deepseek timeout/error | Fall back to `_fallback_plan(svc)` |
| **_run_background_inner (LLM)** | JSON parse failure | Try regex extraction; fall back to `_fallback_plan(svc)` |
| **_run_background_inner (LOCK)** | Lock timeout | Set status `"blocked"`, return without modification |
| **_run_background_inner (VALIDATE)** | Blocked keyword detected | Set status `"blocked"`, return, no devices touched |
| **validate_and_repair_cache** | Duplicate subscribers | Keep highest version, delete duplicates |
| **validate_and_repair_cache** | Stale index entries | Remove from index, clean up empty service keys |
| **validate_and_repair_cache** | Orphan patterns | Re-index if valid; runtime guard deletes invalid ones |
| **load_kb_context** | File read failure | Catch `Exception`, fall back to `KB_DOCS` string |
| **call_deepseek** | Timeout, subprocess error, empty output | Log and return `""` |
| **extract_subscriber_id** | JSON parse failure | Catch-all except, fall through to MSISDN → hash |
| **API routes** | Order/pattern not found | Return 404 JSON |
| **API routes** | Missing required field | Pydantic validation (FastAPI auto 422) |

---

## Module Initialization Order

The module executes these steps at import time (in order):

1. **Lines 1–29:** Imports, logging config, FastAPI app, diskcache, job store, thread pool
2. **Lines 34–195:** `ServiceModelStore` class definition + instance (`service_models`)
3. **Lines 200–270:** `SubscriberLock` + `_LockContext` + instance (`subscriber_lock`)
4. **Lines 273–313:** `extract_subscriber_id()`, `flatten_plan_params()` definitions
5. **Lines 319–330:** Pydantic model definitions
6. **Lines 338–357:** `DataMasker` class
7. **Lines 362–372:** `BLOCKED_KEYWORDS`, `KB_DOCS`, `KB_DIR`
8. **Lines 400–665:** `PatternNode`, `PatternEngine` + instance (`patterns`)
9. **Lines 668–708:** `seed_kb_patterns()` definition
10. **Lines 714–777:** `SERVICE_RESOURCES`, `WF_MAP`
11. **Line 780:** `seed_kb_patterns()` — **executed at module load** (populates cache)
12. **Lines 785–945:** `LifecycleNotifier` class + instance (`lifecycle_notifier`)
13. **Lines 948–1035:** `validate_and_repair_cache()` definition
14. **Line 1038:** `validate_and_repair_cache()` — **executed at module load** (scans/repairs cache)
15. **Lines 1041–1121:** `load_kb_context()`, `call_deepseek()`, `detect_service_type()`
16. **Lines 1126–1733:** Pipeline functions (`start_pipeline`, `_run_background`, `_run_background_inner`, `_fallback_plan`)
17. **Lines 1738–1848:** Route definitions, static files, uvicorn startup

---

> **Document version:** 1.0  
> **Source file analyzed:** `/opt/data/telecom-orchestrator/poc/server_live.py` (1848 lines)  
> **Key:** All line numbers verified against actual code.
