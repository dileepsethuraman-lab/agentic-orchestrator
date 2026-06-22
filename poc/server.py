"""
PoC Server — Telecom Agentic Orchestration Engine Demo
========================================================
Demonstrates the full pipeline: ingress → parse → cache → mask → reason → validate → execute → verify.
All external systems (Redis, RabbitMQ, Deepseek, MCP, network devices) are stubbed.
"""

import uuid
import time
import json
import re
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field


app = FastAPI(title="Telecom Orchestrator PoC", version="1.0.0")

# ====================================================================
# Pydantic Models
# ====================================================================

class ProcessRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="TMF640 JSON or unstructured text request")


class TraceStep(BaseModel):
    stage: str
    status: str          # "running" | "done" | "blocked" | "error"
    title: str
    detail: str
    color: str           # "green" | "amber" | "red" | "blue" | "violet" | "cyan"
    icon: str            # emoji
    elapsed_ms: int = 0


class ProcessResponse(BaseModel):
    order_id: str
    format: str          # "tmf640" | "tmf641" | "unstructured"
    status: str          # "completed" | "blocked" | "error"
    trace: list[TraceStep]
    total_ms: int
    final_state: Optional[dict] = None


# ====================================================================
# Data Masker (simplified for demo)
# ====================================================================

MSISDN_RE = re.compile(r'\+?\d{5,15}')
IP_RE = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
HOST_RE = re.compile(r'\b[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)+\b')

class DataMasker:
    def __init__(self):
        self.map = {}
        self.counters = {"msisdn": 0, "ip": 0, "host": 0}

    def mask(self, text: str) -> tuple[str, dict]:
        """Mask sensitive identifiers. Returns (masked_text, {token: real})."""
        # MSISDN
        def _msisdn(m):
            val = m.group(0)
            if val in self.map:
                return self.map[val]
            self.counters["msisdn"] += 1
            tok = f"VAR_MSISDN_{self.counters['msisdn']}"
            self.map[tok] = val
            self.map[val] = tok
            return tok
        text = MSISDN_RE.sub(_msisdn, text)

        # IPs
        def _ip(m):
            val = m.group(0)
            if val in self.map:
                return self.map[val]
            self.counters["ip"] += 1
            tok = f"VAR_IP_{self.counters['ip']}"
            self.map[tok] = val
            self.map[val] = tok
            return tok
        text = IP_RE.sub(_ip, text)

        return text, {k: v for k, v in self.map.items() if k.startswith("VAR_")}


# ====================================================================
# Pipeline Engine
# ====================================================================

BLOCKED_KEYWORDS = ["erase", "reload", "format", "shutdown", "no switchport",
                    "write erase", "delete startup-config"]

SAMPLE_PLANS = {
    "mobile": {
        "workflows": ["HLR_Provisioning", "IMS_Registration", "APN_Configuration", "Charging_Rule_Setup"],
        "params": {
            "msisdn": "VAR_MSISDN_1",
            "apn": "internet",
            "qos_profile": "gold",
            "hlr_commands": ["ADD_SUBSCRIBER", "SET_APN", "ENABLE_VOLTE"],
        }
    },
    "l3vpn": {
        "workflows": ["ResourceAllocation", "DeviceConfiguration", "PeeringConfiguration", "ServiceVerification"],
        "params": {
            "vrf": "CUST-{site}-CORP",
            "asn": 65001,
            "mtu": 9100,
            "redundancy": "dual_pe_diverse",
        }
    },
    "sdwan": {
        "workflows": ["CPE_Deployment", "Tunnel_Setup", "Policy_Configuration", "SLA_Verification"],
        "params": {
            "transport": ["MPLS", "Internet"],
            "encryption": "IPSec",
            "controller": "sdwan-ctrl-01",
        }
    },
    "broadband": {
        "workflows": ["ONT_Provisioning", "VLAN_Assignment", "IP_Pool_Allocation", "Speed_Profile_Apply"],
        "params": {
            "ont_model": "NOKIA-G-010G",
            "vlan": 1001,
            "speed_profile": "1Gbps",
        }
    },
}

def detect_service_type(text: str) -> str:
    """Heuristic: what kind of service is being requested?"""
    t = text.lower()
    if any(w in t for w in ["mobile", "msisdn", "sim", "activate", "voice", "sms"]):
        return "mobile"
    if any(w in t for w in ["l3vpn", "mpls", "vpn", "bgp", "vrf"]):
        return "l3vpn"
    if any(w in t for w in ["sd-wan", "sdwan", "sd wan"]):
        return "sdwan"
    if any(w in t for w in ["broadband", "ftth", "fiber", "ont", "olt"]):
        return "broadband"
    return "mobile"


def run_pipeline(prompt: str) -> ProcessResponse:
    order_id = f"PO-{uuid.uuid4().hex[:8].upper()}"
    trace: list[TraceStep] = []
    t0 = time.time()

    def step(stage: str, status: str, title: str, detail: str, color: str, icon: str):
        trace.append(TraceStep(
            stage=stage, status=status, title=title, detail=detail,
            color=color, icon=icon, elapsed_ms=int((time.time() - t0) * 1000)
        ))

    # ------------------------------------------------------------------
    # STAGE 0 — DETECT FORMAT
    # ------------------------------------------------------------------
    is_json = prompt.strip().startswith("{")
    if is_json:
        fmt = "tmf640"
        step("DETECT", "done", "Format Detection",
             "Input is structured JSON → treating as TMF640 ServiceActivation",
             "cyan", "🔍")
        try:
            payload = json.loads(prompt)
            service_id = payload.get("serviceId", "unknown")
        except json.JSONDecodeError:
            step("DETECT", "error", "JSON Parse Error",
                 "Invalid JSON structure — aborting",
                 "red", "❌")
            return ProcessResponse(order_id=order_id, format="invalid", status="error",
                                   trace=trace, total_ms=int((time.time()-t0)*1000))
    else:
        fmt = "unstructured"
        step("DETECT", "done", "Format Detection",
             "Input is unstructured text → will parse via secure LLM path",
             "cyan", "🔍")

    # ------------------------------------------------------------------
    # STAGE 1 — MASK SENSITIVE DATA (always before cloud)
    # ------------------------------------------------------------------
    masker = DataMasker()
    masked_text, token_map = masker.mask(prompt)

    if token_map:
        tokens_str = ", ".join(f"{t}→{v}" for t, v in list(token_map.items())[:4])
        if len(token_map) > 4:
            tokens_str += f" ... (+{len(token_map)-4} more)"
        step("MASK", "done", "Data Masking — Sensitive Identifiers Tokenized",
             f"Masked {len(token_map)} identifiers before any cloud call:\n{tokens_str}\n\nCloud LLM will NEVER see real identifiers.",
             "violet", "🛡️")
    else:
        step("MASK", "done", "Data Masking",
             "No sensitive identifiers detected — request can proceed unmasked.",
             "violet", "🛡️")

    # ------------------------------------------------------------------
    # STAGE 2 — CACHE CHECK
    # ------------------------------------------------------------------
    service_type = detect_service_type(prompt)
    time.sleep(0.08)  # simulate Redis lookup
    cache_hit = False  # demo: always miss to show full pipeline

    if cache_hit:
        step("CACHE", "done", "Redis Cache — HIT ✓",
             f"Exact match found for {service_type} pattern.\nReturning pre-built orchestration plan from cache.\n⏱ Latency: <5ms (no LLM call needed)",
             "green", "⚡")
    else:
        step("CACHE", "done", "Redis Cache — MISS",
             f"No cached pattern for {service_type} request.\n→ Triggering secure fallback: masked data → Deepseek reasoning.",
             "amber", "📡")

    # ------------------------------------------------------------------
    # STAGE 3 — RAG: KB DOCUMENT LOOKUP
    # ------------------------------------------------------------------
    time.sleep(0.12)
    kb_docs = {
        "mobile": "3GPP TS 29.002 (MAP), 3GPP TS 23.040 (SMS), GSMA IR.92 (VoLTE)",
        "l3vpn": "RFC 4364 (MPLS BGP VPNs), RFC 8299 (L3VPN YANG), MEF 6.2 (EVC Services)",
        "sdwan": "MEF 70 (SD-WAN Service Attributes), RFC 7348 (VXLAN)",
        "broadband": "TR-069 (CWMP), TR-383 (Common YANG Modules for Access Networks)",
    }
    docs = kb_docs.get(service_type, "Generic provisioning standards")
    step("RAG", "done", "Knowledge Base RAG Lookup",
         f"Loaded relevant standards from local KB:\n📄 {docs}\n\nContext will be injected into Deepseek prompt.",
         "blue", "📚")

    # ------------------------------------------------------------------
    # STAGE 4 — DEEPSEEK REASONING (simulated)
    # ------------------------------------------------------------------
    time.sleep(0.25)
    plan = SAMPLE_PLANS.get(service_type, SAMPLE_PLANS["mobile"])

    step("LLM", "done", "Deepseek v4 — Reasoning & Plan Generation",
         f"Sent MASKED data to Deepseek:\n```\n{masked_text[:200]}{'...' if len(masked_text) > 200 else ''}\n```\n\nDeepseek returned abstract blueprint:\n• {len(plan['workflows'])} workflows\n• {len(plan['params'])} parameters\n\nNote: Blueprint uses tokens (VAR_*), not real identifiers.",
         "blue", "🧠")

    # ------------------------------------------------------------------
    # STAGE 5 — LOCAL HYDRATION
    # ------------------------------------------------------------------
    if token_map:
        plan_str = json.dumps(plan)
        for token, real in token_map.items():
            if token.startswith("VAR_"):
                plan_str = plan_str.replace(token, real)
        plan = json.loads(plan_str)
        step("HYDRATE", "done", "Local Parameter Hydration",
             f"Restored real identifiers from local token map.\nAll {len(token_map)} tokens resolved.\n\nPlan now contains real parameters ready for execution.",
             "violet", "💧")
    else:
        step("HYDRATE", "done", "Local Parameter Hydration",
             "No tokens to resolve — plan is already concrete.",
             "violet", "💧")

    # ------------------------------------------------------------------
    # STAGE 6 — WRITE-THROUGH TO REDIS
    # ------------------------------------------------------------------
    time.sleep(0.03)
    step("CACHE", "done", "Redis Write-Through",
         f"Persisting orchestration plan to Redis.\nKey: sha256({service_type}+characteristics)\n\nNext identical request → <5ms cache HIT.",
         "green", "💾")

    # ------------------------------------------------------------------
    # STAGE 7 — VALIDATION GATEWAY
    # ------------------------------------------------------------------
    time.sleep(0.05)
    # Check for destructive keywords
    plan_text = json.dumps(plan).lower()
    blocked = [kw for kw in BLOCKED_KEYWORDS if kw in plan_text or kw in prompt.lower()]
    if blocked:
        step("VALIDATE", "blocked", "Security Gateway — BLOCKED 🚫",
             f"DESTRUCTIVE KEYWORD DETECTED: {', '.join(blocked)}\n\nTransaction ABORTED. Alert raised.\nNo commands sent to devices.",
             "red", "🚫")
        return ProcessResponse(order_id=order_id, format=fmt, status="blocked",
                               trace=trace, total_ms=int((time.time()-t0)*1000))

    # Range validation (demo: always passes)
    step("VALIDATE", "done", "Security Gateway — PASSED ✓",
         "Hard-gate checks completed:\n✓ Pydantic v2 schema validation\n✓ No destructive keywords detected\n✓ Range constraints satisfied (VLAN 1-4094, MTU 68-9216)\n✓ Regex sanitization passed\n\nProceeding to execution.",
         "green", "🔒")

    # ------------------------------------------------------------------
    # STAGE 8 — MCP EXECUTION
    # ------------------------------------------------------------------
    time.sleep(0.15)
    workflow_steps = []
    for i, wf in enumerate(plan["workflows"]):
        dev = ["HLR", "IMS-Core", "PCRF", "SMSC"][i % 4] if service_type == "mobile" else \
              ["PE-RTR-01", "PE-RTR-02", "Route-Reflector", "NMS"][i % 4]
        time.sleep(0.06)
        workflow_steps.append(f"  ✓ {wf} → {dev} (NETCONF OK)")

    step("EXECUTE", "done", "MCP Execution — Workflows Dispatched",
         f"Orchestration plan deployed via MCP:\n" + "\n".join(workflow_steps) +
         f"\n\nAll {len(plan['workflows'])} workflows completed successfully.\nDevices configured. Config committed.",
         "amber", "⚙️")

    # ------------------------------------------------------------------
    # STAGE 9 — VERIFY & LEARN
    # ------------------------------------------------------------------
    time.sleep(0.04)
    final_state = {
        "serviceId": f"SVC-{uuid.uuid4().hex[:6].upper()}",
        "state": "ACTIVE",
        "workflowsExecuted": len(plan["workflows"]),
        "resourcesProvisioned": len(plan["params"]),
    }

    step("VERIFY", "done", "Verification & Pattern Learning",
         f"Post-execution checks:\n✓ Service state: {final_state['state']}\n✓ All resources IN_SERVICE\n✓ End-to-end verification passed\n\nPattern confidence updated: 0.30 → 0.88\nStored to Redis for future cache hits.",
         "green", "✅")

    total_ms = int((time.time() - t0) * 1000)
    return ProcessResponse(
        order_id=order_id,
        format=fmt,
        status="completed",
        trace=trace,
        total_ms=total_ms,
        final_state=final_state,
    )


# ====================================================================
# Routes
# ====================================================================

@app.post("/api/process", response_model=ProcessResponse)
async def process(request: ProcessRequest):
    return run_pipeline(request.prompt)


@app.get("/api/samples")
async def get_samples():
    return {
        "samples": [
            {
                "label": "TMF640 — Activate Mobile Service",
                "text": json.dumps({
                    "serviceId": "MSISDN-088888",
                    "action": "activate",
                    "characteristic": [
                        {"name": "customerSegment", "value": "retail"},
                        {"name": "slaTier", "value": "gold"},
                        {"name": "productId", "value": "mobile-voice"},
                        {"name": "msisdn", "value": "088888"},
                        {"name": "imsi", "value": "310260123456789"},
                    ]
                }, indent=2),
            },
            {
                "label": "Unstructured — Mobile Activation",
                "text": "activate new mobile service 088888 for retail customer with gold SLA, IMSI 310260123456789, enable VoLTE and international roaming",
            },
            {
                "label": "TMF640 — Activate L3VPN",
                "text": json.dumps({
                    "serviceId": "svc-acme-sjc-l3vpn",
                    "action": "activate",
                    "characteristic": [
                        {"name": "customerSegment", "value": "wholesale"},
                        {"name": "slaTier", "value": "platinum"},
                        {"name": "productId", "value": "prod-l3vpn-01"},
                        {"name": "bandwidth", "value": "1000"},
                    ]
                }, indent=2),
            },
            {
                "label": "TMF641 — ServiceOrder L3VPN",
                "text": json.dumps({
                    "externalId": "CRM-12345",
                    "category": "VPN",
                    "action": "add",
                    "characteristic": [
                        {"name": "customerSegment", "value": "enterprise"},
                        {"name": "slaTier", "value": "gold"},
                        {"name": "productId", "value": "prod-l3vpn-01"},
                        {"name": "sites", "value": "3"},
                    ]
                }, indent=2),
            },
            {
                "label": "Unstructured — SD-WAN Request",
                "text": "deploy SD-WAN for branch offices in Tokyo, Singapore and Sydney, dual transport MPLS and Internet, IPSec encryption, enterprise segment, platinum SLA",
            },
            {
                "label": "Security Test — Blocked Keyword",
                "text": "activate mobile service 088888 with gold SLA and shutdown all interfaces",
            },
        ]
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve static files
app.mount("/", StaticFiles(directory="/opt/data/telecom-orchestrator/poc/static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
