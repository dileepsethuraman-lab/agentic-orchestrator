# End-State Component Specification — Telecom Agentic Orchestration Engine

> **Version:** 1.0.0  
> **Date:** 2026-06-23  
> **Status:** Production Target Architecture  
> **PoC Baseline:** `poc/server_live.py` (1,848 lines, 12-stage pipeline)  
> **Design References:**  
> - `knowledge-base/reference/solution-design-crm-integration.md` — CRM integration, PostgreSQL schema, webhook delivery  
> - `knowledge-base/reference/orchestration-brain-design.md` — 6-stage brain with pattern matching + learning  
> - `knowledge-base/reference/implementation-guide.md` — 7-phase build plan, MCP servers, cron jobs  
> - `knowledge-base/system-docs/architecture/blueprint.md` — PoC architecture blueprint  
> - `knowledge-base/system-docs/components/backend-components.md` — PoC backend class catalog  
> - `knowledge-base/system-docs/components/frontend-components.md` — PoC frontend component tree  
> - `knowledge-base/system-docs/api/api-spec.md` — API routes and Pydantic models  

---

## 1. Modular Directory Structure (`src/`)

```
src/
├── api/
│   ├── __init__.py
│   ├── gateway.py              # FastAPI app, middleware, CORS
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── tmf622.py           # Product Order routes (TMF622)
│   │   ├── tmf641.py           # Service Order routes (TMF641)
│   │   ├── tmf640.py           # Service Activation routes (TMF640)
│   │   ├── tmf638.py           # Service Inventory routes (TMF638)
│   │   ├── tmf639.py           # Resource Inventory routes (TMF639)
│   │   ├── patterns.py         # Pattern management routes
│   │   ├── subscribers.py      # Subscriber model routes
│   │   ├── locks.py            # Lock management routes
│   │   ├── notifications.py    # Notification retrieval
│   │   ├── health.py           # Health + metrics
│   │   └── webhooks.py         # CRM webhook configuration
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py             # API key + OAuth2
│       ├── rate_limit.py       # Redis-backed rate limiter
│       └── logging.py          # Request/response structured logging
├── core/
│   ├── __init__.py
│   ├── orchestrator_brain.py   # Main orchestration engine (6-stage agentic brain)
│   ├── pipeline.py             # 14-stage pipeline definitions
│   ├── order_decomposer.py     # TMF622 → TMF641 decomposition
│   ├── data_masker.py          # Sensitive data tokenization
│   └── validation_gateway.py   # Hard-gate security validation
├── knowledge/
│   ├── __init__.py
│   ├── pattern_engine.py       # RDF pattern store + matching + learning
│   ├── kb_loader.py            # KB file reader + context builder
│   ├── service_resources.py    # KB → required resource mapping
│   └── ontology.py             # Core ontology query interface
├── models/
│   ├── __init__.py
│   ├── service_model.py        # Service model store (persistent subscriber state)
│   ├── resource_model.py       # Resource model (device, VRF, IP allocations)
│   ├── subscriber_lock.py      # Advisory per-subscriber locking
│   └── inventory.py            # PostgreSQL-backed inventory CRUD
├── integration/
│   ├── __init__.py
│   ├── mcp_dispatcher.py       # MCP server dispatch + result aggregation
│   ├── netbox_client.py        # NetBox API client (IPAM/DCIM)
│   ├── ansible_client.py       # Ansible runner client
│   ├── nso_client.py           # Cisco NSO client (YANG service activation)
│   ├── osm_client.py           # OSM NFV orchestrator client
│   └── device_drivers/
│       ├── __init__.py
│       ├── cisco_ios.py        # IOS/IOS-XE/IOS-XR NETCONF/CLI
│       ├── juniper_junos.py    # Junos NETCONF/CLI
│       └── nokia_sros.py       # Nokia SR OS CLI/NETCONF
├── notification/
│   ├── __init__.py
│   ├── lifecycle_notifier.py   # TMF641 event emitter (milestones + state changes)
│   ├── webhook_manager.py      # CRM callback dispatcher (retry + dead-letter)
│   └── gateway_notifier.py     # Telegram/Discord/Slack alerting
├── cron/
│   ├── __init__.py
│   ├── service_assurance.py    # Periodic health checks (every 30m)
│   ├── resource_discovery.py   # Network scan + inventory sync (daily at 02:00)
│   └── capacity_management.py  # Capacity forecast + trend report (weekly)
└── frontend/
    ├── dashboard/              # React/Next.js production dashboard
    │   ├── pages/
    │   │   ├── index.tsx        # Main orchestration console
    │   │   ├── orders.tsx       # Order management
    │   │   ├── inventory.tsx    # Service/resource inventory browser
    │   │   ├── patterns.tsx     # Pattern analysis + management
    │   │   └── settings.tsx     # Webhook + notification settings
    │   ├── components/
    │   │   ├── TraceViewer.tsx  # Real-time pipeline trace (polling → WebSocket upgrade)
    │   │   ├── NetworkElementCards.tsx  # NE state grid
    │   │   ├── PatternAnalysis.tsx      # Pattern match/confidence panel
    │   │   ├── NotificationTimeline.tsx # TMF641 lifecycle timeline
    │   │   ├── OrderConsole.tsx         # Order lifecycle dashboard
    │   │   ├── InventoryBrowser.tsx     # Service + resource inventory
    │   │   ├── SampleSelector.tsx       # Pre-built request samples
    │   │   └── DiffViewer.tsx           # Subscriber model diff viewer
    │   └── api/
    │       └── client.ts        # API client wrapper (fetch → WebSocket upgrade)
    └── trace_viewer/           # Standalone trace visualization
        ├── index.html
        └── viewer.js
```

---

## 2. Component Specifications

### 2.1 API Layer — `src/api/`

#### 2.1.1 `gateway.py` — FastAPI Application Gateway

| Aspect | Detail |
|--------|--------|
| **Purpose** | Initialize FastAPI app with middleware stack, CORS, static file serving, and lifecycle hooks. Single entry point for all HTTP traffic. |
| **Responsibility** | App factory, middleware registration, lifespan events (Redis/DB connection pools), CORS policy, static file mount for production dashboard. |

**Key Classes & Functions:**

```python
def create_app() -> FastAPI:
    """Factory: build and configure the FastAPI application."""

class AppConfig:
    """Application configuration from environment / YAML."""
    title: str = "Telecom Agentic Orchestration Engine"
    version: str
    cors_origins: list[str]
    auth_mode: str  # "api_key" | "oauth2" | "both"
    rate_limit_enabled: bool
```

**Integration Points:**
- **Depends on:** `middleware.auth`, `middleware.rate_limit`, `middleware.logging`
- **Depended on by:** All route modules (registered via `app.include_router()`)
- **External**: nginx reverse proxy terminates TLS; gateway binds to `127.0.0.1:8000`

**Error Handling:**
- Global exception handler catches unhandled exceptions → JSON `{"error": "...", "code": 500}`
- FastAPI built-in request validation via Pydantic models
- Health endpoint returns DB/Redis connectivity status

**Script Reference:**
```bash
uvicorn src.api.gateway:create_app --factory --host 0.0.0.0 --port 8000
gunicorn src.api.gateway:create_app --factory -w 4 -k uvicorn.workers.UvicornWorker
```

---

#### 2.1.2 `routes/tmf622.py` — Product Order Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | Implement TMF622 Product Ordering API — CRM-facing entry point. Accept product orders, decompose into service orders, return 202 Accepted. |
| **Responsibility** | Validate product order payload against JSON Schema, check product catalog, call `OrderDecomposer`, enqueue child service orders to Redis, return status URL. |

**Key Methods:**

```python
@router.post("/tmf622/productOrder", response_model=ProductOrderResponse)
async def create_product_order(request: ProductOrderRequest) -> ProductOrderResponse:
    """Accept TMF622 product order, decompose, queue, return 202."""

@router.get("/tmf622/productOrder/{order_id}", response_model=ProductOrderResponse)
async def get_product_order(order_id: str) -> ProductOrderResponse:
    """Retrieve product order status and child service order references."""

@router.post("/tmf622/productOrder/{order_id}/cancel")
async def cancel_product_order(order_id: str) -> CancelResponse:
    """Cancel a product order and all descendant service orders."""
```

**Input/Output:**

| Direction | Structure | Description |
|-----------|-----------|-------------|
| Input | `ProductOrderRequest` | TMF622 payload with `externalId`, `productOrderItem[]`, `relatedParty[]`, `characteristic[]` |
| Output | `ProductOrderResponse` | `id`, `href`, `state`, `externalId`, `serviceOrder[]`, `expectedCompletionDate` |

**Database Tables:** `product_orders` (PostgreSQL)

**Integration Points:**
- Calls `core.order_decomposer.decompose()` to split into service orders
- Calls `models.inventory` to write order record
- Enqueues to Redis task queue via `integration.mcp_dispatcher`

**Error Handling:**
- `409 Conflict` if `externalId` already exists (idempotency guard)
- `422 Unprocessable Entity` if product not found in catalog
- `400 Bad Request` if required characteristics missing

**Script Reference:**
```bash
curl -X POST https://orchestrator.example.com/api/tmf622/productOrder \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @order.json
```

---

#### 2.1.3 `routes/tmf641.py` — Service Order Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | TMF641 Service Ordering API — query, cancel, and list service orders. |
| **Responsibility** | Expose GET/POST for service orders with full audit log and resource references. |

**Key Methods:**

```python
@router.get("/tmf641/serviceOrder/{order_id}", response_model=ServiceOrderResponse)
async def get_service_order(order_id: str) -> ServiceOrderResponse:
    """Full service order detail with audit log, child orders, resource refs."""

@router.get("/tmf641/serviceOrder", response_model=ServiceOrderListResponse)
async def list_service_orders(status: str = None, customer_id: str = None,
                               limit: int = 50, offset: int = 0):
    """List service orders with optional filters."""

@router.post("/tmf641/serviceOrder/{order_id}/cancel")
async def cancel_service_order(order_id: str) -> CancelResponse:
    """Cancel a service order and trigger rollback workflow."""
```

**Database Tables:** `service_orders`, `audit_log` (PostgreSQL)

---

#### 2.1.4 `routes/tmf640.py` — Service Activation Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | TMF640 Service Activation API — the primary ingress for provisioning requests. |
| **Responsibility** | Accept structured activation requests, validate characteristics, trigger pipeline. |

**Key Methods:**

```python
@router.post("/tmf640/serviceActivation", response_model=ProcessResponse)
async def activate_service(request: ServiceActivationRequest) -> ProcessResponse:
    """Accept TMF640 activation, classify service type, start pipeline."""

@router.get("/tmf640/serviceActivation/{activation_id}")
async def get_activation_status(activation_id: str) -> ProcessResponse:
    """Poll for activation status — equivalent to GET /api/process/{id}."""
```

---

#### 2.1.5 `routes/tmf638.py` — Service Inventory Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | TMF638 Service Inventory API — query provisioned services. |
| **Responsibility** | CRUD for service inventory entities; supports search by customer, type, state. |

**Key Methods:**

```python
@router.get("/tmf638/service/{service_id}")
async def get_service(service_id: str) -> ServiceResponse:
    """Retrieve service with all child resources."""

@router.get("/tmf638/service", response_model=ServiceListResponse)
async def list_services(customer_id: str = None, service_type: str = None,
                        state: str = None, limit: int = 50, offset: int = 0):
    """Search services with filters."""

@router.post("/tmf638/service/{service_id}/suspend")
async def suspend_service(service_id: str) -> StateChangeResponse:
    """Suspend an active service — triggers deprovisioning workflow."""

@router.post("/tmf638/service/{service_id}/terminate")
async def terminate_service(service_id: str) -> StateChangeResponse:
    """Terminate a service — full resource release."""
```

**Database Tables:** `service_inventory` (PostgreSQL)

---

#### 2.1.6 `routes/tmf639.py` — Resource Inventory Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | TMF639 Resource Inventory API — query provisioned resources. |
| **Responsibility** | CRUD for resource inventory; supports search by device, type, service ref. |

**Key Methods:**

```python
@router.get("/tmf639/resource/{resource_id}")
async def get_resource(resource_id: str) -> ResourceResponse:
    """Retrieve resource with configuration and parent references."""

@router.get("/tmf639/resource", response_model=ResourceListResponse)
async def list_resources(service_id: str = None, resource_type: str = None,
                         device_name: str = None, state: str = None,
                         limit: int = 50, offset: int = 0):
    """Search resources across all dimensions."""
```

**Database Tables:** `resource_inventory` (PostgreSQL)

---

#### 2.1.7 `routes/patterns.py` — Pattern Management Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | Admin API for viewing, teaching, and managing orchestration patterns. |

**Key Methods:**

```python
@router.get("/api/patterns")
async def list_patterns() -> PatternListResponse:
    """List all patterns with metadata (confidence, use_count, triples_count)."""

@router.get("/api/patterns/{pattern_id}")
async def get_pattern(pattern_id: str) -> PatternDetailResponse:
    """Full pattern detail including RDF triples and resources."""

@router.post("/api/patterns/teach")
async def teach_pattern(request: TeachPatternRequest) -> TeachResponse:
    """Teach the engine a new pattern via RDF triples — high confidence (0.9)."""

@router.delete("/api/patterns/{pattern_id}")
async def delete_pattern(pattern_id: str) -> DeleteResponse:
    """Admin: delete a deprecated or experimental pattern."""

@router.post("/api/patterns/{pattern_id}/promote")
async def promote_pattern(pattern_id: str) -> PatternDetailResponse:
    """Promote experimental pattern to active status."""
```

**Integration Points:**
- Calls `knowledge.pattern_engine.PatternEngine.teach()`
- Calls `knowledge.pattern_engine.PatternEngine.get()`
- Calls `knowledge.pattern_engine.PatternEngine.list_all()`

---

#### 2.1.8 `routes/subscribers.py` — Subscriber Model Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | Expose subscriber service models for inspection and diff viewing. |

**Key Methods:**

```python
@router.get("/api/subscribers/{subscriber_id}")
async def get_subscriber(subscriber_id: str) -> SubscriberModelResponse:
    """Retrieve the current service model for a subscriber."""

@router.get("/api/subscribers/{subscriber_id}/history")
async def get_subscriber_history(subscriber_id: str) -> list[SubscriberModelResponse]:
    """Retrieve version history for a subscriber's service model."""
```

---

#### 2.1.9 `routes/locks.py` — Lock Management Routes

| Aspect | Detail |
|--------|--------|
| **Purpose** | Admin endpoints for inspecting and releasing subscriber advisory locks. |

**Key Methods:**

```python
@router.get("/api/locks/status")
async def lock_status() -> LockStatusResponse:
    """List all active subscriber locks with worker_id and age."""

@router.post("/api/locks/release")
async def release_lock(request: LockReleaseRequest) -> ReleaseResponse:
    """Admin: force-release a subscriber lock (dangerous — use only for stuck workers)."""
```

---

#### 2.1.10 `routes/notifications.py` — Notification Retrieval

| Aspect | Detail |
|--------|--------|
| **Purpose** | Retrieve TMF lifecycle notifications for completed orders. |

**Key Methods:**

```python
@router.get("/api/notifications/{order_id}")
async def get_notifications(order_id: str) -> NotificationResponse:
    """Retrieve all TMF641 milestone and state change events for an order."""
```

---

#### 2.1.11 `routes/health.py` — Health + Metrics

| Aspect | Detail |
|--------|--------|
| **Purpose** | Kubernetes-compatible health checks + Prometheus metrics endpoint. |

**Key Methods:**

```python
@router.get("/health")
async def health() -> HealthResponse:
    """Liveness check: returns 200 if process is alive."""

@router.get("/healthz")
async def healthz() -> HealthResponse:
    """Liveness probe — always returns OK."""

@router.get("/readyz")
async def readyz() -> ReadyResponse:
    """Readiness probe — checks PostgreSQL + Redis connectivity."""

@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint — order throughput, latency, error rates."""
```

**Metrics Collected:**
```
orchestrator_orders_total{status="completed|failed|blocked"}     # counter
orchestrator_pipeline_duration_ms{stage="..."}                   # histogram
orchestrator_pattern_cache_hits_total                            # counter
orchestrator_pattern_cache_misses_total                          # counter
orchestrator_llm_call_duration_ms                                # histogram
orchestrator_active_locks                                        # gauge
orchestrator_webhook_delivery_total{status="delivered|failed"}   # counter
```

---

#### 2.1.12 `routes/webhooks.py` — CRM Webhook Configuration

| Aspect | Detail |
|--------|--------|
| **Purpose** | CRUD for webhook callback registration per CRM integration. |

**Key Methods:**

```python
@router.post("/api/webhooks/register")
async def register_webhook(request: WebhookRegistration) -> WebhookResponse:
    """Register a CRM webhook callback URL with shared secret for HMAC signing."""

@router.get("/api/webhooks")
async def list_webhooks() -> list[WebhookResponse]:
    """List all registered webhook endpoints."""

@router.delete("/api/webhooks/{webhook_id}")
async def unregister_webhook(webhook_id: str) -> DeleteResponse:
    """Remove a webhook registration."""

@router.post("/api/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str) -> TestResponse:
    """Send a test ping to the registered webhook URL."""
```

**Database Tables:** `webhook_registrations` (PostgreSQL)

---

#### 2.1.13 `middleware/auth.py` — Authentication

| Aspect | Detail |
|--------|--------|
| **Purpose** | Authenticate API requests via API Key header or OAuth2 Bearer token. |
| **Responsibility** | Extract credentials, validate against API key store or OAuth2 introspection endpoint. |

**Key Functions:**

```python
class AuthMiddleware:
    """ASGI middleware for API key + OAuth2 authentication."""

    def __init__(self, app, auth_mode: str, api_keys: dict, oauth_config: OAuthConfig):
        ...

    async def __call__(self, scope, receive, send):
        """Intercept request, validate auth, attach scope to scope."""

class APIKeyValidator:
    """Validate X-API-Key header against PostgreSQL api_keys table."""

class OAuth2Validator:
    """Validate Bearer tokens via introspection endpoint."""
```

**Database Tables:** `api_keys` (PostgreSQL)

---

#### 2.1.14 `middleware/rate_limit.py` — Rate Limiter

| Aspect | Detail |
|--------|--------|
| **Purpose** | Redis-backed sliding window rate limiter. |

**Key Classes:**

```python
class RateLimiter:
    """Sliding window rate limiter backed by Redis sorted sets."""

    def __init__(self, redis_client, rate: int = 5, window_sec: int = 1):
        """5 requests per second default, configurable per route."""

    async def check(self, key: str) -> bool:
        """Return True if request allowed, False if rate exceeded."""

    async def get_remaining(self, key: str) -> int:
        """Return remaining requests in current window."""
```

**Redis Data Structure:** `ratelimit:{route}:{key}` → sorted set of timestamps

**Error Handling:** Returns `429 Too Many Requests` with `Retry-After` header and `X-RateLimit-Remaining`.

---

#### 2.1.15 `middleware/logging.py` — Request/Response Logging

| Aspect | Detail |
|--------|--------|
| **Purpose** | Structured request/response logging with correlation IDs. |

**Key Functions:**

```python
class LoggingMiddleware:
    """Log every request with correlation_id, duration, status, and body size."""

    def __init__(self, app, log_level: str = "INFO"):
        ...

async def extract_correlation_id(request) -> str:
    """Extract X-Correlation-ID header or generate new UUID."""
```

**Log Format:**
```json
{
  "correlation_id": "uuid",
  "method": "POST",
  "path": "/api/tmf622/productOrder",
  "status": 202,
  "duration_ms": 45,
  "request_size": 1024,
  "response_size": 512,
  "client_ip": "10.0.0.1"
}
```

---

### 2.2 Core Layer — `src/core/`

#### 2.2.1 `orchestrator_brain.py` — Main Orchestration Engine

| Aspect | Detail |
|--------|--------|
| **Purpose** | 6-stage agentic brain that receives TMF640/641 requests and produces orchestration plans. |
| **Responsibility** | PARSE → MATCH → REASON → PLAN → DELEGATE → VERIFY_LEARN per the orchestration brain design. |
| **Key Design:** | Single Hermes agent process; stateless between requests; does NOT execute workflows — delegates to MCP. |

**Key Classes:**

```python
class OrchestrationBrain:
    """6-stage agentic orchestration engine. Reasoning only — no device interaction."""

    def __init__(self, pattern_engine: PatternEngine, kb_loader: KBLoader,
                 mcp_dispatcher: MCPDispatcher):
        ...

    async def orchestrate(self, request: TMFRequest) -> OrchestrationResult:
        """Full 6-stage orchestration: parse → match → reason → plan → delegate → verify+learn."""

    # Stage 1: PARSE
    def parse_request(self, request: TMFRequest) -> ParseResult:
        """Extract customer segment, SLA tier, product ID, action, characteristics."""

    # Stage 2: MATCH
    async def match_pattern(self, parse_result: ParseResult) -> MatchResult:
        """Search pattern store: exact → adapted → novel. Return match type + confidence."""

    # Stage 3: REASON
    def derive_expected_state(self, parse_result: ParseResult,
                              match_result: MatchResult) -> ExpectedServiceState:
        """Derive CE model, handoff type, QoS, IP scheme, redundancy from segment + SLA."""

    # Stage 4: PLAN
    def build_plan(self, parse_result: ParseResult, match_result: MatchResult,
                   expected_state: ExpectedServiceState) -> OrchestrationPlan:
        """Determine workflow list, params, device targets, dependencies."""

    # Stage 5: DELEGATE
    async def delegate(self, plan: OrchestrationPlan) -> DelegationResult:
        """Call MCP for each workflow sequentially respecting dependencies."""

    # Stage 6: VERIFY + LEARN
    async def verify_and_learn(self, plan: OrchestrationPlan, delegation_result: DelegationResult,
                               expected_state: ExpectedServiceState) -> OrchestrationResult:
        """Compare actual vs expected, save trace, update pattern store confidence."""
```

**Data Structures:**

```python
@dataclass
class ParseResult:
    """Output of STAGE 1: PARSE"""
    order_id: str
    service_type: str            # "mobile", "l3vpn", "sdwan", "broadband"
    customer_segment: str        # "wholesale", "retail", "enterprise"
    sla_tier: str                # "platinum", "gold", "silver", "bronze"
    product_id: str
    action: str                  # "add", "modify", "delete", "suspend"
    characteristics: dict        # All name→value from request
    related_parties: list[dict]

@dataclass
class MatchResult:
    match_type: str              # "exact", "adapted", "novel"
    pattern: Optional[PatternNode]
    confidence: float
    adaptation_reasons: list[str]

@dataclass
class ExpectedServiceState:
    target_state: str            # "active"
    ce_model: str                # "customer_managed" | "provider_managed"
    handoff_type: str
    qos_profile: str
    ip_scheme: str
    mtu: int
    redundancy: str              # "dual_pe_diverse" | "single_pe" | ...
    failover_target_ms: int
    verification_scope: str      # "pe_only" | "end_to_end" | "pe_plus_handoff"

@dataclass
class OrchestrationPlan:
    workflows: list[WorkflowStep]  # Ordered, dependency-respecting list
    expected_state: ExpectedServiceState

@dataclass
class WorkflowStep:
    workflow_name: str           # e.g., "ResourceAllocation", "DeviceConfiguration"
    params: dict
    target_device: str
    depends_on: list[str]        # workflow names that must complete first
    rollback_workflow: Optional[str]
```

**Integration Points:**
- **Depends on:** `knowledge.pattern_engine`, `knowledge.kb_loader`, `integration.mcp_dispatcher`
- **Depended on by:** `core.pipeline` (invoked by pipeline's DELEGATE stage)
- **External contract:** Calls Workflow MCP tools: `list_workflows()`, `execute_workflow()`, `rollback_workflow()`

**Error Handling:**
- EXECUTE failure → check rollback workflows, attempt rollback → mark `failed`
- MCP unreachable → retry 3x, then mark `failed` + alert ops
- Novel pattern → flag for human review, lower confidence (0.3–0.4)

**Script Reference:**
```bash
# Invoke via Hermes CLI (single agent mode)
hermes chat -q "Orchestrate this TMF641 ServiceOrder: {...}" \
  -s orchestration-brain -p orchestration-brain
```

---

#### 2.2.2 `pipeline.py` — 14-Stage Pipeline Definitions

| Aspect | Detail |
|--------|--------|
| **Purpose** | Define all 14 pipeline stages, their dependencies, parallelism rules, and shared context. |
| **Responsibility** | Register stage handlers, manage pipeline context (thread-safe state bag), provide stage runner with timeout and retry semantics. |

**Pipeline Stages (PoC 12-stage + 2 production additions):**

| # | Stage | Foreground/Background | Responsibility |
|---|-------|-----------------------|----------------|
| 0 | `DETECT` | Foreground | Classify format — JSON (structured) vs text (unstructured) |
| 1 | `MASK` | Foreground | `DataMasker.mask()` — tokenize MSISDNs, IPs, hostnames |
| 2 | `CACHE` | Foreground | `PatternEngine.lookup()` — Jaccard match; HIT or MISS |
| 3 | `DECOMPOSE` | Background | **NEW** `OrderDecomposer.decompose()` — TMF622 → TMF641 when needed |
| 4 | `RAG` | Background | `kb_loader.load_context()` — load KB ontology + standards |
| 5 | `LLM` | Background | `call_deepseek()` — AI reasoning on masked data (cache miss only) |
| 6 | `HYDRATE` | Background | Reverse VAR_* tokens → real values via local mapping |
| 7 | `LOCK` | Background | `SubscriberLock.acquire()` — per-subscriber advisory lock |
| 8 | `MERGE` | Background | Cascade request characteristics + previous model → plan |
| 9 | `WRITETHROUGH` | Background | `PatternEngine.learn()` — persist new pattern to RDF store |
| 10 | `VALIDATE` | Background | `ValidationGateway` — hard-gate destructive keyword scan |
| 11 | `EXECUTE` | Background | `MCPDispatcher.dispatch()` — delegate to MCP servers |
| 12 | `NOTIFY` | Background | `LifecycleNotifier.build_notification_trace()` — TMF641 events |
| 13 | `VERIFY` | Background | Build NEs, compute diff, save service model, emit final state |

**Key Classes:**

```python
@dataclass
class PipelineStage:
    name: str
    handler: Callable
    depends_on: list[str]       # stage names that must complete before this one
    can_fail: bool = True       # False for critical stages that abort on failure
    retry_count: int = 0
    timeout_ms: int = 30_000

class Pipeline:
    """14-stage pipeline manager."""

    def __init__(self):
        self.stages: dict[str, PipelineStage] = {}

    def register(self, stage: PipelineStage):
        """Register a stage handler — callable or async callable."""

    async def run(self, context: PipelineContext) -> ProcessResponse:
        """Execute all stages in dependency order. Return trace + final state."""

    async def run_stage(self, stage_name: str, context: PipelineContext) -> StageResult:
        """Execute one stage with timeout, retry, and error capture."""

@dataclass
class PipelineContext:
    """Mutable context bag passed between stages."""
    order_id: str
    format: str                 # "tmf640" | "tmf641" | "unstructured" | "tmf622"
    service_type: str
    prompt: str
    masked_text: str
    token_map: dict
    characteristics: dict
    all_characteristics: dict
    pattern_match: Optional[PatternNode]
    plan: Optional[dict]
    subscriber_id: str
    previous_model: Optional[dict]
    traces: list[TraceStep]
    errors: list[StageError]
    metrics: dict               # {stage_name: duration_ms}
```

---

#### 2.2.3 `order_decomposer.py` — TMF622 → TMF641 Decomposition

| Aspect | Detail |
|--------|--------|
| **Purpose** | Decompose a TMF622 ProductOrder into one or more TMF641 ServiceOrders. |
| **Responsibility** | Look up product catalog for decomposition rules, generate parent-child service order hierarchy, enqueue in dependency order. |

**Key Classes:**

```python
class OrderDecomposer:
    """Decompose TMF622 product orders into TMF641 service orders."""

    def __init__(self, product_catalog: ProductCatalog):
        ...

    def decompose(self, product_order: ProductOrderRequest) -> DecompositionResult:
        """Main entry: product order → list of service orders with dependencies."""

    def _lookup_product(self, product_id: str) -> ProductDefinition:
        """Query product_catalog table for decomposition rules."""

    def _generate_service_orders(self, product_def: ProductDefinition,
                                  characteristics: list[Characteristic]) -> list[ServiceOrderDef]:
        """Generate TMF641 service orders from product template + characteristics."""

    def _resolve_dependencies(self, service_orders: list[ServiceOrderDef]) -> list[ServiceOrderDef]:
        """Order service orders respecting parent-child and resource dependencies."""

    def _enqueue(self, service_orders: list[ServiceOrderDef], priority: str):
        """Push service orders to appropriate Redis queue by priority."""

@dataclass
class DecompositionResult:
    product_order_id: str
    service_orders: list[str]        # service order IDs created
    hierarchy: dict                   # parent_id → [child_ids]
    queue_status: dict                # queue_name → enqueued_count
```

**Database Tables:** `product_catalog` — reads decomposition_rules JSONB; `service_orders` — writes

**Error Handling:**
- Product not found → `raise ProductNotFoundError`
- No decomposition rules → use default: one service order per product order item
- Duplicate externalId → return existing order (idempotent)

---

#### 2.2.4 `data_masker.py` — Sensitive Data Tokenization

| Aspect | Detail |
|--------|--------|
| **Purpose** | Strip sensitive identifiers before data leaves the local perimeter for cloud AI. |
| **Responsibility** | Tokenize MSISDNs (+5–15 digit phone numbers), IPv4 addresses, and hostnames. Build bidirectional mapping for hydration. |

**Key Classes:**

```python
class DataMasker:
    """Sensitive data tokenization for cloud-safe AI reasoning."""

    MSISDN_RE = re.compile(r'\+?\d{5,15}')
    IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    HOSTNAME_RE = re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b')

    def __init__(self):
        self.map: dict[str, str] = {}      # token ↔ real value (bidirectional)
        self.counters: dict[str, int] = {"msisdn": 0, "ip": 0, "host": 0}

    def mask(self, text: str) -> tuple[str, dict]:
        """Mask text, return (masked_text, token_map_bidirectional)."""

    def unmask(self, text: str) -> str:
        """Reverse the masking — restore all real values from token map."""

    def _mask_msisdn(self, match: re.Match) -> str:
        """Replace MSISDN with VAR_MSISDN_N, track mapping."""

    def _mask_ip(self, match: re.Match) -> str:
        """Replace IP address with VAR_IP_N, track mapping."""
```

**Output:** `token_map = {"VAR_MSISDN_1": "447700123456", "447700123456": "VAR_MSISDN_1", ...}` — bidirectional for efficient lookup in both directions.

**Integration Points:**
- Called by `pipeline.Pipeline` STAGE 1 (MASK) — foreground
- `token_map` flows through `PipelineContext` to STAGE 6 (HYDRATE)
- Mapping **never persisted or sent over network** — lives in process memory only

**Error Handling:** Regex-safe substitution; duplicates reuse existing tokens; non-matching text passes through unchanged.

---

#### 2.2.5 `validation_gateway.py` — Hard-Gate Security Validation

| Aspect | Detail |
|--------|--------|
| **Purpose** | Prevent destructive commands from reaching network devices. |
| **Responsibility** | Scan plan text for blocked keywords; validate callback URLs against allowlist; enforce resource allocation limits. |

**Key Classes:**

```python
class ValidationGateway:
    """Hard-gate security validator — last line of defense before execution."""

    BLOCKED_KEYWORDS = [
        "erase", "reload", "format", "shutdown", "no switchport",
        "write erase", "delete startup-config", "boot system flash",
        "config-register", "confreg"
    ]

    def __init__(self, allowed_callback_domains: list[str]):
        self.allowed_domains = allowed_callback_domains

    def validate_plan(self, plan: dict, masked_text: str) -> ValidationResult:
        """Run all security checks: keyword scan, URL validation, resource limits."""

    def _scan_keywords(self, text: str) -> list[str]:
        """Check text for blocked keywords; return list of matches."""

    def _validate_callback_url(self, url: str) -> bool:
        """Ensure callback URL domain is in allowed list (SSRF prevention)."""

    def _check_resource_limits(self, plan: dict) -> bool:
        """Validate plan does not exceed per-order resource allocation caps."""

@dataclass
class ValidationResult:
    passed: bool
    blocked_keywords: list[str]
    invalid_urls: list[str]
    limit_violations: list[str]
    message: str
```

**Integration Points:**
- Called by `pipeline.Pipeline` STAGE 10 (VALIDATE)
- On BLOCKED: aborts transaction, no devices touched, state = `blocked`
- Feeds audit log with exact reason

---

### 2.3 Knowledge Layer — `src/knowledge/`

#### 2.3.1 `pattern_engine.py` — RDF Pattern Store + Matching

| Aspect | Detail |
|--------|--------|
| **Purpose** | RDF-inspired pattern store with Jaccard similarity matching, confidence lifecycle, and auto-learning. |
| **PoC Equivalent:** `poc/server_live.py` lines 400–665 (`PatternNode`, `PatternEngine`) |

**Key Classes:**

```python
@dataclass
class PatternNode:
    """Named pattern: service type + resource graph as RDF triples."""
    id: str                      # "pat:mobile:abc123" or "pat:taught:xyz789"
    service_type: str            # "mobile" | "l3vpn" | "sdwan" | "broadband"
    label: str                   # Human-readable: "mobile | retail/gold"
    characteristics: dict        # Service-defining chars (excludes instance IDs like msisdn)
    triples: list                # RDF assertions: [subject, predicate, object]
    resources: list              # Derived resource bindings: {name, workflow, role, attributes}
    confidence: float            # 0.0–0.98 (caps at 0.98, hard ceiling)
    use_count: int               # Times matched
    created_at: str              # ISO 8601
    last_used: str               # ISO 8601
    source: str                  # "auto" | "teach" | "kb"
    status: str                  # "active" | "deprecated" | "experimental"

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for API responses."""

class PatternEngine:
    """RDF-inspired pattern store with learning, matching, and confidence lifecycle."""

    INSTANCE_ATTRS = {"msisdn", "imsi", "imei", "pe_ip", "hostname", "serviceid",
                       "serial", "loopback", "management_ip"}

    def __init__(self, cache_backend):
        """cache_backend: diskcache.Cache (PoC) or Redis (production)."""
        self.cache = cache_backend
        self._index: dict[str, list[str]] = {}  # service_type → [pattern_ids]
        self._load_index()

    # ── QUERY ──
    def lookup(self, service_type: str, characteristics: dict) -> Optional[PatternNode]:
        """Find best-matching pattern via Jaccard similarity. Returns None on miss."""

    def _match_score(self, pat_chars: dict, req_chars: dict) -> float:
        """Jaccard similarity on service-defining characteristics. Instance attrs excluded."""

    # ── LEARN ──
    def learn(self, service_type: str, characteristics: dict,
              plan: dict, all_chars: dict = None, source: str = "auto") -> PatternNode:
        """Create new pattern from cache miss + successful orchestration plan."""

    def reinforce(self, pattern: PatternNode) -> PatternNode:
        """Boost confidence on cache hit. Diminishing returns: +0.05 until 0.9, then +0.005 until 0.98."""

    def teach(self, triples: list, source: str = "teach") -> PatternNode:
        """Manual knowledge injection — high confidence (0.9), can override auto-learned."""

    # ── INSPECTION ──
    def list_all(self) -> list[dict]:
        """Return all patterns sorted by (confidence desc, use_count desc)."""

    def get(self, pid: str) -> Optional[dict]:
        """Retrieve full pattern detail by ID."""

    def delete(self, pid: str):
        """Remove pattern from cache and index."""

    def promote(self, pid: str, new_status: str = "active"):
        """Admin: promote experimental → active, or demote to deprecated."""

    # ── INTERNAL ──
    def _save(self, node: PatternNode):
        """Serialise and persist pattern to cache backend."""

    def _load(self, pid: str) -> Optional[PatternNode]:
        """Load pattern with runtime validation. Rejects empty/corrupt patterns."""

    def _index_pattern(self, node: PatternNode):
        """Add pattern ID to service_type index."""

    def _load_index(self):
        """Load in-memory index from cache."""

    def _save_index(self):
        """Persist in-memory index to cache."""

    def seed_from_kb(self, service_resources: dict, wf_map: dict):
        """Pre-seed patterns from KB resource definitions. Confidence starts at 0.25."""
```

**Cache Backend Keys:**
```
orch:idx:patterns  →  {"mobile": ["pat:mobile:abc123", ...], "l3vpn": [...], ...}
orch:pat:{pid}     →  serialized PatternNode
```

**Integration Points:**
- **Called by:** `core.orchestrator_brain` STAGE 2 (MATCH), `core.pipeline` STAGE 2 (CACHE) + STAGE 9 (WRITETHROUGH)
- **Calls:** KB-seeded patterns via `seed_from_kb()` at module load
- **Depended on by:** `api.routes.patterns` — admin CRUD

**Error Handling:**
- `_load()` rejects: patterns with no resources, <3 triples, unreadable data → auto-deletes
- `default_*` contaminated resource attrs → logged as warning, pattern still usable
- Corrupt cache entries → deleted on read, removed from index

**Script Reference:**
```bash
# Query patterns via CLI
curl http://localhost:8090/api/patterns
curl http://localhost:8090/api/patterns/pat:mobile:abc123

# Teach a new pattern
curl -X POST http://localhost:8090/api/patterns/teach \
  -H "Content-Type: application/json" \
  -d '{"triples": [...]}'
```

---

#### 2.3.2 `kb_loader.py` — Knowledge Base File Reader + Context Builder

| Aspect | Detail |
|--------|--------|
| **Purpose** | Read telecom knowledge base files and build structured context for LLM reasoning. |
| **PoC Equivalent:** `poc/server_live.py` lines 1041–1081 (`load_kb_context()`) |

**Key Classes:**

```python
class KBLoader:
    """Load and parse telecom KB files for domain reasoning."""

    KB_DIR = "/opt/data/telecom-orchestrator/knowledge-base"

    def __init__(self, kb_dir: str = KB_DIR):
        self.kb_dir = kb_dir
        self._cache: dict[str, str] = {}  # file_path → content (TTL: 5 min)

    def load_context(self, service_type: str) -> str:
        """Build complete domain context for a service type: ontology + standards + resources."""

    def load_ontology_section(self, section_name: str) -> str:
        """Extract a named section from core-ontology.md."""

    def load_standards(self, service_type: str, keywords: list[str] = None) -> str:
        """Extract relevant standards from standards-index.md."""

    def load_product_template(self, product_id: str) -> dict:
        """Load YAML product template with required workflows and attributes."""

    def load_workflow(self, workflow_name: str) -> str:
        """Load a provisioning workflow markdown from workflows/."""

    def load_segment_overrides(self, segment: str) -> dict:
        """Load customer segment → state attribute overrides."""

    def load_sla_overrides(self, sla_tier: str) -> dict:
        """Load SLA tier → redundancy/QoS/schedule overrides."""

    def load_lessons(self) -> dict:
        """Load human-reviewed corrections and refinements."""

    def invalidate_cache(self):
        """Clear the file content cache (called on KB file changes)."""
```

**KB File Structure Referenced:**
```
knowledge-base/
├── ontologies/core-ontology.md      # Service taxonomy, resource taxonomy
├── reference/standards-index.md     # Standards catalog with keywords
├── products/product-catalog.yaml    # Product → workflows + resources mapping
├── services/*.md                    # Service definitions
├── resources/*.md                   # Resource definitions
├── workflows/*.md                   # Step-by-step provisioning workflows
├── segments/segment-overrides.yaml  # Customer segment → expected state overrides
├── sla/sla-overrides.yaml           # SLA tier → redundancy/performance overrides
└── lessons/lessons.yaml             # Human-reviewed corrections
```

**Integration Points:**
- Called by `core.orchestrator_brain` STAGE 4 (PLAN) — loads templates + overrides
- Called by `core.pipeline` STAGE 4 (RAG) — loads domain context for LLM prompt

---

#### 2.3.3 `service_resources.py` — KB → Resource Mapping

| Aspect | Detail |
|--------|--------|
| **Purpose** | Define required network elements per service type — single source of truth. |
| **PoC Equivalent:** `poc/server_live.py` lines 714–777 (`SERVICE_RESOURCES`, `WF_MAP`) |

**Key Data Structures:**

```python
SERVICE_RESOURCES: dict[str, ServiceResourceDef] = {
    "mobile": ServiceResourceDef(
        domain="Voice / Mobile Core",
        standards=["3GPP TS 29.002 (MAP/HLR)", "3GPP TS 23.040 (SMS)", ...],
        required_resources=[
            ResourceDef(type="HLR/HSS", role="Subscriber registry",
                       attributes=["msisdn", "imsi", "subscriber_profile", "roaming_profile"]),
            ResourceDef(type="IMS-Core", role="VoLTE/VoWiFi call control",
                       attributes=["msisdn", "imsi", "volte_enabled", "codec_profile"]),
            ResourceDef(type="PCRF/PCF", role="Policy & charging rules",
                       attributes=["apn", "qos_profile", "charging_rule", "bandwidth_limit"]),
            ResourceDef(type="SMSC", role="SMS store-and-forward",
                       attributes=["msisdn", "routing", "validity_period"]),
            ResourceDef(type="MSC/MME", role="Mobility management",
                       attributes=["msisdn", "imsi", "location_area", "tac"]),
            ResourceDef(type="SBC", role="Session border control",
                       attributes=["sip_domain", "codec_list", "media_handling"]),
        ],
        lifecycle="DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE",
    ),
    "l3vpn": ServiceResourceDef(...),
    "sdwan": ServiceResourceDef(...),
    "broadband": ServiceResourceDef(...),
}

WF_MAP: dict[str, str] = {
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
```

**Integration Points:**
- Used by `knowledge.pattern_engine` for KB seeding
- Used by `core.pipeline` for fallback plan generation (when LLM unavailable)
- Used by `knowledge.kb_loader` for RAG context building

---

#### 2.3.4 `ontology.py` — Core Ontology Query Interface

| Aspect | Detail |
|--------|--------|
| **Purpose** | Programmatic query interface for the core ontology. |
| **Responsibility** | Parse core-ontology.md sections, answer queries about service taxonomy, resource types, relationships. |

**Key Functions:**

```python
class Ontology:
    """Query interface for core telecom ontology."""

    def __init__(self, kb_loader: KBLoader):
        ...

    def get_service_subclass_of(self, service_type: str) -> list[str]:
        """Get parent service types in the taxonomy."""

    def get_required_resources(self, service_type: str) -> list[ResourceDef]:
        """Get required resources for a service type."""

    def get_resource_attributes(self, resource_type: str) -> list[str]:
        """Get required attributes for a resource type."""

    def get_lifecycle(self, service_type: str) -> list[str]:
        """Get ordered lifecycle states as list."""

    def validate_service_type(self, service_type: str) -> bool:
        """Check if a service type exists in the ontology."""

    def get_standards(self, service_type: str) -> list[str]:
        """Get applicable standards for a service type."""
```

---

### 2.4 Models Layer — `src/models/`

#### 2.4.1 `service_model.py` — Service Model Store

| Aspect | Detail |
|--------|--------|
| **Purpose** | Persistent flat representation of a subscriber service. Created after successful provisioning. |
| **PoC Equivalent:** `poc/server_live.py` lines 34–193 (`ServiceModelStore`) |

**Key Classes:**

```python
class ServiceModelStore:
    """Persistent subscriber service model. Versioned. Corruption-resilient."""

    MIN_REAL_ATTRS = 3  # minimum real NE attributes to consider salvageable

    def __init__(self, backend):
        """backend: Redis or PostgreSQL-based adapter."""
        self.backend = backend

    def get(self, subscriber_id: str) -> Optional[dict]:
        """Load subscriber model with runtime corruption check. Deletes and returns None if unsalvageable."""

    def save(self, subscriber_id: str, model: dict):
        """Write model with version increment. Previous versions retained in history table."""

    def build_model(self, subscriber_id: str, service_type: str,
                    characteristics: dict, network_elements: list[dict],
                    version: int = 0) -> dict:
        """Construct a new model dict from pipeline output."""

    def compute_diff(self, previous_model: Optional[dict], new_characteristics: dict,
                     new_network_elements: list[dict]) -> dict:
        """Compute characteristic changes and NE attribute diffs between old and new model."""

    def delete(self, subscriber_id: str):
        """Delete subscriber model and all history."""

    def get_history(self, subscriber_id: str) -> list[dict]:
        """Retrieve all versions of a subscriber's model."""

    def _validate_model(self, model: dict) -> bool:
        """Check for corruption: default_* values, placeholder markers, missing fields."""

    def _salvage_model(self, model: dict) -> Optional[dict]:
        """Attempt to clean a partially corrupt model by stripping poison values."""
```

**Model Structure:**
```json
{
    "subscriber_id": "MSISDN-447700123456",
    "service_type": "mobile",
    "version": 3,
    "characteristics": {
        "msisdn": "447700123456",
        "customerSegment": "retail",
        "slaTier": "gold",
        "subscriber_profile": "Gold_VoLTE_IntlRoam",
        ...
    },
    "network_elements": [
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
        },
        ...
    ],
    "created_at": "2026-06-21T14:31:05Z",
    "updated_at": "2026-06-21T14:31:05Z"
}
```

**Backend Key Pattern:**
```
orch:sub:{subscriber_id}        →  current model dict
orch:sub:{subscriber_id}:v{N}  →  historical version (in PostgreSQL)
```

**Integration Points:**
- Called by `core.pipeline` STAGE 13 (VERIFY) — saves model after provisioning
- Called by `core.pipeline` STAGE 2 (CACHE) — loads previous model for diff context
- Called by `api.routes.subscribers` for admin inspection

**Error Handling:**
- `get()` with full corruption → delete entry, return None (treated as fresh provisioning)
- Partial corruption → log warning, salvage clean attributes, return salvaged model
- `save()` failure → raise, pipeline aborts

---

#### 2.4.2 `resource_model.py` — Resource Model

| Aspect | Detail |
|--------|--------|
| **Purpose** | Manage resource instances (VRF, BGP peer, IP subnet, interface, VLAN, VNF, etc.) in PostgreSQL. |
| **Responsibility** | CRUD for resource inventory; capacity tracking; allocation/release lifecycle. |

**Key Classes:**

```python
class ResourceModel:
    """Resource lifecycle manager backed by PostgreSQL."""

    def __init__(self, pg_pool):
        self.db = pg_pool

    async def allocate(self, resource: ResourceDef, service_id: str) -> ResourceRecord:
        """Reserve a new resource instance. Generate ID, set state=planned."""

    async def configure(self, resource_id: str, config: dict) -> ResourceRecord:
        """Update resource config after device push. Set state=configuring."""

    async def activate(self, resource_id: str) -> ResourceRecord:
        """Set resource state to in_service."""

    async def decommission(self, resource_id: str) -> ResourceRecord:
        """Release resource. Set state=decommissioned."""

    async def get_by_service(self, service_id: str) -> list[ResourceRecord]:
        """Get all resources belonging to a service."""

    async def get_by_device(self, device_name: str) -> list[ResourceRecord]:
        """Get all resources on a device."""

    async def get_capacity(self, device_name: str) -> CapacityReport:
        """Calculate remaining capacity on a device (VRFs, interfaces, BGP sessions)."""

    async def check_availability(self, resource_type: str, device_name: str,
                                  quantity: int = 1) -> bool:
        """Pre-flight: does the device have capacity for this resource type?"""
```

**Database Tables:** `resource_inventory` (PostgreSQL) — see Section 4.1.

---

#### 2.4.3 `subscriber_lock.py` — Advisory Locking

| Aspect | Detail |
|--------|--------|
| **Purpose** | Per-subscriber advisory lock preventing concurrent modification of subscriber models. |
| **PoC Equivalent:** `poc/server_live.py` lines 200–271 (`SubscriberLock`, `_LockContext`) |

**Key Classes:**

```python
class SubscriberLock:
    """Per-subscriber advisory lock backed by Redis (production) or diskcache (PoC)."""

    LOCK_TTL = 30        # seconds — auto-releases on worker crash
    RETRY_DELAY = 0.1    # seconds between retries
    MAX_RETRIES = 50     # 5 seconds total retry budget

    def __init__(self, backend):
        """backend: Redis client (production) or diskcache.Cache (PoC)."""
        self.backend = backend
        self._local = threading.local()  # per-thread re-entrancy tracking

    def acquire(self, subscriber_id: str, worker_id: str) -> LockContext:
        """Context-manager-able acquire. Returns LockContext — use with `with` statement."""

    def _try_acquire(self, lock_key: str, worker_id: str) -> bool:
        """Non-blocking acquire with retry loop. Returns True/False."""

    def _release(self, lock_key: str, worker_id: str):
        """Release lock if owned by this worker."""

    def force_release(self, subscriber_id: str):
        """Admin: force-release any worker's lock on this subscriber."""

    def list_active(self) -> list[dict]:
        """List all active locks with worker_id and age."""

class LockContext:
    """Context manager — enter: acquire lock; exit: release if held."""

    def __enter__(self) -> bool:
        """Returns True if lock acquired, False if timed out."""

    def __exit__(self, *args):
        """Release lock if acquired."""
```

**Lock Key Pattern:** `lock:sub:{subscriber_id}` → `{worker_id, acquired_at, ttl_seconds}`

**Integration Points:**
- Called by `core.pipeline` STAGE 7 (LOCK) — wraps MERGE → VERIFY critical section
- Called by `api.routes.locks` for admin status/release
- Re-entrant: same worker_id can re-acquire without deadlock

---

#### 2.4.4 `inventory.py` — PostgreSQL-Backed Inventory CRUD

| Aspect | Detail |
|--------|--------|
| **Purpose** | Thin CRUD layer for PostgreSQL inventory tables. |
| **Responsibility** | Provide async read/write operations with connection pooling and query building. |

**Key Classes:**

```python
class InventoryDB:
    """PostgreSQL-backed inventory CRUD with connection pooling."""

    def __init__(self, pg_pool):
        self.pool = pg_pool

    # ── Service Inventory ──
    async def create_service(self, service: ServiceRecord) -> str:
    async def get_service(self, service_id: str) -> ServiceRecord:
    async def list_services(self, filters: dict, limit: int, offset: int) -> list[ServiceRecord]:
    async def update_service_state(self, service_id: str, state: str):
    async def delete_service(self, service_id: str):

    # ── Resource Inventory ──
    async def create_resource(self, resource: ResourceRecord) -> str:
    async def get_resource(self, resource_id: str) -> ResourceRecord:
    async def list_resources(self, filters: dict, limit: int, offset: int) -> list[ResourceRecord]:
    async def update_resource_state(self, resource_id: str, state: str):
    async def update_resource_config(self, resource_id: str, config: dict):

    # ── Orders ──
    async def create_product_order(self, order: ProductOrderRecord) -> str:
    async def create_service_order(self, order: ServiceOrderRecord) -> str:
    async def get_service_order(self, order_id: str) -> ServiceOrderRecord:
    async def append_audit_entry(self, order_id: str, entry: AuditEntry):

    # ── Webhook Delivery ──
    async def log_delivery(self, delivery: WebhookDeliveryRecord):
    async def get_delivery_status(self, order_id: str) -> list[WebhookDeliveryRecord]:

    # ── Product Catalog ──
    async def get_product(self, product_id: str) -> ProductRecord:
    async def list_products(self, category: str = None) -> list[ProductRecord]:
```

---

### 2.5 Integration Layer — `src/integration/`

#### 2.5.1 `mcp_dispatcher.py` — MCP Server Dispatch

| Aspect | Detail |
|--------|--------|
| **Purpose** | Dispatcher that routes workflow execution requests to the correct MCP server. |
| **Responsibility** | Maintain MCP server registry, route `execute_workflow()` calls, aggregate results, handle retries. |

**Key Classes:**

```python
class MCPDispatcher:
    """Central dispatcher for all MCP server integrations."""

    def __init__(self):
        self.servers: dict[str, MCPServerAdapter] = {}

    def register(self, name: str, adapter: MCPServerAdapter):
        """Register a named MCP server adapter."""

    async def list_workflows(self) -> list[dict]:
        """Aggregate workflow lists from all registered MCP servers."""

    async def execute_workflow(self, workflow_name: str, params: dict,
                                context: dict) -> ExecutionResult:
        """Find MCP server for workflow, execute, return result."""

    async def get_workflow_status(self, workflow_run_id: str) -> ExecutionResult:
        """Poll for long-running workflow status."""

    async def rollback_workflow(self, workflow_run_id: str) -> RollbackResult:
        """Execute rollback for a failed workflow."""

    async def validate_workflow_params(self, workflow_name: str, params: dict) -> ValidationResult:
        """Pre-flight parameter validation against MCP server schema."""

    def health_check(self) -> dict[str, bool]:
        """Check connectivity to all registered MCP servers."""

@dataclass
class ExecutionResult:
    status: str                 # "running" | "completed" | "failed"
    workflow_run_id: str
    output: dict
    duration_ms: int
    error: Optional[str]

class MCPServerAdapter(ABC):
    """Abstract adapter for an MCP server."""

    @abstractmethod
    async def execute(self, workflow_name: str, params: dict) -> ExecutionResult: ...
    @abstractmethod
    async def list_workflows(self) -> list[dict]: ...
    @abstractmethod
    async def get_status(self, run_id: str) -> ExecutionResult: ...
    @abstractmethod
    async def rollback(self, run_id: str) -> RollbackResult: ...
    @abstractmethod
    async def health_check(self) -> bool: ...
```

**Registered MCP Servers (production):**

| Server | Adapter Class | Purpose |
|--------|--------------|---------|
| `netbox` | `NetBoxAdapter` | IPAM/DCIM inventory, IP allocation, VLAN/circuit management |
| `ansible` | `AnsibleAdapter` | Push-button config deployment via ansible-runner |
| `nso` | `NSOAdapter` | Cisco NSO YANG service activation |
| `osm` | `OSMAdapter` | OSM NFV orchestration (VNF lifecycle) |
| `device` | `DeviceAdapter` | Direct device CLI/NETCONF (Netmiko, NAPALM) |

**Integration Points:**
- Called by `core.orchestrator_brain` STAGE 5 (DELEGATE)
- Called by `core.pipeline` STAGE 11 (EXECUTE)
- Each adapter wraps a Hermes MCP server registered via `hermes mcp add`

---

#### 2.5.2-2.5.5 Integration Clients (`netbox_client.py`, `ansible_client.py`, `nso_client.py`, `osm_client.py`)

Each client follows the same pattern:

```python
class {Vendor}Adapter(MCPServerAdapter):
    """Adapter for {Vendor} API."""

    def __init__(self, base_url: str, auth_token: str, timeout: int = 60):
        ...

    async def execute(self, workflow_name: str, params: dict) -> ExecutionResult:
        """Map workflow name to API call(s), execute, return result."""

    async def health_check(self) -> bool:
        """Ping the API health endpoint."""

    # Vendor-specific methods
    ...
```

**NetBox Adapter Tools:**
- `netbox_get_device(name)` — Query device details, interfaces, status
- `netbox_allocate_ip(prefix_id)` — Allocate next available IP
- `netbox_get_prefixes(site)` — List IP prefixes at a site
- `netbox_create_circuit(cid, provider, type, bandwidth)` — Create circuit record
- `netbox_assign_ip(interface_id, address)` — Assign IP to interface
- `netbox_get_device_capacity(name)` — Check available VRFs, interfaces, BGP sessions

**Ansible Adapter Tools:**
- `ansible_run_playbook(playbook, inventory, limit, extra_vars)` — Execute playbook
- `ansible_get_facts(device)` — Gather device facts
- `ansible_validate_config(device, config_type)` — Validate against compliance rules

**Cisco NSO Tools:**
- `nso_activate_service(service_type, device, params)` — Activate YANG service model
- `nso_get_service_status(service_id)` — Check NSO service instance state
- `nso_sync_from_device(device)` — Sync device config into NSO CDB

**OSM Tools:**
- `osm_onboard_vnfd(vnfd_descriptor)` — Onboard VNF descriptor
- `osm_instantiate_ns(ns_descriptor, vim_account)` — Instantiate network service
- `osm_get_ns_status(ns_instance_id)` — Check NS instance status

---

#### 2.5.6 Device Drivers (`device_drivers/`)

| Driver | File | Transport | Config Method |
|--------|------|-----------|---------------|
| Cisco IOS/IOS-XE/IOS-XR | `cisco_ios.py` | SSH + NETCONF | CLI commands or YANG/XML |
| Juniper Junos | `juniper_junos.py` | SSH + NETCONF | CLI (set/delete) or Junos XML |
| Nokia SR OS | `nokia_sros.py` | SSH + MD-CLI | MD-CLI commands |

**Key Interface:**

```python
class DeviceDriver(ABC):
    """Abstract device driver — all vendor drivers implement this interface."""

    def __init__(self, hostname: str, credentials: dict, jump_host: Optional[str] = None):
        ...

    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def configure(self, config: list[str]) -> ConfigResult: ...

    @abstractmethod
    async def show(self, command: str) -> str: ...

    @abstractmethod
    async def validate_state(self, expected_state: dict) -> ValidationResult: ...

    @abstractmethod
    async def rollback(self, changeset: ConfigResult) -> RollbackResult: ...

    @abstractmethod
    async def disconnect(self): ...
```

---

### 2.6 Notification Layer — `src/notification/`

#### 2.6.1 `lifecycle_notifier.py` — TMF641 Event Emitter

| Aspect | Detail |
|--------|--------|
| **Purpose** | Emit TMF641 ServiceOrderMilestoneEvent and ServiceOrderStateChangeEvent notifications. |
| **PoC Equivalent:** `poc/server_live.py` lines 785–945 (`LifecycleNotifier`) |

**Key Classes:**

```python
class LifecycleNotifier:
    """TMF641 v4.1.0 compliant notification emitter."""

    ORDER_IN_PROGRESS = "inProgress"
    ORDER_COMPLETED = "completed"
    ORDER_FAILED = "failed"

    def __init__(self):
        self._notifications: list[dict] = []

    def parse_lifecycle(self, service_type: str) -> list[str]:
        """Extract ordered lifecycle states from KB service_resources.py."""

    def emit_milestone(self, state: str, service_type: str, order_id: str,
                       correlation_id: str, description: str = "",
                       status: str = "achieved") -> dict:
        """Emit ServiceOrderMilestoneEvent — order remains inProgress."""

    def emit_state_change(self, to_state: str, service_type: str, order_id: str,
                          correlation_id: str, description: str = "") -> dict:
        """Emit ServiceOrderStateChangeEvent — final state transition."""

    def build_notification_trace(self, order_id: str, service_type: str,
                                  subscriber_id: str, start_time: float,
                                  step_callback: Callable) -> int:
        """Walk KB lifecycle, emit milestone for each intermediate state + state change for final."""

    def flush(self) -> list[dict]:
        """Return all notifications emitted and clear buffer."""

    def _base_event(self, event_type: str, order_id: str,
                    correlation_id: str, domain: str = "ServiceFulfillment",
                    priority: str = "normal") -> dict:
        """Base TMF notification envelope."""
```

**Notification Event Structure:**
```json
{
    "eventId": "evt-PO-ABC12345-ServiceOrderMilestone",
    "eventTime": "2026-06-21T14:30:45Z",
    "eventType": "ServiceOrderMilestoneEvent",
    "correlationId": "corr-PO-ABC12345",
    "domain": "ServiceFulfillment",
    "priority": "normal",
    "event": {
        "serviceOrder": {
            "id": "PO-ABC12345",
            "href": "/api/tmf641/serviceOrder/PO-ABC12345",
            "state": "inProgress",
            "externalId": "PO-ABC12345",
            "category": "mobile",
            "milestone": [{
                "id": "ms-PO-ABC12345-HLR_PROVISIONED",
                "name": "HLR_PROVISIONED",
                "description": "Orchestrator provisioning: HLR_PROVISIONED.",
                "message": "Orchestrator reached lifecycle state: HLR_PROVISIONED",
                "milestoneDate": "2026-06-21T14:30:45Z",
                "status": "achieved"
            }]
        }
    }
}
```

**Integration Points:**
- Called by `core.pipeline` STAGE 12 (NOTIFY)
- Notifications flow into `ProcessResponse.final_state.notifications`
- Retained in PostgreSQL `audit_log` for historical access
- Webhook delivery handled by `webhook_manager.py`

---

#### 2.6.2 `webhook_manager.py` — CRM Callback Dispatcher

| Aspect | Detail |
|--------|--------|
| **Purpose** | Deliver TMF641 state change events to CRM webhook endpoints. |
| **Responsibility** | Look up registered callback URL, POST event with HMAC signature, retry with exponential backoff, dead-letter queue on final failure. |

**Key Classes:**

```python
class WebhookManager:
    """CRM webhook delivery with retry, signing, and dead-letter handling."""

    def __init__(self, secret_key: str, redis_client, pg_pool):
        self.secret = secret_key
        self.redis = redis_client
        self.db = pg_pool

    async def deliver(self, order_id: str, event_type: str,
                       payload: dict, callback_url: str) -> DeliveryResult:
        """Deliver webhook with HMAC signing and retry."""

    async def _send(self, url: str, payload: dict) -> tuple[int, str]:
        """Single delivery attempt with 15s timeout."""

    def _sign(self, payload: dict) -> str:
        """HMAC-SHA256 sign the payload for CRM verification."""

    async def _retry_policy(self, attempt: int) -> float:
        """Exponential backoff: 10s, 30s, 90s for attempts 1-3."""

    async def _dead_letter(self, order_id: str, payload: dict, error: str):
        """Push failed delivery to dead-letter queue + alert ops channel."""

    async def reprocess_dead_letter(self, order_id: str) -> DeliveryResult:
        """Admin: manually retry a dead-lettered delivery."""

@dataclass
class DeliveryResult:
    success: bool
    response_code: Optional[int]
    response_body: Optional[str]
    attempt: int
    error: Optional[str]
```

**Database Tables:** `webhook_deliveries` (PostgreSQL) — delivery audit log

**Delivery Guarantees:**
- At-least-once delivery (CRM must be idempotent on `eventId`)
- Retry: 3 attempts, exponential backoff (10s → 30s → 90s)
- Timeout per attempt: 15 seconds
- On final failure: dead-letter queue + alert ops channel
- Authentication: HMAC-SHA256 signature in `X-Signature` header

---

#### 2.6.3 `gateway_notifier.py` — Telegram/Discord/Slack Alerting

| Aspect | Detail |
|--------|--------|
| **Purpose** | Push operational alerts to messaging platforms on critical events. |

**Key Functions:**

```python
class GatewayNotifier:
    """Send operational alerts to Telegram, Discord, and/or Slack."""

    def __init__(self, config: NotificationConfig):
        ...

    async def alert_ops_channel(self, message: str, severity: str = "error"):
        """Send alert to all configured channels."""

    async def alert_failure(self, order_id: str, error: str, target_channel: str = "telegram"):
        """Alert on provisioning failure."""

    async def alert_completion(self, order_id: str, service_id: str,
                                target_channel: str = "slack"):
        """Notify on successful provisioning."""

    async def alert_capacity(self, device: str, resource_type: str, remaining_pct: float):
        """Capacity threshold alert."""
```

**Events That Trigger Alerts:**
- Order FAILED after retry exhaustion
- Webhook delivery dead-lettered
- Pattern deprecated after 3 consecutive failures
- Resource pool below 20% remaining capacity
- Device unreachable after 3 retries

---

### 2.7 Cron Layer — `src/cron/`

| Cron Job | Schedule | Purpose |
|----------|----------|---------|
| `service_assurance.py` | Every 30 min | Verify BGP sessions, ping CE, check interface counters, flag failures |
| `resource_discovery.py` | Daily at 02:00 | Sync NetBox inventory, compare actual vs recorded config, flag discrepancies |
| `capacity_management.py` | Weekly Mon 08:00 | Analyze resource usage trends, identify pools <20% capacity, generate report |

**Key Pattern:**

```python
class BaseCronJob(ABC):
    """Base class for all cron jobs."""

    def __init__(self, config: dict):
        ...

    @abstractmethod
    async def run(self) -> CronResult:
        """Execute the cron job. Returns results + alerts."""

    async def run_with_logging(self) -> CronResult:
        """Wrapper: run with logging, error capture, alert dispatch."""

class ServiceAssuranceJob(BaseCronJob):
    async def run(self) -> CronResult:
        """For each ACTIVE service: verify BGP, ping, check counters. Flag failures."""

class ResourceDiscoveryJob(BaseCronJob):
    async def run(self) -> CronResult:
        """Sync NetBox devices, compare actual vs recorded state, update inventory."""

class CapacityManagementJob(BaseCronJob):
    async def run(self) -> CronResult:
        """Analyze trends, identify pools below threshold, generate capacity report."""
```

**Script Reference:**
```bash
# Register cron jobs via Hermes
hermes cron create "0 2 * * *" --name "resource-discovery" \
  --prompt "Run resource discovery: sync all network devices..." --deliver local

hermes cron create "30m" --name "service-assurance" \
  --prompt "Run service health check on all ACTIVE services..." --deliver local

hermes cron create "0 8 * * 1" --name "capacity-trending" \
  --prompt "Analyze resource utilisation trends..." --deliver local
```

---

## 3. Frontend Components

### 3.1 Dashboard Layout (React Component Tree)

```
<App>
  <Header>
    <BrandLogo />
    <StatusBadge status="production" />
    <UserMenu />
  </Header>
  <MainLayout>
    <LeftPanel>
      <ServiceRequestInput />        # Textarea for TMF640/641 JSON or unstructured text
      <SampleSelector />             # Pre-built sample request chips
      <ActionButtons />             # Execute + Clear
    </LeftPanel>
    <RightPanel>
      <EmptyState />                 # Shown before first submission
      <TraceViewer />               # Pipeline stage flow cards
      <PatternAnalysisPanel />      # Match confidence, comparison tables
      <NotificationTimeline />      # TMF641 lifecycle notifications
      <NetworkElementCards />       # Post-activation NE state grid
      <FinalSummary />              # Orchestration totals + subscriber diff
    </RightPanel>
  </MainLayout>
  <Pages>                            # React Router pages
    <Route path="/" element={<OrchestrationConsole />} />
    <Route path="/orders" element={<OrderManagementConsole />} />
    <Route path="/inventory" element={<InventoryBrowser />} />
    <Route path="/patterns" element={<PatternManagement />} />
    <Route path="/settings" element={<SettingsPage />} />
  </Pages>
</App>
```

### 3.2 Trace Viewer Component

| Aspect | Detail |
|--------|--------|
| **PoC Implementation** | `poc/static/index.html` — `#trace-steps` with `.trace-step` > `.step-card` flow |
| **Production Stack** | React component with polling (3s interval) → WebSocket upgrade |

**Key States:**
- **Polling mode:** `setInterval(3000)` calling `GET /api/process/{order_id}`
- **WebSocket upgrade:** On production deploy, connect to `ws://host/ws/trace/{order_id}` for real-time trace step pushes
- **Rendering:** Each `TraceStep` → `.step-card` with color-coded header bar, `Goal/Input/Expected/Actual/Output` sections
- **Flow lines:** Vertical connectors between cards showing pipeline progression

**Component Props:**
```typescript
interface TraceViewerProps {
  orderId: string;
  trace: TraceStep[];
  status: "processing" | "completed" | "blocked" | "error";
  totalMs: number;
}

interface TraceStep {
  stage: string;
  status: "done" | "running" | "error" | "blocked";
  title: string;
  detail: string;       // Goal/Input/Expected/Actual/Output formatted text
  color: string;        // cyan | violet | green | amber | blue | red
  icon: string;         // emoji
  elapsedMs: number;
}
```

### 3.3 Network Element Cards

| Aspect | Detail |
|--------|--------|
| **Purpose** | Display post-activation NE state grid with attribute tables. |
| **PoC Element** | `#network-elements` section with `.ne-card` > `.ne-attr-row` |

**Data Source:** `final_state.networkElements[]`

**Card Layout per NE:**
```
┌─────────────────────────────────┐
│ 🔷 HLR-HSS    (HLR_Provisioning)│
│    Subscriber registry           │
├─────────────────────────────────┤
│ msisdn            447700123456  │
│ imsi         234151234567890    │
│ subscriber_profile  Gold_VoLTE  │
│ status           Configured     │
└─────────────────────────────────┘
```

**Diff highlighting:** Changed attributes (from previous model) shown with green background.

### 3.4 Pattern Analysis Panel

| Aspect | Detail |
|--------|--------|
| **Purpose** | Visualize pattern match results — confidence score, comparison tables, suggestions. |
| **PoC Element** | `#pattern-analysis` section with `.match-grid` |

**Components:**
- **Confidence gauge:** Circular progress with percentage
- **Comparison table:** Request chars vs pattern chars with ✓/✗/? indicators
- **Instance attrs excluded:** List of characteristics excluded from matching (msisdn, imsi, etc.)
- **Suggestions:** On MISS, show "No existing pattern. Pattern will be learned from this run." On HIT, show "Reused pattern with N prior uses."

### 3.5 Notification Timeline

| Aspect | Detail |
|--------|--------|
| **Purpose** | Horizontal timeline showing TMF641 milestone + state change events. |
| **PoC Element** | `#notification-timeline` with `.notif-timeline` > `.notif-event` |

**Data Source:** `final_state.notifications[]`

**Rendering:** Horizontal flow with dots and connectors. Each event shows:
- Event type badge (Milestone / State Change)
- Lifecycle state name
- ISO 8601 timestamp
- Status badge (achieved / completed)

### 3.6 Service Inventory Browser

| Aspect | Detail |
|--------|--------|
| **Page** | `/inventory` — React page with search, filter, paginated table |
| **API** | `GET /api/tmf638/service` with filters |

**Features:**
- Search by customer_id, service_type, state
- Click row → expand to see child resources
- Suspend/Terminate action buttons
- Export to CSV

### 3.7 Resource Inventory Browser

| Aspect | Detail |
|--------|--------|
| **Page** | `/inventory?tab=resources` — same page, resources tab |
| **API** | `GET /api/tmf639/resource` with filters |

**Features:**
- Search by service_id, resource_type, device_name, state
- Click row → show full config JSON
- Capacity utilization indicators per device

### 3.8 Order Management Console

| Aspect | Detail |
|--------|--------|
| **Page** | `/orders` — React page for CRM operators |
| **API** | `GET /api/tmf622/productOrder`, `GET /api/tmf641/serviceOrder` |

**Features:**
- Product order list with state badges
- Click → expand child service orders
- Full audit log per service order
- Cancel action with rollback initiation
- Webhook delivery status per order

---

## 4. Database Schemas

### 4.1 PostgreSQL — Primary Data Store

#### `product_catalog`
```sql
CREATE TABLE product_catalog (
    id              TEXT PRIMARY KEY,       -- 'prod-l3vpn-01'
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,          -- 'VPN', 'Internet', 'Voice', 'SD-WAN', 'Broadband'
    description     TEXT,
    service_template TEXT,                  -- path to YAML/TOSCA template
    decomposition_rules JSONB,              -- how to break into service orders
    required_resources JSONB,               -- [{type: 'VRF', count: 1}, ...]
    supported_devices TEXT[],               -- ['cisco-ios-xr', 'juniper-junos']
    sla_tiers       JSONB,                  -- [{name: 'standard', max_fulfillment_sec: 600}, ...]
    provisioning_workflows TEXT[],          -- ['ResourceAllocation', 'DeviceConfiguration', ...]
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `product_orders` (TMF622)
```sql
CREATE TABLE product_orders (
    id              TEXT PRIMARY KEY,       -- 'ord-20260621-0001'
    external_id     TEXT,                   -- CRM order reference
    state           TEXT DEFAULT 'acknowledged',
    priority        TEXT DEFAULT 'standard', -- 'urgent' | 'standard' | 'bulk'
    category        TEXT,
    customer_id     TEXT,
    customer_name   TEXT,
    callback_url    TEXT,
    order_data      JSONB,                  -- Full original TMF622 request
    expected_completion TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX idx_product_orders_external ON product_orders(external_id) WHERE external_id IS NOT NULL;
```

#### `service_orders` (TMF641)
```sql
CREATE TABLE service_orders (
    id              TEXT PRIMARY KEY,       -- 'so-l3vpn-0001'
    product_order_id TEXT REFERENCES product_orders(id),
    parent_order_id TEXT REFERENCES service_orders(id),
    state           TEXT DEFAULT 'acknowledged',
    external_id     TEXT,
    action          TEXT DEFAULT 'add',     -- 'add' | 'modify' | 'delete' | 'noChange'
    product_id      TEXT REFERENCES product_catalog(id),
    service_id      TEXT,                   -- Set when service instance created
    category        TEXT,
    characteristics JSONB,                  -- Site, bandwidth, device, etc.
    audit_log       JSONB DEFAULT '[]',     -- [{date, state, message}, ...]
    worker_id       TEXT,
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `service_inventory` (TMF638)
```sql
CREATE TABLE service_inventory (
    id              TEXT PRIMARY KEY,       -- 'svc-acme-sjc-l3vpn'
    service_order_id TEXT REFERENCES service_orders(id),
    customer_id     TEXT NOT NULL,
    product_id      TEXT REFERENCES product_catalog(id),
    name            TEXT NOT NULL,
    service_type    TEXT NOT NULL,          -- 'mobile' | 'l3vpn' | 'sdwan' | 'broadband'
    state           TEXT DEFAULT 'designed',
                    -- 'designed' | 'reserved' | 'provisioning' | 'active' | 'suspended' | 'terminated'
    service_characteristics JSONB,
    child_services  JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `resource_inventory` (TMF639)
```sql
CREATE TABLE resource_inventory (
    id              TEXT PRIMARY KEY,       -- 'res-VRF-0001'
    service_id      TEXT REFERENCES service_inventory(id),
    resource_type   TEXT NOT NULL,          -- 'VRF' | 'BGP_PEER' | 'IP_SUBNET' | 'INTERFACE' | 'VLAN' | 'VNF' | ...
    name            TEXT NOT NULL,
    device_name     TEXT,
    device_vendor   TEXT,                   -- 'Cisco' | 'Juniper' | 'Nokia'
    config          JSONB,                  -- Actual configuration applied
    state           TEXT DEFAULT 'planned',
                    -- 'planned' | 'allocated' | 'configuring' | 'in_service' | 'maintenance' | 'decommissioned'
    parent_resource_id TEXT REFERENCES resource_inventory(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `audit_log`
```sql
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    order_id        TEXT NOT NULL,
    order_type      TEXT NOT NULL,          -- 'product' | 'service'
    state           TEXT NOT NULL,
    message         TEXT NOT NULL,
    event_type      TEXT,                   -- 'milestone' | 'state_change' | 'error' | 'action'
    actor           TEXT,                   -- 'system' | 'hermes_worker_X' | 'admin'
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_log_order ON audit_log(order_id, created_at);
```

#### `webhook_deliveries`
```sql
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
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    delivered_at    TIMESTAMPTZ
);
```

#### `webhook_registrations`
```sql
CREATE TABLE webhook_registrations (
    id              SERIAL PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    callback_url    TEXT NOT NULL,
    shared_secret   TEXT NOT NULL,          -- HMAC signing key
    event_types     TEXT[],                 -- ['completed', 'failed', 'inProgress', ...]
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

#### `api_keys`
```sql
CREATE TABLE api_keys (
    id              SERIAL PRIMARY KEY,
    key_hash        TEXT NOT NULL UNIQUE,   -- SHA-256 of API key
    name            TEXT NOT NULL,          -- 'CRM-Salesforce-Prod'
    scopes          TEXT[],                 -- ['read:order', 'write:order', ...]
    customer_id     TEXT,
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_used_at    TIMESTAMPTZ
);
```

### 4.2 Redis — Task Queues, Cache, and Coordination

| Key Pattern | Purpose | Data Type |
|-------------|---------|-----------|
| `queue:orders_urgent` | High-priority order queue | List (RQ) |
| `queue:orders_standard` | Normal-priority order queue | List (RQ) |
| `queue:orders_bulk` | Low-priority order queue | List (RQ) |
| `queue:retry` | Retry queue for failed jobs | List (RQ) |
| `queue:webhook_delivery` | Webhook delivery queue | List (RQ) |
| `session:{session_id}` | Worker session cache | Hash (TTL: 30m) |
| `ratelimit:{route}:{key}` | Rate limit counters | Sorted Set |
| `lock:sub:{subscriber_id}` | Subscriber advisory lock | String (TTL: 30s) |
| `pattern_hot:{pattern_id}` | Hot cache for frequent patterns | String (TTL: 5m) |
| `orch:idx:patterns` | Pattern index (service_type → [pids]) | JSON String |
| `orch:pat:{pattern_id}` | Serialized pattern node | JSON String |
| `orch:sub:{subscriber_id}` | Subscriber service model | JSON String |

**Queue Architecture:**
```
Queue                 │ Priority │ Concurrency │ Purpose
──────────────────────┼──────────┼─────────────┼────────────────────────
orders_urgent         │ high     │ 1 worker    │ Restore/emergency orders
orders_standard       │ normal   │ 3 workers   │ Normal provisioning
orders_bulk           │ low      │ 2 workers   │ Bulk/migration orders
retry                 │ normal   │ 1 worker    │ Failed job retries
webhook_delivery      │ normal   │ 2 workers   │ CRM callback delivery
```

### 4.3 Hermes SQLite — Agent Memory

**Location:** `~/.hermes/state.db` (managed by Hermes framework)

| Table | Purpose |
|-------|---------|
| `memory` | Hermes persistent memory entries — orchestration patterns, lessons learned |
| `sessions` | Agent conversation session history |
| `skills` | Loaded skill references and configurations |

**Key Hermes memory operations used by orchestrator:**
```
session_search(query=...)    → search past sessions for similar orchestrations
memory_add(content=...)      → persist a new pattern or lesson
memory_search(query=...)     → recall stored knowledge
```

---

## 5. Configuration Management

### 5.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string: `postgresql://user:pass@host:5432/orchestrator` |
| `REDIS_URL` | Yes | — | Redis connection string: `redis://user:pass@host:6379/0` |
| `DEEPSEEK_API_KEY` | Yes | — | Deepseek API key for LLM calls |
| `WEBHOOK_SECRET` | Yes | — | HMAC-SHA256 shared secret for webhook signing |
| `AUTH_MODE` | No | `api_key` | `api_key` \| `oauth2` \| `both` \| `none` (dev only) |
| `CORS_ORIGINS` | No | `*` | Comma-separated allowed origins |
| `RATE_LIMIT_RPS` | No | `5` | Max requests per second per IP |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `KB_DIR` | No | `/opt/data/telecom-orchestrator/knowledge-base` | Knowledge base root directory |
| `MCP_NETBOX_URL` | No | — | NetBox API base URL |
| `MCP_ANSIBLE_URL` | No | — | Ansible Runner API base URL |
| `MCP_NSO_URL` | No | — | Cisco NSO API base URL |
| `MCP_OSM_URL` | No | — | OSM NFV API base URL |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token for Gateway alerts |
| `SLACK_WEBHOOK_URL` | No | — | Slack incoming webhook URL |
| `DISCORD_WEBHOOK_URL` | No | — | Discord incoming webhook URL |

### 5.2 Config Files (YAML)

**`config/orchestrator.yaml`:**
```yaml
app:
  name: "telecom-orchestrator"
  version: "1.0.0"
  port: 8000

pipeline:
  stages:
    - name: DETECT
      timeout_ms: 1000
      retry: 0
    - name: MASK
      timeout_ms: 500
      retry: 0
    # ... all 14 stages
  thread_pool:
    max_workers: 4

auth:
  mode: api_key
  oauth2:
    introspection_url: "https://auth.example.com/oauth2/introspect"
    client_id: "orchestrator"
    client_secret: "${OAUTH2_SECRET}"

rate_limit:
  enabled: true
  default_rps: 5
  per_route:
    "/api/tmf622/productOrder": 10
    "/api/health": 100

notification:
  channels:
    telegram:
      enabled: true
      token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "-1001234567890"
    slack:
      enabled: true
      webhook_url: "${SLACK_WEBHOOK_URL}"
    discord:
      enabled: false
      webhook_url: "${DISCORD_WEBHOOK_URL}"

webhook:
  retry:
    max_attempts: 3
    backoff_seconds: [10, 30, 90]
    timeout_per_attempt: 15
  signing:
    algorithm: "sha256"
    header: "X-Signature"

validation:
  blocked_keywords:
    - "erase"
    - "reload"
    - "format"
    - "shutdown"
    - "no switchport"
    - "write erase"
    - "delete startup-config"
    - "boot system flash"
  allowed_callback_domains:
    - "*.salesforce.com"
    - "*.acme-corp.com"
    - "*.example.com"

monitoring:
  prometheus:
    enabled: true
    port: 9090
  health_check_interval: 10
```

**`config/product-catalog.yaml`:**
```yaml
products:
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
    provisioning_workflows:
      - "ResourceAllocation"
      - "DeviceConfiguration"
      - "PeeringConfiguration"
      - "ServiceVerification"
      - "StateActivation"
    supported_devices:
      - "cisco-ios-xr"
      - "cisco-ios-xe"
      - "juniper-junos"
      - "nokia-sros"
    sla_tiers:
      - name: "platinum"
        max_fulfillment_sec: 300
        redundancy: "dual_pe_diverse"
      - name: "gold"
        max_fulfillment_sec: 600
        redundancy: "dual_pe_shared"
      - name: "silver"
        max_fulfillment_sec: 900
        redundancy: "single_pe"
      - name: "bronze"
        max_fulfillment_sec: 1800
        redundancy: "single_pe"
  # ... other products
```

### 5.3 Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `LLM_ENABLED` | `true` | Enable/disable Deepseek LLM calls (dev mode: false) |
| `CACHE_FIRST` | `true` | Check pattern cache before LLM (dev mode: false) |
| `MASK_ENABLED` | `true` | Enable data masking before cloud AI |
| `VALIDATE_ENABLED` | `true` | Enable hard-gate security validation |
| `WEBHOOK_DELIVERY_ENABLED` | `true` | Enable CRM webhook dispatch |
| `EXECUTE_ENABLED` | `false` | Enable real device execution (PoC: false, production: true) |
| `NOTIFY_ENABLED` | `true` | Enable TMF641 lifecycle notifications |
| `GATEWAY_ALERTS_ENABLED` | `true` | Enable Telegram/Slack/Discord alerts |
| `PROMETHEUS_METRICS_ENABLED` | `true` | Enable Prometheus metrics endpoint |
| `RATE_LIMIT_ENABLED` | `true` | Enable API rate limiting |
| `CRON_ENABLED` | `true` | Enable scheduled cron jobs |
| `DEBUG_TRACE_DETAIL` | `false` | Include full prompt/responses in trace detail (security risk) |

---

## 6. Testing Strategy

### 6.1 Unit Tests Per Module

| Module | Test File | Coverage Target | Key Test Scenarios |
|--------|-----------|-----------------|--------------------|
| `data_masker.py` | `tests/unit/test_data_masker.py` | 100% | Tokenize MSISDN, IP, hostname; bidirectional mapping; duplicates reuse tokens; empty text; no matches |
| `pattern_engine.py` | `tests/unit/test_pattern_engine.py` | 95% | lookup HIT/MISS; learn + receive; Jaccard matching; confidence lifecycle; corrupt pattern rejection; teach high-confidence |
| `service_model.py` | `tests/unit/test_service_model.py` | 90% | get/save/delete; corruption detection (full/partial/salvage); compute_diff; build_model; versioning |
| `subscriber_lock.py` | `tests/unit/test_subscriber_lock.py` | 95% | acquire/release; TTL expiration; retry timeout; re-entrancy; force_release; concurrent access |
| `validation_gateway.py` | `tests/unit/test_validation_gateway.py` | 100% | Blocked keywords detected; clean plan passes; SSRF callback URL rejected; resource limit enforced |
| `order_decomposer.py` | `tests/unit/test_order_decomposer.py` | 90% | Product found/not found; single-item decomposition; multi-item with dependencies; idempotency; priority routing |
| `orchestrator_brain.py` | `tests/unit/test_orchestrator_brain.py` | 85% | PARSE: structured JSON, unstructured text; MATCH: exact/adapted/novel; REASON: segment→expected state; PLAN: workflow ordering |
| `lifecycle_notifier.py` | `tests/unit/test_lifecycle_notifier.py` | 95% | Milestone emission; state change emission; flush; lifecycle parsing; correct TMF641 schema |
| `webhook_manager.py` | `tests/unit/test_webhook_manager.py` | 85% | Successful delivery; retry with backoff; dead-letter on exhaustion; HMAC signing |
| `kb_loader.py` | `tests/unit/test_kb_loader.py` | 80% | Ontology section extraction; standards keyword matching; product template loading; cache invalidation |
| `mcp_dispatcher.py` | `tests/unit/test_mcp_dispatcher.py` | 80% | Workflow routing; execute delegation; health check aggregation; error propagation |

**Framework:** `pytest` + `pytest-asyncio` + `pytest-cov`

### 6.2 Integration Tests (Pipeline Stages)

| Test Suite | Test File | Key Scenarios |
|------------|-----------|---------------|
| Pipeline stage flow | `tests/integration/test_pipeline_stages.py` | Full foreground pipeline (DETECT→MASK→CACHE); foreground dispatch; trace accumulation; error propagation |
| LLM integration | `tests/integration/test_llm_integration.py` | Deepseek call with mocked response; fallback plan on timeout; cache hit skips LLM |
| Pattern → Plan → Hydrate | `tests/integration/test_pattern_to_plan.py` | Lookup HIT → hydrate plan; MISS → LLM → hydrate; token map roundtrip |
| MCP server dispatch | `tests/integration/test_mcp_dispatch.py` | NetBox mock: allocate IP; Ansible mock: run playbook; error propagation; rollback on failure |
| Webhook delivery | `tests/integration/test_webhook_delivery.py` | POST to CRM mock; retry with backoff; dead-letter queue; HMAC verification |
| Database CRUD | `tests/integration/test_database.py` | PostgreSQL: create/read/update for all tables; Redis: queue enqueue/dequeue, lock acquire/release, cache set/get |

**Framework:** `pytest` with Docker Compose (PostgreSQL + Redis containers)

### 6.3 End-to-End Tests (Request → Provisioning)

| Scenario | Assertions |
|----------|------------|
| **TMF640 Mobile Voice Activation (Gold)** | JSON parsed → mobile detected → MASK tokens → CACHE HIT or MISS → LLM reasoned → HYDRATE reversed → LOCK acquired → MERGE cascaded → VALIDATE passed → EXECUTE stubbed → NOTIFY milestones emitted → VERIFY NEs built → model saved → state=completed |
| **TMF641 L3VPN Activation (Enterprise/Platinum)** | L3VPN detected → correct resource types from KB → plan has VRF, BGP, NMS workflows → lifecycle includes RESOURCE_ALLOCATED, DEVICE_CONFIGURED, PEERING_ESTABLISHED → final state ACTIVE |
| **Unstructured Text — SD-WAN** | Text classified as unstructured → SD-WAN detected → LLM plan generated → plan has CPE_Deployment, Controller_Setup, ZTP_Bootstrap workflows |
| **Security — Blocked Keyword** | "shutdown all interfaces" → VALIDATE stage BLOCKED → order status=blocked → no devices touched |
| **Duplicate externalId** | Second request with same externalId → 409 Conflict or idempotent return |
| **CRM Webhook Callback** | State changes → webhook POSTs to CRM mock → CRM receives TMF641-compliant payload with HMAC signature |
| **Pattern Learning Loop** | First MISS → LLM plan → pattern learned (confidence=0.3) → Second same request → CACHE HIT (confidence boosted to 0.35) → LLM skipped |

**Framework:** `pytest` with FastAPI `TestClient` — full app with in-memory SQLite + fakeredis

### 6.4 Load Tests (5 TPS Target)

| Test | Tool | Target | Configuration |
|------|------|--------|---------------|
| API throughput | `locust` or `k6` | 5 requests/sec sustained | 4 workers, 100 concurrent connections, 5-minute ramp-up |
| Cache hit performance | Custom bench | <5ms p99 | Pre-warmed pattern store, 1000 sequential lookups |
| LLM latency measurement | Custom bench | <90s p99 | Real Deepseek calls with masked payloads (cost-monitored) |
| Pipeline end-to-end | `k6` | <60s p95 for cache hit | Full pipeline minus real device execution |
| Concurrent subscriber locks | Custom bench | 0 deadlocks | 10 concurrent requests for same subscriber, all serialized by lock |

**Targets:**
- **5 TPS sustained** for API ingress
- **p99 latency <5ms** for cache hit decisions
- **p95 <60s** end-to-end pipeline (cache hit path, minus real device execution)
- **p99 <120s** end-to-end with LLM call (cache miss path)

---

## Appendix A: Component Dependency Matrix

| Component | Depends On | Depended On By |
|-----------|------------|----------------|
| `api/gateway.py` | `middleware/*`, all route modules | nginx (reverse proxy) |
| `api/routes/tmf622.py` | `core/order_decomposer.py`, `models/inventory.py` | CRM clients |
| `api/routes/tmf640.py` | `core/pipeline.py` | CRM clients, operators |
| `api/routes/tmf641.py` | `models/inventory.py` | CRM clients |
| `api/routes/tmf638.py` | `models/inventory.py` | CRM / dashboard |
| `api/routes/tmf639.py` | `models/inventory.py` | CRM / dashboard |
| `api/middleware/auth.py` | `models/inventory.py` (api_keys table), Redis (rate limit) | `gateway.py` |
| `api/middleware/rate_limit.py` | Redis | `gateway.py` |
| `core/orchestrator_brain.py` | `knowledge/pattern_engine.py`, `knowledge/kb_loader.py`, `integration/mcp_dispatcher.py` | `core/pipeline.py` |
| `core/pipeline.py` | `core/data_masker.py`, `core/order_decomposer.py`, `core/validation_gateway.py`, `knowledge/*`, `models/*`, `notification/*` | `api/routes/tmf640.py`, `api/routes/tmf622.py` |
| `core/data_masker.py` | — (stdlib only) | `core/pipeline.py` (STAGE 1) |
| `core/validation_gateway.py` | — | `core/pipeline.py` (STAGE 10) |
| `knowledge/pattern_engine.py` | diskcache or Redis | `core/orchestrator_brain.py`, `core/pipeline.py`, `api/routes/patterns.py` |
| `knowledge/kb_loader.py` | file system (KB markdown/YAML files) | `core/orchestrator_brain.py`, `core/pipeline.py` |
| `knowledge/service_resources.py` | — (constant data) | `knowledge/pattern_engine.py`, `knowledge/kb_loader.py`, `notification/lifecycle_notifier.py` |
| `models/service_model.py` | diskcache or Redis | `core/pipeline.py` (STAGES 2, 13) |
| `models/subscriber_lock.py` | diskcache or Redis | `core/pipeline.py` (STAGE 7) |
| `models/inventory.py` | PostgreSQL | All API route modules |
| `integration/mcp_dispatcher.py` | `integration/netbox_client.py`, `integration/ansible_client.py`, etc. | `core/orchestrator_brain.py`, `core/pipeline.py` |
| `notification/lifecycle_notifier.py` | `knowledge/service_resources.py` | `core/pipeline.py` (STAGE 12) |
| `notification/webhook_manager.py` | Redis, PostgreSQL | `core/pipeline.py`, `notification/lifecycle_notifier.py` |
| `notification/gateway_notifier.py` | Telegram/Discord/Slack APIs | `notification/webhook_manager.py`, `cron/*` |

---

## Appendix B: Service Lifecycle States by Type

| Stage | Mobile Voice | L3VPN | SD-WAN | Broadband |
|-------|-------------|-------|--------|-----------|
| 1 | DESIGNED | DESIGNED | DESIGNED | DESIGNED |
| 2 | FEASIBILITY_CHECKED | FEASIBILITY_CHECKED | FEASIBILITY_CHECKED | FEASIBILITY_CHECKED |
| 3 | HLR_PROVISIONED | RESOURCE_ALLOCATED | CPE_DEPLOYED | ONT_PROVISIONED |
| 4 | IMS_REGISTERED | DEVICE_CONFIGURED | TUNNELS_ESTABLISHED | VLAN_ASSIGNED |
| 5 | PCRF_CONFIGURED | PEERING_ESTABLISHED | POLICIES_APPLIED | IP_ALLOCATED |
| 6 | ACTIVE | ACTIVE | ACTIVE | ACTIVE |

---

> **Document Status:** Complete — 6 sections, covering 35+ components across 7 layers, production database schemas, configuration management, and testing strategy. Total: ~1,100 lines.
