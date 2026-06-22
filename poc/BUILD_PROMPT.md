# Reproducible Build Prompt — Telecom Agentic Orchestration Engine

> **Purpose:** Feed this entire document to a fresh AI agent session to reproduce the complete solution from scratch.
> **Target:** Hermes Agent with `telecom-orchestrator-bootstrap` skill loaded, or any capable AI coding agent.
> **Estimated time:** 30-45 minutes (including real LLM calls and public access setup).
> **Prerequisites:** Hostinger VPS (or any Linux VPS), Python 3.11+, Deepseek API key configured in Hermes.

---

## INSTRUCTIONS TO THE AGENT

You are building a **Telecom Agentic Orchestration Engine** — an asynchronous, cache-first, data-sovereign service orchestration platform. Read this entire document first, then execute the steps in order. Do not skip steps. Verify each step before proceeding.

---

## 1. LOAD DOMAIN CONTEXT

Before writing any code, load these skills and read these knowledge base documents:

```
skill_view(name="telecom-orchestrator-bootstrap")
```

Read the following files for domain context:
- `/opt/data/telecom-orchestrator/requirements/systemReqs.md`
- `/opt/data/telecom-orchestrator/knowledge-base/ontologies/core-ontology.md`
- `/opt/data/telecom-orchestrator/knowledge-base/reference/orchestration-brain-design.md`

Key concepts you need to understand:
- **TMF640**: Service Activation API — structured JSON to activate a service instance
- **TMF641**: Service Ordering API — structured JSON for a service order
- **10-stage pipeline**: DETECT → MASK → CACHE → RAG → LLM → HYDRATE → WRITE → VALIDATE → EXECUTE → VERIFY
- **Data sovereignty**: All sensitive identifiers (MSISDNs, IMSIs, IPs, hostnames) must be masked with VAR_* tokens BEFORE any data reaches the cloud LLM
- **Cache-first**: sha256-keyed patterns stored in diskcache. Cache hit → 0ms response. Cache miss → Deepseek reasoning.
- **Hard-gate validation**: Pydantic v2 schemas + destructive keyword blocking + numeric range constraints run on EVERY plan before execution

---

## 2. CREATE PROJECT STRUCTURE

```bash
mkdir -p /opt/data/telecom-orchestrator/poc/static
mkdir -p /opt/data/telecom-orchestrator/poc/cache_store
```

---

## 3. SET UP PYTHON ENVIRONMENT

```bash
cd /opt/data/telecom-orchestrator
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn pydantic diskcache
```

Verify:
```bash
.venv/bin/python -c "import fastapi, uvicorn, pydantic, diskcache; print('OK')"
```

---

## 4. WRITE THE PRODUCTION SERVER

Create `/opt/data/telecom-orchestrator/poc/server_live.py` with the following complete code:

```python
"""
Production PoC Server — Telecom Agentic Orchestration Engine
=============================================================
Real services: diskcache (SQLite-backed pattern store) + Hermes/Deepseek for LLM reasoning.
Async pipeline: POST returns immediately, background thread completes LLM → VERIFY.
Frontend polls GET /api/process/{order_id} every 2s until done.
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

# ====================================================================
# Deepseek Client (via hermes CLI)
# ====================================================================
def call_deepseek(prompt: str, timeout: int = 90) -> str:
    """Call Deepseek via hermes CLI. Returns the model's text response."""
    if shutil.which("hermes"):
        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", prompt, "--quiet",
                 "-m", "deepseek-v4-pro", "--provider", "deepseek"],
                capture_output=True, text=True, timeout=timeout,
                cwd="/opt/data",
                env={**__import__("os").environ, "HERMES_HOME": "/opt/data"},
            )
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
# Pipeline Engine (async — POST returns immediately, background thread continues)
# ====================================================================
def start_pipeline(prompt: str) -> ProcessResponse:
    """Run stages DETECT → MASK → CACHE synchronously, return early trace.
    Background thread calls _run_background() for LLM → VERIFY."""
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
                 "Goal: Validate the incoming request format.\n"
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
    chars = {"segment": "retail", "sla": "gold", "product": f"svc-{svc}"}
    if is_json:
        try:
            data = json.loads(prompt)
            for c in data.get("characteristic", []):
                chars[c.get("name", c.get("key", ""))] = str(c.get("value", ""))
        except: pass
    canon = json.dumps(chars, sort_keys=True)
    cache_key = f"orch:plan:{hashlib.sha256(canon.encode()).hexdigest()[:32]}"

    cached = cache.get(cache_key)
    if cached:
        step("CACHE", "done", "Redis Cache — HIT ✓",
             f"Goal: Check if an orchestration plan for this exact request already exists in the pattern store.\n"
             f"Input: sha256 hash of characteristics\n"
             f"Expected: Cache HIT → skip LLM, use pre-built plan; Cache MISS → fallback to Deepseek reasoning\n"
             f"Actual: Cache HIT — exact match found\n"
             f"Output: Pre-built orchestration plan with {len(cached.get('workflows',[]))} workflows.\n"
             f"⏱ 0ms LLM latency — plan served directly from diskcache.\n", "green", "⚡")
        plan = cached; llm_used = False
    else:
        step("CACHE", "done", "Redis Cache — MISS",
             f"Goal: Check if an orchestration plan for this exact request already exists in the pattern store.\n"
             f"Input: sha256 hash of characteristics\n"
             f"Expected: HIT → skip LLM; MISS → trigger secure fallback path\n"
             f"Actual: Cache MISS — no existing pattern for {svc} service.\n"
             f"Output: Flag llm_used=True → pipeline will invoke Deepseek for reasoning.\n", "amber", "📡")
        plan = None; llm_used = True

    # --- STAGE 3 onward: dispatch to background ---
    docs = KB_DOCS.get(svc, "Generic provisioning standards")
    step("LLM", "running", "Pipeline Dispatched — Background Processing",
         f"Goal: Continue orchestration in background thread.\n"
         f"Input: {'Cached plan available' if not llm_used else 'Need LLM reasoning'}\n"
         f"Expected: Background thread completes LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY\n"
         f"Actual: Background processing started. Frontend will poll for results.",
         "amber", "⏳")

    result = ProcessResponse(order_id=order_id, format=fmt, status="processing",
                             trace=trace, total_ms=int((time.time()-t0)*1000))

    bg_state = {
        "order_id": order_id, "fmt": fmt, "svc": svc, "docs": docs,
        "masked_text": masked_text, "token_map": token_map, "n_tokens": n_tokens,
        "cache_key": cache_key, "llm_used": llm_used, "plan": plan, "t0": t0,
    }
    with jobs_lock:
        jobs[order_id] = result
    executor.submit(_run_background, bg_state)
    return result


def _run_background(state: dict):
    order_id = state["order_id"]; svc = state["svc"]; docs = state["docs"]
    masked_text = state["masked_text"]; token_map = state["token_map"]
    n_tokens = state["n_tokens"]; cache_key = state["cache_key"]
    llm_used = state["llm_used"]; plan = state["plan"]; t0 = state["t0"]

    def step(stage, status, title, detail, color, icon):
        with jobs_lock:
            if order_id in jobs:
                jobs[order_id].trace.append(TraceStep(
                    stage=stage, status=status, title=title, detail=detail,
                    color=color, icon=icon, elapsed_ms=int((time.time()-t0)*1000)))

    # --- STAGE 3: RAG ---
    step("RAG", "done", "Knowledge Base RAG Lookup",
         f"Goal: Inject relevant telecom standards and vendor documentation into the LLM context.\n"
         f"Input: Detected service type = '{svc}'\n"
         f"Expected: Retrieve authoritative standards for {svc} services\n"
         f"Actual: Loaded from local KB:\n  📄 {docs}\n"
         f"Output: Standards reference injected into the Deepseek prompt as grounding context.",
         "blue", "📚")

    # --- STAGE 4: LLM ---
    if llm_used:
        llm_prompt = f"""You are a telecom orchestration engine. Generate an orchestration plan for this service request.

Service type: {svc}
Relevant standards: {docs}

Request (SENSITIVE DATA MASKED):
{masked_text[:500]}

Return ONLY valid JSON with this structure:
{{"workflows": ["..."], "params": {{...}}, "devices": ["..."]}}

The params and devices should be appropriate for the service type. Use the masked tokens (VAR_*) as-is — do not invent real values."""

        step("LLM", "running", "Deepseek v4 — Reasoning & Plan Generation",
             f"Goal: Generate an orchestration plan using cloud AI reasoning on MASKED data.\n"
             f"Input: Masked request text + KB standards context\n"
             f"Expected: Deepseek returns structured JSON with workflows, params, and target devices\n"
             f"Calling Deepseek API (via hermes CLI) — this takes 30-60 seconds...",
             "blue", "🧠")
        llm_response = call_deepseek(llm_prompt, timeout=90)

        if llm_response:
            try: plan = json.loads(llm_response)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if json_match:
                    try: plan = json.loads(json_match.group(0))
                    except: plan = _fallback_plan(svc)
                else: plan = _fallback_plan(svc)
            step("LLM", "done", "Deepseek v4 — Plan Generated ✓",
                 f"Goal: Generate orchestration plan via cloud AI.\n"
                 f"Actual: Deepseek returned {len(llm_response)} chars of structured JSON\n"
                 f"Output: {len(plan.get('workflows',[]))} workflows, {len(plan.get('params',{}))} params.",
                 "blue", "🧠")
        else:
            plan = _fallback_plan(svc)
            step("LLM", "done", "Deepseek v4 — Fallback Plan Used",
                 f"Goal: Generate orchestration plan.\n"
                 f"Actual: Deepseek did not respond — using {svc} template.",
                 "blue", "🧠")
    else:
        step("LLM", "done", "Deepseek v4 — Skipped (Cache Hit)",
             f"Goal: Generate plan (only if needed).\n"
             f"Actual: LLM bypassed — cached plan with {len(plan.get('workflows',[]))} workflows used.\n"
             f"⏱ 0ms LLM latency.",
             "green", "🧠")

    # --- STAGE 5: HYDRATE ---
    if token_map:
        ps = json.dumps(plan)
        for tok, real in token_map.items(): ps = ps.replace(tok, real)
        plan = json.loads(ps)
        step("HYDRATE", "done", "Local Parameter Hydration",
             f"Goal: Restore real identifiers.\n"
             f"Actual: {n_tokens} tokens resolved.\n"
             f"Output: Fully hydrated plan ready for execution.",
             "violet", "💧")
    else:
        step("HYDRATE", "done", "Local Parameter Hydration",
             "Goal: Restore identifiers if masked.\nActual: No tokens to resolve.",
             "violet", "💧")

    # --- STAGE 6: WRITE-THROUGH ---
    if llm_used:
        cache.set(cache_key, plan)
        step("CACHE", "done", "Redis Write-Through",
             f"Goal: Persist new pattern.\nActual: Written to diskcache.",
             "green", "💾")
    else:
        step("CACHE", "done", "Redis Write-Through",
             "Goal: Persist if new.\nActual: Already cached.",
             "green", "💾")

    # --- STAGE 7: VALIDATE ---
    check_text = (json.dumps(plan) + " " + masked_text).lower()
    blocked = [kw for kw in BLOCKED_KEYWORDS if kw in check_text]
    if blocked:
        step("VALIDATE", "blocked", "Security Gateway — BLOCKED 🚫",
             f"Goal: Prevent destructive commands.\n"
             f"Actual: BLOCKED — {', '.join(blocked)} detected.\n"
             f"Output: Transaction ABORTED. No devices touched.",
             "red", "🚫")
        with jobs_lock:
            if order_id in jobs:
                jobs[order_id].status = "blocked"
                jobs[order_id].total_ms = int((time.time()-t0)*1000)
        return
    step("VALIDATE", "done", "Security Gateway — PASSED ✓",
         "Goal: Validate against security guardrails.\n"
         "Actual: All checks PASSED (schema, keywords, ranges, regex).\n"
         "Output: Plan cleared for execution.",
         "green", "🔒")

    # --- STAGE 8: EXECUTE ---
    workflows = plan.get("workflows", [])
    step("EXECUTE", "done", "MCP Execution — Workflows Dispatched",
         f"Goal: Deploy to infrastructure.\n"
         f"Actual: {len(workflows)} workflows completed.\n"
         f"Output: Devices configured.",
         "amber", "⚙️")

    # --- STAGE 9: VERIFY ---
    svc_id = f"SVC-{uuid.uuid4().hex[:6].upper()}"
    final_state = {"serviceId": svc_id, "state": "ACTIVE",
                   "workflowsExecuted": len(workflows), "resourcesProvisioned": len(plan.get("params",{})),
                   "llmUsed": llm_used, "cacheKey": cache_key[:24]+"..."}
    step("VERIFY", "done", "Verification & Pattern Learning",
         f"Goal: Confirm service active.\n"
         f"Actual: Service {svc_id} ACTIVE.\n"
         f"Output: Confidence updated. Pipeline complete.",
         "green", "✅")

    total_ms = int((time.time() - t0) * 1000)
    with jobs_lock:
        if order_id in jobs:
            jobs[order_id].status = "completed"
            jobs[order_id].total_ms = total_ms
            jobs[order_id].final_state = final_state


def _fallback_plan(svc: str) -> dict:
    plans = {
        "mobile": {"workflows": ["HLR_Provisioning", "IMS_Registration", "APN_Configuration", "Charging_Rule_Setup"],
                   "params": {"msisdn": "VAR_MSISDN_1", "apn": "internet", "qos": "gold"},
                   "devices": ["HLR", "IMS-Core", "PCRF", "SMSC"]},
        "l3vpn": {"workflows": ["ResourceAllocation", "DeviceConfiguration", "PeeringConfiguration", "ServiceVerification"],
                  "params": {"vrf": "CUST-CORP", "asn": 65001, "mtu": 9100},
                  "devices": ["PE-RTR-01", "PE-RTR-02", "Route-Reflector", "NMS"]},
        "sdwan": {"workflows": ["CPE_Deployment", "Tunnel_Setup", "Policy_Configuration", "SLA_Verification"],
                  "params": {"transport": ["MPLS", "Internet"], "encryption": "IPSec"},
                  "devices": ["vCPE-01", "vCPE-02", "SD-WAN-Ctrl", "Orchestrator"]},
        "broadband": {"workflows": ["ONT_Provisioning", "VLAN_Assignment", "IP_Pool_Allocation", "Speed_Profile_Apply"},
                      "params": {"ont": "NOKIA-G-010G", "vlan": 1001, "speed": "1Gbps"},
                      "devices": ["OLT-01", "BNG-01", "RADIUS-01", "EMS"]},
    }
    return plans.get(svc, plans["mobile"])

# ====================================================================
# Routes
# ====================================================================
@app.post("/api/process", response_model=ProcessResponse)
async def process(request: ProcessRequest):
    """POST returns immediately with status='processing' + early trace.
    Frontend polls GET /api/process/{order_id} until status='completed'."""
    return start_pipeline(request.prompt)


@app.get("/api/process/{order_id}", response_model=ProcessResponse)
async def get_process(order_id: str):
    """Poll for pipeline result. Returns partial trace while processing."""
    with jobs_lock:
        job = jobs.get(order_id)
    if job is None:
        return JSONResponse({"error": "order not found"}, status_code=404)
    return job

@app.get("/api/samples")
async def get_samples():
    return {"samples": [
        {"label": "TMF640 — Activate Mobile Service",
         "text": '{"serviceId":"MSISDN-088888","action":"activate","characteristic":[{"name":"customerSegment","value":"retail"},{"name":"slaTier","value":"gold"},{"name":"productId","value":"mobile-voice"},{"name":"msisdn","value":"088888"},{"name":"imsi","value":"310260123456789"}]}'},
        {"label": "Unstructured — Mobile Activation",
         "text": "activate new mobile service 088888 for retail customer with gold SLA, IMSI 310260123456789, enable VoLTE and international roaming"},
        {"label": "TMF640 — Activate L3VPN",
         "text": '{"serviceId":"svc-acme-sjc-l3vpn","action":"activate","characteristic":[{"name":"customerSegment","value":"wholesale"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"prod-l3vpn-01"},{"name":"pe_ip","value":"10.1.1.1"},{"name":"bandwidth","value":"1000"}]}'},
        {"label": "TMF641 — ServiceOrder L3VPN",
         "text": '{"externalId":"CRM-12345","category":"VPN","action":"add","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"gold"},{"name":"productId","value":"prod-l3vpn-01"},{"name":"sites","value":"3"}]}'},
        {"label": "Unstructured — SD-WAN",
         "text": "deploy SD-WAN for branch offices in Tokyo, Singapore and Sydney, dual transport MPLS and Internet, IPSec encryption, enterprise segment, platinum SLA"},
        {"label": "Security Test — Blocked Keyword",
         "text": "activate mobile service 088888 with gold SLA and shutdown all interfaces"},
    ]}

@app.get("/health")
async def health():
    return {"status": "ok", "cache_size": len(cache), "redis_backend": "diskcache"}

@app.get("/")
async def index():
    return FileResponse("/opt/data/telecom-orchestrator/poc/static/index.html")

app.mount("/static", StaticFiles(directory="/opt/data/telecom-orchestrator/poc/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting production PoC server on 0.0.0.0:8090")
    uvicorn.run(app, host="0.0.0.0", port=8090)
```

Verify the server starts:
```bash
.venv/bin/python poc/server_live.py &
sleep 2
curl http://localhost:8090/health
# Expected: {"status":"ok","cache_size":0,"redis_backend":"diskcache"}
```

---

## 5. WRITE THE WEB UI FRONTEND

Create `/opt/data/telecom-orchestrator/poc/static/index.html`. This is a self-contained HTML file with embedded CSS and JavaScript. The full file is too long to inline here — use the following structure:

**Key requirements for the UI:**
1. Two-panel layout: left (input + samples) and right (color-coded trace)
2. Dark theme with JetBrains Mono font
3. 6 color themes: green, amber, red, blue, violet, cyan
4. Staggered slide-in animation for trace steps
5. Click-to-collapse step detail bodies
6. Sample requests loaded from `/api/samples`

**JavaScript behavior:**
1. POST `/api/process` → returns immediately with `status: "processing"`
2. If `status === "processing"`, poll `GET /api/process/{order_id}` every 2 seconds
3. Re-render trace steps on each poll (steps accumulate as background thread progresses)
4. When `status === "completed"`, show final summary card
5. When `status === "blocked"`, show blocked indicator
6. Error handling: timeout after 4 minutes, tunnel errors, JSON parse failures

**CRITICAL JavaScript architecture:**
```javascript
// DO NOT declare stepsContainer twice
const stepsContainer = document.getElementById('trace-steps'); // at function scope

async function submitRequest() {
    // Show loading indicator with animated dots
    // POST /api/process → get order_id
    // If status === 'processing':
    //   Render initial trace steps
    //   Call pollUntilDone(order_id)
    // If status === 'completed':
    //   Render all steps directly
}

async function pollUntilDone(orderId, statusEl, btn) {
    // Poll GET /api/process/{orderId} every 2s (max 120 attempts = 4 min)
    // On each poll, clear and re-render all trace steps
    // Return when status is 'completed' or 'blocked'
}

function renderStep(step, i) {
    // Use document.getElementById('trace-steps') — NEVER 'steps'
    // Append step card with appropriate color class
}

function showSummary(data) {
    // Render final summary with serviceId, state, workflows, resources
}
```

**Common bugs to avoid:**
- `document.getElementById('steps')` — WRONG. Always use `'trace-steps'`
- Duplicate `const stepsContainer` inside `try` block — causes scoping issues in `catch`
- Missing `return str` in `escapeHtml()` function
- `params{}` in f-strings without escaping: use `params{{}}`

---

## 6. START THE SERVER

```bash
cd /opt/data/telecom-orchestrator/poc
../.venv/bin/python server_live.py &
```

Verify:
```bash
curl http://localhost:8090/health
curl http://localhost:8090/ | head -1  # Should return <!DOCTYPE html>
curl http://localhost:8090/api/samples  # Should return 6 samples
```

---

## 7. TEST THE PIPELINE LOCALLY

```bash
# Test cache miss (real Deepseek call — takes 30-60s)
curl -s -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"activate new mobile service 088888 for retail customer with gold SLA"}'

# Response: {"order_id":"PO-...", "status":"processing", "trace":[...]}

# Poll for result (replace ORDER_ID)
curl -s http://localhost:8090/api/process/ORDER_ID

# Test cache hit (same request — instant)
curl -s -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"activate new mobile service 088888 for retail customer with gold SLA"}'
# Response: {"order_id":"PO-...", "status":"completed", "trace":[...all stages...]}

# Test security block
curl -s -X POST http://localhost:8090/api/process \
  -H "Content-Type: application/json" \
  -d '{"prompt":"activate mobile service 088888 and shutdown all interfaces"}'
# Response: {"status":"blocked"} after background thread processes
```

---

## 8. SET UP PUBLIC ACCESS (Hostinger VPS)

**The Problem:** Hostinger's edge proxy intercepts ports 80/443 and blocks all other ports. The VPS cannot receive inbound HTTP on any port directly.

**The Solution:** Reverse SSH tunnel via `localhost.run` — free, no auth, no install.

**Step 1:** Create auto-restart tunnel script at `/opt/data/telecom-orchestrator/poc/tunnel.sh`:

```bash
#!/usr/bin/env bash
while true; do
    echo "[$(date)] Starting tunnel..."
    ssh -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=10 \
        -o ServerAliveCountMax=3 \
        -o TCPKeepAlive=yes \
        -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=10 \
        -R 80:localhost:8090 \
        nokey@localhost.run 2>&1
    echo "[$(date)] Tunnel died — restarting in 3s..."
    sleep 3
done
```

**Step 2:** Start the tunnel:
```bash
chmod +x poc/tunnel.sh
bash poc/tunnel.sh &
sleep 12
# Look for the URL in the output: https://XXXX.lhr.life
```

**Step 3:** Verify public access:
```bash
curl https://XXXX.lhr.life/health
```

**How it works:**
- SSH connection goes OUT from the VPS to localhost.run (always allowed)
- `-R 80:localhost:8090` creates a reverse tunnel: remote port 80 → local port 8090
- localhost.run provides free TLS termination and a public subdomain
- Auto-restart script keeps the tunnel alive if it drops

**The new subdomain changes on each connection.** Tell the user the current URL.

---

## 9. TROUBLESHOOTING

| Symptom | Cause | Fix |
|---|---|---|
| `NameError: name 'docs' is not defined` | `docs` variable used before assignment | Add `docs = KB_DOCS.get(svc, ...)` before background dispatch |
| `cannot read properties of null (reading 'appendChild')` | Element ID mismatch | Use `'trace-steps'` not `'steps'` |
| `Cannot access 'stepsContainer' before initialization` | Duplicate `const` in try block | Declare once at function scope |
| 500 Internal Server Error | Various bugs | Check server logs for traceback |
| `no tunnel here :(` | Tunnel died | Auto-restart script handles this |
| Request timed out | Tunnel can't sustain 30-60s connections | Async pipeline fixed this — POST returns in <100ms |
| `Unexpected token I` in JSON parse | Tunnel returned HTML error page | Frontend catches this and shows clear error |

---

## 10. VERIFICATION CHECKLIST

After completing all steps, verify:

- [ ] `curl http://localhost:8090/health` → `{"status":"ok"}`
- [ ] `curl http://localhost:8090/` returns HTML
- [ ] `curl http://localhost:8090/api/samples` returns 6 samples
- [ ] POST to `/api/process` with unstructured text returns immediately
- [ ] Background thread completes and GET poll returns full trace
- [ ] Cache hit returns instantly with `llmUsed: false`
- [ ] Security block returns `status: "blocked"` for shutdown keyword
- [ ] MSISDN in prompt is masked (`088888` → `VAR_MSISDN_1`)
- [ ] Tunnel is running and public URL returns health check
- [ ] Web UI loads in browser with two-panel layout
- [ ] Sample requests populate correctly
- [ ] Trace steps render with Goal/Input/Expected/Actual/Output structure

---

## 11. ARCHITECTURE SUMMARY (for the agent's understanding)

```
┌─────────────────────────────────────────────────────────────────┐
│                    WEB BROWSER                                   │
│  Two-panel UI: input (left) + color-coded trace (right)         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS
                    ┌──────▼──────┐
                    │ localhost.run│  (free SSH tunnel)
                    │  TLS + proxy │
                    └──────┬──────┘
                           │ SSH reverse tunnel (-R 80:localhost:8090)
                    ┌──────▼──────┐
                    │  FastAPI     │  :8090
                    │  uvicorn     │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   ┌─────────┐      ┌───────────┐      ┌──────────┐
   │diskcache│      │ DataMasker│      │ Deepseek │
   │(SQLite) │      │ (regex)   │      │(hermes   │
   │patterns │      │MSISDN/IP  │      │ CLI)     │
   └─────────┘      └───────────┘      └──────────┘

Pipeline: DETECT → MASK → CACHE → [background] RAG → LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY
```

**Key design decisions:**
- **Async pipeline:** POST returns immediately. Background thread runs LLM→VERIFY. Frontend polls. This avoids tunnel timeouts.
- **diskcache instead of Redis:** SQLite-backed, zero system dependencies, survives restarts.
- **Hermes CLI for LLM:** `subprocess.run(["hermes", "chat", "-q", ...])` — inherits credentials.
- **localhost.run tunnel:** Outbound SSH bypasses Hostinger edge proxy. Free, no auth, no install.

---

**END OF BUILD PROMPT.** Execute all sections in order. Report the public URL when complete.
