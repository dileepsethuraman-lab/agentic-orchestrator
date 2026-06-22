# Telecom Orchestrator — API Specification

> **Version:** 2.0.0  
> **Base URL:** `http://0.0.0.0:8090`  
> **Source:** `poc/server_live.py`  
> **Framework:** FastAPI (Pydantic models)  
> **Backend Store:** diskcache (Redis-compatible)

---

## Table of Contents

1. [Pydantic Models](#1-pydantic-models)
   - [ProcessRequest](#11-processrequest)
   - [TraceStep](#12-tracestep)
   - [ProcessResponse](#13-processresponse)
   - [final_state Structure](#14-finalstate-structure)
2. [Endpoints](#2-endpoints)
   - [POST /api/process](#21-post-apiprocess)
   - [GET /api/process/{order_id}](#22-get-apiprocessorder_id)
   - [GET /api/patterns](#23-get-appatterns)
   - [GET /api/patterns/{pattern_id}](#24-get-appatternspattern_id)
   - [POST /api/patterns/teach](#25-post-appatternsteach)
   - [GET /api/notifications/{order_id}](#26-get-apinotificationsorder_id)
   - [GET /api/locks/status](#27-get-apilocksstatus)
   - [POST /api/locks/release](#28-post-apilocksrelease)
   - [GET /api/samples](#29-get-apisamples)
   - [GET /health](#210-get-health)
3. [TMF641 Notification Event Structures](#3-tmf641-notification-event-structures)
4. [Lifecycle States by Service Type](#4-lifecycle-states-by-service-type)

---

## 1. Pydantic Models

### 1.1 ProcessRequest

The request body for initiating orchestration.

| Field   | Type   | Required | Description                                          |
|---------|--------|----------|------------------------------------------------------|
| `prompt` | `str` | Yes (min_length=1) | The service request payload — structured TMF640 JSON or unstructured natural language text. |

**Model definition (from `server_live.py` line 319-320):**

```python
class ProcessRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
```

**Example (TMF640 structured JSON):**
```json
{
  "prompt": "{\"serviceId\":\"MSISDN-447700123456\",\"action\":\"activate\",\"characteristic\":[{\"name\":\"customerSegment\",\"value\":\"retail\"},{\"name\":\"slaTier\",\"value\":\"gold\"}]}"
}
```

**Example (unstructured text):**
```json
{
  "prompt": "activate new mobile voice service for retail customer with gold SLA: MSISDN 447700123456, IMSI 234151234567890, enable VoLTE with EVS codec"
}
```

---

### 1.2 TraceStep

A single pipeline stage trace entry. Returned in the `trace[]` array of `ProcessResponse`.

| Field        | Type  | Description                                                      |
|--------------|-------|------------------------------------------------------------------|
| `stage`      | `str` | Pipeline stage name: `DETECT`, `MASK`, `CACHE`, `RAG`, `LLM`, `HYDRATE`, `LOCK`, `MERGE`, `VALIDATE`, `EXECUTE`, `NOTIFY`, `VERIFY`, `ERROR` |
| `status`     | `str` | `done`, `running`, `error`, `blocked`                            |
| `title`      | `str` | Human-readable step title                                        |
| `detail`     | `str` | Detailed explanation of goal/input/expected/actual/output        |
| `color`      | `str` | UI display color: `cyan`, `violet`, `green`, `amber`, `blue`, `red` |
| `icon`       | `str` | UI emoji icon                                                    |
| `elapsed_ms` | `int` | Milliseconds elapsed since pipeline start (default: 0)           |

**Model definition (from `server_live.py` line 322-324):**

```python
class TraceStep(BaseModel):
    stage: str; status: str; title: str; detail: str
    color: str; icon: str; elapsed_ms: int = 0
```

**Example:**
```json
{
  "stage": "DETECT",
  "status": "done",
  "title": "Format Detection",
  "detail": "Goal: Classify the incoming request as structured (TMF640/TMF641 JSON) or unstructured natural language text.\nInput: Raw prompt string (first character check)\nExpected: '{' prefix → structured JSON path\nActual: Detected structured JSON → routing to TMF640 pipeline",
  "color": "cyan",
  "icon": "🔍",
  "elapsed_ms": 0
}
```

---

### 1.3 ProcessResponse

Returned by both `POST /api/process` and `GET /api/process/{order_id}`.

| Field        | Type              | Description                                                       |
|--------------|-------------------|-------------------------------------------------------------------|
| `order_id`   | `str`             | Unique order ID (format: `PO-XXXXXXXX` where X is uppercase hex)  |
| `format`     | `str`             | Request format: `"tmf640"`, `"unstructured"`, or `"invalid"`      |
| `status`     | `str`             | Pipeline status: `"processing"`, `"completed"`, `"error"`, `"blocked"` |
| `trace`      | `list[TraceStep]` | Ordered array of pipeline stage trace entries                     |
| `total_ms`   | `int`             | Total elapsed milliseconds since pipeline start                   |
| `final_state`| `dict` \| `null`  | Present only when `status == "completed"`; see [§1.4](#14-finalstate-structure) |
| `started_at` | `str`             | ISO 8601 timestamp of pipeline start (default: `""`)              |

**Model definition (from `server_live.py` line 326-330):**

```python
class ProcessResponse(BaseModel):
    order_id: str; format: str; status: str
    trace: list[TraceStep]; total_ms: int
    final_state: Optional[dict] = None
    started_at: str = ""
```

---

### 1.4 final_state Structure

Populated when `status == "completed"`. Contains the full service provisioning result.

| Field                 | Type        | Description                                                               | Source (line)     |
|-----------------------|-------------|---------------------------------------------------------------------------|--------------------|
| `serviceId`           | `str`       | Generated service ID (format: `SVC-XXXXXX`)                               | line 1690          |
| `state`               | `str`       | Final state: `"ACTIVE"`                                                   | line 1690          |
| `workflowsExecuted`   | `int`       | Number of workflows executed                                              | line 1691          |
| `resourcesProvisioned`| `int`       | Number of configuration parameters applied                                | line 1691          |
| `networkElements`     | `list[dict]`| Array of provisioned network element objects (see below)                  | line 1692          |
| `patternId`           | `str`\|`null`| Pattern identifier used (learned pattern, cache hit, or null)            | line 1693          |
| `patternConfidence`   | `float`     | Pattern confidence score (0.0–1.0)                                        | line 1694          |
| `llmUsed`             | `bool`      | Whether Deepseek LLM was invoked (`true` on cache miss, `false` on hit)   | line 1695          |
| `patternMatch`        | `dict`\|`null`| Detailed pattern match/miss comparison (see below)                       | line 1696          |
| `subscriberId`        | `str`       | Stable subscriber identifier (derived from MSISDN, serviceId, or hash)    | line 1697          |
| `subscriberDiff`      | `dict`      | Change detection vs previous service model (see below)                    | line 1698          |
| `notificationCount`   | `int`       | Number of TMF641 lifecycle notifications emitted                          | line 1699          |
| `notifications`       | `list[dict]`| Array of TMF641 notification event objects (see [§3](#3-tmf641-notification-event-structures)) | line 1700 |

**networkElement object:**

| Field        | Type   | Description                                   |
|--------------|--------|-----------------------------------------------|
| `name`       | `str`  | NE name (e.g., `"HLR-HSS"`, `"PCRF-PCF"`)    |
| `type`       | `str`  | NE type from KB (e.g., `"HLR/HSS"`)           |
| `workflow`   | `str`  | Workflow that provisioned this NE             |
| `role`       | `str`  | Role description (e.g., `"Subscriber registry"`) |
| `attributes` | `dict` | Key-value attribute map (e.g., `{"msisdn": "447700123456", "imsi": "234151234567890", "status": "Configured"}`) |

**patternMatch object (on HIT):**

| Field                   | Type          | Description                                     |
|-------------------------|---------------|-------------------------------------------------|
| `result`                | `str`         | `"HIT"`                                         |
| `patternId`             | `str`         | Matched pattern ID                              |
| `patternLabel`          | `str`         | Human-readable pattern label                    |
| `confidence`            | `float`       | Pattern confidence (0.0–1.0)                    |
| `useCount`              | `int`         | Times pattern has been used                     |
| `triplesCount`          | `int`         | Number of RDF triples in pattern                |
| `resourcesCount`        | `int`         | Number of resources in pattern                  |
| `compareLogic`          | `str`         | Description of matching algorithm               |
| `requestChars`          | `dict`        | Service-defining characteristics from request   |
| `patternChars`          | `dict`        | Service-defining characteristics from pattern   |
| `matchedKeys`           | `list[str]`   | Keys that matched                               |
| `mismatchedKeys`        | `list[str]`   | Keys that mismatched                            |
| `extraKeys`             | `list[str]`   | Keys in request but not in pattern              |
| `excludedInstanceAttrs` | `list[str]`   | Instance attributes excluded from matching      |
| `score`                 | `float`       | Jaccard similarity score (0.0–1.0)              |

**patternMatch object (on MISS):**

| Field                   | Type          | Description                                     |
|-------------------------|---------------|-------------------------------------------------|
| `result`                | `str`         | `"MISS"`                                        |
| `patternsInStore`       | `int`         | Total patterns in the store                     |
| `patternsForService`    | `int`         | Patterns for this service type                  |
| `requestChars`          | `dict`        | Service-defining characteristics from request   |
| `excludedInstanceAttrs` | `list[str]`   | Instance attributes excluded from matching      |
| `compareLogic`          | `str`         | Description of matching algorithm               |

**subscriberDiff object:**

| Field                  | Type     | Description                                               |
|------------------------|----------|-----------------------------------------------------------|
| `hasPrevious`           | `bool`  | Whether a previous service model exists                   |
| `isFirstRun`            | `bool`  | `true` if this is the first provisioning for this subscriber |
| `hasChanges`            | `bool`  | Whether any characteristics or NE attributes changed      |
| `changedAttributes`     | `dict`  | Changed characteristic-level attributes: `{key: {"from": old, "to": new}}` |
| `networkElementDiffs`   | `dict`  | Per-NE attribute diffs: `{ne_name: {attr: {"from": old, "to": new}}}` |

---

## 2. Endpoints

### 2.1 POST /api/process

Initiate orchestration for a service request.

| Aspect           | Details                                                      |
|------------------|--------------------------------------------------------------|
| **Method**       | `POST`                                                       |
| **Path**         | `/api/process`                                              |
| **Content-Type** | `application/json`                                          |
| **Request Body** | [`ProcessRequest`](#11-processrequest)                       |
| **Response**     | [`ProcessResponse`](#13-processresponse) (pipeline starts synchronously, completes in background) |

**Behavior:**
- Runs stages DETECT → MASK → CACHE synchronously, returns immediately with `status: "processing"`.
- Background thread completes LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY → NOTIFY.
- Poll `GET /api/process/{order_id}` to retrieve the completed result.

**Status Codes:**

| Code | Meaning               | When                                          |
|------|-----------------------|-----------------------------------------------|
| 200  | OK                    | Pipeline started; response includes `order_id` |
| 422  | Unprocessable Entity  | Invalid request body (e.g., empty prompt)     |

**Example — TMF640 structured JSON:**
```bash
curl -X POST http://0.0.0.0:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "{\"serviceId\":\"MSISDN-447700123456\",\"action\":\"activate\",\"characteristic\":[{\"name\":\"customerSegment\",\"value\":\"retail\"},{\"name\":\"slaTier\",\"value\":\"gold\"},{\"name\":\"msisdn\",\"value\":\"447700123456\"}]}"
  }'
```

**Example — Unstructured text:**
```bash
curl -X POST http://0.0.0.0:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "activate new mobile voice service for retail customer with gold SLA: MSISDN 447700123456, IMSI 234151234567890"
  }'
```

**Example response (immediate, while still processing):**
```json
{
  "order_id": "PO-A1B2C3D4",
  "format": "tmf640",
  "status": "processing",
  "trace": [
    {
      "stage": "DETECT",
      "status": "done",
      "title": "Format Detection",
      "detail": "Goal: Classify the incoming request...\nActual: Detected structured JSON → routing to TMF640 pipeline",
      "color": "cyan",
      "icon": "🔍",
      "elapsed_ms": 0
    },
    {
      "stage": "MASK",
      "status": "done",
      "title": "Data Masking — 1 Identifiers Tokenized",
      "detail": "Goal: Strip all sensitive identifiers...\nActual: 1 identifiers tokenized",
      "color": "violet",
      "icon": "🛡️",
      "elapsed_ms": 5
    },
    {
      "stage": "CACHE",
      "status": "done",
      "title": "Pattern Store — MISS",
      "detail": "Goal: Query the RDF pattern store...\nActual: No match...",
      "color": "amber",
      "icon": "📡",
      "elapsed_ms": 10
    },
    {
      "stage": "LLM",
      "status": "done",
      "title": "Pipeline Dispatched — Background Processing",
      "detail": "Goal: Continue orchestration in background thread...",
      "color": "green",
      "icon": "⏳",
      "elapsed_ms": 15
    }
  ],
  "total_ms": 15,
  "final_state": null,
  "started_at": "2026-06-22T12:00:00.123456"
}
```

---

### 2.2 GET /api/process/{order_id}

Poll for pipeline result. Returns partial trace while processing, full result when completed.

| Aspect           | Details                                                      |
|------------------|--------------------------------------------------------------|
| **Method**       | `GET`                                                        |
| **Path**         | `/api/process/{order_id}`                                    |
| **Path Params**  | `order_id` (str) — Order ID from `POST /api/process`         |
| **Response**     | [`ProcessResponse`](#13-processresponse) with `final_state` populated when `status == "completed"` |

**Status Codes:**

| Code | Meaning          | When                        |
|------|------------------|-----------------------------|
| 200  | OK               | Order found                 |
| 404  | Not Found        | Order ID not in job store   |

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/api/process/PO-A1B2C3D4
```

**Example response (completed):**
```json
{
  "order_id": "PO-A1B2C3D4",
  "format": "tmf640",
  "status": "completed",
  "trace": [ /* ... full trace of all stages ... */ ],
  "total_ms": 45230,
  "final_state": {
    "serviceId": "SVC-F7A3B1",
    "state": "ACTIVE",
    "workflowsExecuted": 6,
    "resourcesProvisioned": 20,
    "networkElements": [
      {
        "name": "HLR-HSS",
        "type": "HLR/HSS",
        "workflow": "HLR_Provisioning",
        "role": "Subscriber registry",
        "attributes": {
          "msisdn": "447700123456",
          "imsi": "234151234567890",
          "subscriber_profile": "Gold_VoLTE_IntlRoam",
          "roaming_profile": "WorldZone1",
          "status": "Configured"
        }
      }
    ],
    "patternId": "pat:mobile:a1b2c3d4e5f6",
    "patternConfidence": 0.35,
    "llmUsed": true,
    "patternMatch": { /* ... see §1.4 ... */ },
    "subscriberId": "MSISDN-447700123456",
    "subscriberDiff": {
      "hasPrevious": false,
      "isFirstRun": true,
      "hasChanges": false,
      "changedAttributes": {},
      "networkElementDiffs": {}
    },
    "notificationCount": 6,
    "notifications": [ /* ... see §3 ... */ ]
  },
  "started_at": "2026-06-22T12:00:00.123456"
}
```

---

### 2.3 GET /api/patterns

List all learned patterns with metadata.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/patterns`                                      |
| **Response**     | `{"patterns": [...]}` — array of pattern metadata objects |

**Status Codes:**

| Code | Meaning | When        |
|------|---------|-------------|
| 200  | OK      | Always      |

**Pattern metadata object:**

| Field           | Type    | Description                                |
|-----------------|---------|--------------------------------------------|
| `id`            | `str`   | Pattern identifier                         |
| `service_type`  | `str`   | `"mobile"`, `"l3vpn"`, `"sdwan"`, `"broadband"` |
| `label`         | `str`   | Human-readable label                       |
| `confidence`    | `float` | Confidence score (0.0–1.0)                 |
| `use_count`     | `int`   | Number of times used                       |
| `triples_count` | `int`   | Number of RDF triples                      |
| `source`        | `str`   | `"auto"`, `"teach"`, or `"kb"`             |
| `last_used`     | `str`   | ISO 8601 timestamp of last use             |

Results are sorted by confidence (descending) then use_count (descending).

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/api/patterns
```

**Example response:**
```json
{
  "patterns": [
    {
      "id": "pat:mobile:a1b2c3d4e5f6",
      "service_type": "mobile",
      "label": "mobile | retail/gold",
      "confidence": 0.85,
      "use_count": 12,
      "triples_count": 42,
      "source": "auto",
      "last_used": "2026-06-22T12:05:00.123456"
    },
    {
      "id": "pat:mobile:kb-seed-0001",
      "service_type": "mobile",
      "label": "mobile | ?/?",
      "confidence": 0.25,
      "use_count": 0,
      "triples_count": 30,
      "source": "kb",
      "last_used": ""
    }
  ]
}
```

---

### 2.4 GET /api/patterns/{pattern_id}

Get full pattern details including RDF triples and resource definitions.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/patterns/{pattern_id}`                         |
| **Path Params**  | `pattern_id` (str) — Pattern ID                      |
| **Response**     | Full `PatternNode.to_dict()` object                  |

**Status Codes:**

| Code | Meaning    | When              |
|------|------------|-------------------|
| 200  | OK         | Pattern found     |
| 404  | Not Found  | Pattern not found |

**Response fields:**

| Field            | Type         | Description                                     |
|------------------|--------------|-------------------------------------------------|
| `id`             | `str`        | Pattern ID                                      |
| `service_type`   | `str`        | Service type                                    |
| `label`          | `str`        | Human-readable label                            |
| `characteristics`| `dict`       | Service-defining characteristics                |
| `triples`        | `list[list]` | RDF triples `[subject, predicate, object]`      |
| `resources`      | `list[dict]` | Resource bindings with attributes               |
| `confidence`     | `float`      | Confidence score (rounded to 2 decimal places)  |
| `use_count`      | `int`        | Usage count                                     |
| `created_at`     | `str`        | ISO 8601 creation timestamp                     |
| `last_used`      | `str`        | ISO 8601 last-use timestamp                     |
| `source`         | `str`        | `"auto"`, `"teach"`, or `"kb"`                  |

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/api/patterns/pat:mobile:a1b2c3d4e5f6
```

**Example response:**
```json
{
  "id": "pat:mobile:a1b2c3d4e5f6",
  "service_type": "mobile",
  "label": "mobile | retail/gold",
  "characteristics": {
    "customerSegment": "retail",
    "slaTier": "gold",
    "productId": "mobile-voice"
  },
  "triples": [
    ["pat:mobile:a1b2c3d4e5f6", "rdf:type", "service:MobileVoice"],
    ["pat:mobile:a1b2c3d4e5f6", "orch:hascustomerSegment", "retail"],
    ["pat:mobile:a1b2c3d4e5f6", "orch:hasslaTier", "gold"],
    ["pat:mobile:a1b2c3d4e5f6", "orch:requiresResource", "res:HLR-HSS"],
    ["res:HLR-HSS", "orch:provisionedBy", "wf:HLR_Provisioning"],
    ["res:HLR-HSS", "orch:hasAttribute", "msisdn=447700123456"]
  ],
  "resources": [
    {
      "name": "HLR-HSS",
      "workflow": "HLR_Provisioning",
      "role": "Subscriber registry",
      "attributes": {
        "msisdn": "447700123456",
        "imsi": "234151234567890",
        "subscriber_profile": "Gold_VoLTE_IntlRoam",
        "roaming_profile": "WorldZone1"
      }
    }
  ],
  "confidence": 0.85,
  "use_count": 12,
  "created_at": "2026-06-20T10:00:00.000000",
  "last_used": "2026-06-22T12:05:00.123456",
  "source": "auto"
}
```

---

### 2.5 POST /api/patterns/teach

Teach the engine a new pattern via RDF triples. High initial confidence (0.9).

| Aspect           | Details                                                  |
|------------------|----------------------------------------------------------|
| **Method**       | `POST`                                                   |
| **Path**         | `/api/patterns/teach`                                    |
| **Content-Type** | `application/json`                                       |
| **Request Body** | `{"triples": [["subject", "predicate", "object"], ...]}` |
| **Response**     | `{"status": "learned", "pattern": {...}}`                |

**Status Codes:**

| Code | Meaning              | When                     |
|------|----------------------|--------------------------|
| 200  | OK                   | Pattern learned          |
| 400  | Bad Request          | Missing `triples` array  |

**Request format requirements:**
- `triples`: Required array of `[subject, predicate, object]` arrays.
- Predicates like `rdf:type`, `orch:has*`, `orch:requiresResource` define the service type, characteristics, and resource bindings.
- Service type is auto-detected from `rdf:type` predicate values (e.g., `service:MobileVoice` → `mobile`).

**Example:**
```bash
curl -X POST http://0.0.0.0:8090/api/patterns/teach \
  -H "Content-Type: application/json" \
  -d '{
    "triples": [
      ["my-pattern", "rdf:type", "service:MobileVoice"],
      ["my-pattern", "orch:hasSegment", "enterprise"],
      ["my-pattern", "orch:hasSLA", "gold"],
      ["my-pattern", "orch:requiresResource", "res:HLR"],
      ["res:HLR", "orch:provisionedBy", "wf:HLR_Provisioning"]
    ]
  }'
```

**Example response:**
```json
{
  "status": "learned",
  "pattern": {
    "id": "pat:taught:a1b2c3d4e5f6",
    "service_type": "mobile",
    "label": "mobile | Segment=enterprise / SLA=gold",
    "characteristics": {
      "Segment": "enterprise",
      "SLA": "gold"
    },
    "triples": [ /* ... */ ],
    "resources": [],
    "confidence": 0.9,
    "use_count": 0,
    "created_at": "2026-06-22T12:10:00.000000",
    "last_used": "2026-06-22T12:10:00.000000",
    "source": "teach"
  }
}
```

---

### 2.6 GET /api/notifications/{order_id}

Retrieve TMF641 lifecycle notifications for a completed order.

| Aspect           | Details                                                  |
|------------------|----------------------------------------------------------|
| **Method**       | `GET`                                                    |
| **Path**         | `/api/notifications/{order_id}`                          |
| **Path Params**  | `order_id` (str) — Order ID                              |
| **Response**     | `{"orderId": "...", "notifications": [...], "count": N}` |

**Status Codes:**

| Code | Meaning          | When                                  |
|------|------------------|---------------------------------------|
| 200  | OK               | Order found (may have empty notifications if still processing) |
| 404  | Not Found        | Order ID not in job store             |

**Still-processing response (200):**
```json
{
  "notifications": [],
  "message": "Pipeline still processing"
}
```

**Completed response (200):**
```json
{
  "orderId": "PO-A1B2C3D4",
  "notifications": [ /* ... see §3 ... */ ],
  "count": 6
}
```

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/api/notifications/PO-A1B2C3D4
```

---

### 2.7 GET /api/locks/status

List all active subscriber locks.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/locks/status`                                  |
| **Response**     | `{"activeLocks": N, "locks": [...]}`                 |

**Status Codes:**

| Code | Meaning | When   |
|------|---------|--------|
| 200  | OK      | Always |

**Lock object:**

| Field           | Type    | Description                                |
|-----------------|---------|--------------------------------------------|
| `key`           | `str`   | Cache key (`lock:sub:{subscriberId}`)      |
| `subscriberId`  | `str`   | Subscriber ID                              |
| `workerId`      | `str`   | Order ID holding the lock                  |
| `acquiredAt`    | `float` | Unix timestamp when lock was acquired      |
| `ageSeconds`    | `float` | Seconds since lock acquisition             |

Locks auto-expire after 30 seconds (preventing deadlock if worker crashes).

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/api/locks/status
```

**Example response:**
```json
{
  "activeLocks": 1,
  "locks": [
    {
      "key": "lock:sub:MSISDN-447700123456",
      "subscriberId": "MSISDN-447700123456",
      "workerId": "PO-A1B2C3D4",
      "acquiredAt": 1749153600.123,
      "ageSeconds": 5.2
    }
  ]
}
```

---

### 2.8 POST /api/locks/release

Admin endpoint to force-release a subscriber lock. Useful if a worker crashes and leaves a stale lock.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `POST`                                               |
| **Path**         | `/api/locks/release`                                 |
| **Content-Type** | `application/json`                                   |
| **Request Body** | `{"subscriberId": "..."}`                            |
| **Response**     | `{"status": "released", "subscriberId": "..."}`      |

**Status Codes:**

| Code | Meaning        | When                        |
|------|----------------|-----------------------------|
| 200  | OK             | Lock released               |
| 400  | Bad Request    | Missing `subscriberId`      |

**Example:**
```bash
curl -X POST http://0.0.0.0:8090/api/locks/release \
  -H "Content-Type: application/json" \
  -d '{"subscriberId": "MSISDN-447700123456"}'
```

**Example response:**
```json
{
  "status": "released",
  "subscriberId": "MSISDN-447700123456"
}
```

---

### 2.9 GET /api/samples

Return pre-built sample request payloads for testing. Useful for populating the frontend "Examples" dropdown.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/samples`                                       |
| **Response**     | `{"samples": [...]}`                                 |

**Status Codes:**

| Code | Meaning | When   |
|------|---------|--------|
| 200  | OK      | Always |

**Sample object:**

| Field   | Type | Description                                          |
|---------|------|------------------------------------------------------|
| `label` | `str`| Human-readable description of the sample             |
| `text`  | `str`| The complete request payload (JSON or plain text)    |

**Available samples:**
1. TMF640 — Activate Mobile Voice (Gold)
2. TMF640 — Activate Mobile Data (Platinum)
3. Unstructured — Mobile Voice Activation
4. TMF640 — Activate L3VPN (Enterprise Platinum)
5. TMF640 — Activate SD-WAN (Dual Transport)
6. TMF641 — ServiceOrder Broadband (FTTH Silver)
7. Security Test — Blocked Keyword

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/api/samples
```

---

### 2.10 GET /health

Health check endpoint.

| Aspect           | Details                                                  |
|------------------|----------------------------------------------------------|
| **Method**       | `GET`                                                    |
| **Path**         | `/health`                                                |
| **Response**     | `{"status": "ok", "cache_size": N, "redis_backend": "diskcache"}` |

**Status Codes:**

| Code | Meaning | When   |
|------|---------|--------|
| 200  | OK      | Always |

**Example:**
```bash
curl -X GET http://0.0.0.0:8090/health
```

**Example response:**
```json
{
  "status": "ok",
  "cache_size": 128,
  "redis_backend": "diskcache"
}
```

---

## 3. TMF641 Notification Event Structures

Published lifecycle notifications follow the TMF641 v4.1.0 specification. The engine emits two types of notification events as it walks the KB-defined lifecycle for a service type.

### 3.1 ServiceOrderMilestoneEvent

Emitted for each intermediate lifecycle state (all states except the final ACTIVE state). The service order remains `inProgress`.

**Schema:**

```json
{
  "eventId": "evt-{order_id}-{milestone_name}",
  "eventTime": "2026-06-22T12:00:05.123456Z",
  "eventType": "ServiceOrderMilestoneEvent",
  "correlationId": "corr-{order_id}",
  "domain": "ServiceFulfillment",
  "priority": "normal",
  "timeOcurred": "2026-06-22T12:00:05.123456Z",
  "title": "Milestone: {state_name}",
  "description": "Service order reached milestone: {state_name}",
  "event": {
    "serviceOrder": {
      "id": "{order_id}",
      "href": "/api/tmf641/serviceOrder/{order_id}",
      "state": "inProgress",
      "externalId": "{order_id}",
      "category": "{service_type}",
      "milestone": [
        {
          "id": "ms-{order_id}-{state_name}",
          "name": "{state_name}",
          "description": "State transition: {state_name}",
          "message": "Orchestrator reached lifecycle state: {state_name}",
          "milestoneDate": "2026-06-22T12:00:05.123456Z",
          "status": "achieved"
        }
      ]
    }
  }
}
```

**Example — Mobile service DESIGNED milestone:**
```json
{
  "eventId": "evt-PO-A1B2C3D4-DESIGNED",
  "eventTime": "2026-06-22T12:00:01.000000Z",
  "eventType": "ServiceOrderMilestoneEvent",
  "correlationId": "corr-PO-A1B2C3D4",
  "domain": "ServiceFulfillment",
  "priority": "normal",
  "timeOcurred": "2026-06-22T12:00:01.000000Z",
  "title": "Milestone: DESIGNED",
  "description": "Service order reached milestone: DESIGNED",
  "event": {
    "serviceOrder": {
      "id": "PO-A1B2C3D4",
      "href": "/api/tmf641/serviceOrder/PO-A1B2C3D4",
      "state": "inProgress",
      "externalId": "PO-A1B2C3D4",
      "category": "mobile",
      "milestone": [
        {
          "id": "ms-PO-A1B2C3D4-DESIGNED",
          "name": "DESIGNED",
          "description": "State transition: DESIGNED",
          "message": "Orchestrator reached lifecycle state: DESIGNED",
          "milestoneDate": "2026-06-22T12:00:01.000000Z",
          "status": "achieved"
        }
      ]
    }
  }
}
```

### 3.2 ServiceOrderStateChangeEvent

Emitted for the final ACTIVE state. Transitions the order from `inProgress` to `completed`.

**Schema:**

```json
{
  "eventId": "evt-{order_id}-ACTIVE",
  "eventTime": "2026-06-22T12:00:45.000000Z",
  "eventType": "ServiceOrderStateChangeEvent",
  "correlationId": "corr-{order_id}",
  "domain": "ServiceFulfillment",
  "priority": "normal",
  "timeOcurred": "2026-06-22T12:00:45.000000Z",
  "title": "Order completed",
  "description": "Service order state changed to: completed",
  "event": {
    "serviceOrder": {
      "id": "{order_id}",
      "href": "/api/tmf641/serviceOrder/{order_id}",
      "state": "completed",
      "externalId": "{order_id}",
      "category": "{service_type}",
      "completionDate": "2026-06-22T12:00:45.000000Z"
    }
  }
}
```

**Example — Mobile service ACTIVE state change:**
```json
{
  "eventId": "evt-PO-A1B2C3D4-ACTIVE",
  "eventTime": "2026-06-22T12:00:45.000000Z",
  "eventType": "ServiceOrderStateChangeEvent",
  "correlationId": "corr-PO-A1B2C3D4",
  "domain": "ServiceFulfillment",
  "priority": "normal",
  "timeOcurred": "2026-06-22T12:00:45.000000Z",
  "title": "Order completed",
  "description": "Service provisioning complete. Final state: ACTIVE. All network elements configured and verified.",
  "event": {
    "serviceOrder": {
      "id": "PO-A1B2C3D4",
      "href": "/api/tmf641/serviceOrder/PO-A1B2C3D4",
      "state": "completed",
      "externalId": "PO-A1B2C3D4",
      "category": "mobile",
      "completionDate": "2026-06-22T12:00:45.000000Z"
    }
  }
}
```

### 3.3 TMF641 Lifecycle → Event Mapping

All events for a single orchestration share the same `correlationId` for distributed traceability.

| TMF Event Type                  | Trigger                 | ServiceOrder State | Lifecycle States                             |
|---------------------------------|-------------------------|---------------------|----------------------------------------------|
| `ServiceOrderMilestoneEvent`    | Intermediate milestone  | `inProgress`        | DESIGNED, FEASIBILITY_CHECKED, HLR_PROVISIONED, IMS_REGISTERED, PCRF_CONFIGURED, etc. |
| `ServiceOrderStateChangeEvent`  | Final state transition  | `completed`         | ACTIVE                                       |

**Reference:** `knowledge-base/reference/tmf-notification-schemas.md`  
**Implementation:** `poc/server_live.py` class `LifecycleNotifier` (lines 785–945)

---

## 4. Lifecycle States by Service Type

Each service type has a KB-defined lifecycle that drives milestone notification emission. Derived from `SERVICE_RESOURCES` (lines 714–761).

| Service Type | Lifecycle States                                                                                     |
|--------------|------------------------------------------------------------------------------------------------------|
| `mobile`     | DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE         |
| `l3vpn`      | DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE |
| `sdwan`      | DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE       |
| `broadband`  | DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE              |
