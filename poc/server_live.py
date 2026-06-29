"""
Production PoC Server — Telecom Agentic Orchestration Engine
=============================================================
Real services: diskcache (Redis-compatible pattern store) + Hermes/Deepseek for LLM reasoning.
Web UI served on 0.0.0.0:8090.
"""

import uuid, time, json, re, subprocess, hashlib, logging, shutil, threading, os
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
# Service Model Store — persistent subscriber representations
# ====================================================================
class ServiceModelStore:
    """Persistent flat representation of a subscriber service, keyed by subscriber_id.
    Created after successful NE update. Used for change detection on repeat requests.

    Runtime validation: get() checks for corruption on every read and repairs
    or rejects poisoned data before it can infect the pipeline."""

    # Thresholds for partial corruption salvage
    MIN_REAL_ATTRS = 3  # minimum real NE attributes to consider salvageable

    def __init__(self, cache: diskcache.Cache):
        self.cache = cache

    def _key(self, subscriber_id: str) -> str:
        return f"orch:sub:{subscriber_id}"

    def get(self, subscriber_id: str) -> dict | None:
        """Load subscriber model with runtime corruption check.
        If corrupted beyond repair, deletes the entry and returns None
        so the pipeline treats it as a fresh provisioning."""
        model = self.cache.get(self._key(subscriber_id))
        if model is None:
            return None
        if not isinstance(model, dict):
            logger.warning("Runtime: non-dict model for %s — deleting", subscriber_id)
            self.delete(subscriber_id)
            return None

        chars = model.get("characteristics", {})
        nes = model.get("network_elements", [])
        ver = model.get("version", 0)

        # Count corruption
        def_chars = sum(1 for v in chars.values() if str(v).startswith("default_"))
        ph_chars  = sum(1 for v in chars.values() if str(v).startswith("<"))
        def_nes = 0
        real_nes = 0
        for ne in nes:
            for v in ne.get("attributes", {}).values():
                sv = str(v)
                if sv.startswith("default_"):
                    def_nes += 1
                elif sv.startswith("<"):
                    pass  # placeholders are ok
                elif sv != "Configured":
                    real_nes += 1

        total_corrupt = def_chars + ph_chars + def_nes

        if total_corrupt == 0:
            return model  # clean — fast path

        # Partially corrupt: try to salvage
        if real_nes >= self.MIN_REAL_ATTRS and def_chars < len(chars):
            logger.warning(
                "Runtime: partial corruption in %s v%d (%d default_* NE, %d default_* chars, "
                "%d real NE attrs). Salvaging real data; will self-heal on next orchestration.",
                subscriber_id, ver, def_nes, def_chars, real_nes)
            # Strip default_* from characteristics so they don't poison MERGE
            clean_chars = {k: v for k, v in chars.items()
                          if not str(v).startswith("default_") and not str(v).startswith("<")}
            model["characteristics"] = clean_chars
            return model

        # Fully corrupt or not enough real data — delete and force fresh provisioning
        logger.warning(
            "Runtime: %s v%d too corrupted (%d default_* NE, %d default_* chars, "
            "only %d real NE attrs). Deleting — will re-provision from scratch.",
            subscriber_id, ver, def_nes, def_chars, real_nes)
        self.delete(subscriber_id)
        return None

    def save(self, subscriber_id: str, model: dict):
        model["version"] = model.get("version", 0) + 1
        model["last_updated"] = datetime.utcnow().isoformat()
        self.cache[self._key(subscriber_id)] = model

    def delete(self, subscriber_id: str):
        key = self._key(subscriber_id)
        if key in self.cache:
            del self.cache[key]

    def compute_diff(self, previous: dict | None, incoming_chars: dict,
                     new_network_elements: list[dict]) -> dict:
        """Compare incoming characteristics and NE state against previous model.
        Returns a subscriberDiff structure for the UI."""
        changed_attrs = {}
        if previous:
            prev_chars = previous.get("characteristics", {})
            for k, v in incoming_chars.items():
                prev_v = prev_chars.get(k)
                if prev_v is not None and str(v) != str(prev_v):
                    changed_attrs[k] = {"from": str(prev_v), "to": str(v)}
            for k in prev_chars:
                if k not in incoming_chars:
                    changed_attrs[k] = {"from": str(prev_chars[k]), "to": "(removed)"}

        # NE-level diffs: which attributes changed per device.
        # Normalize NE names: strip /HSS, /PCF, /MME suffixes for fuzzy matching
        # so "PCRF" matches "PCRF/PCF" and "HLR" matches "HLR/HSS".
        ne_diffs = {}
        if previous:
            prev_nes_raw = {ne["name"]: ne.get("attributes", {})
                           for ne in previous.get("network_elements", [])}
            # Build canonical name → raw name mapping for previous model
            prev_canonical = {}
            for raw_name in prev_nes_raw:
                canonical = raw_name.split("/")[0]  # PCRF/PCF → PCRF
                prev_canonical[canonical] = raw_name

            for ne in new_network_elements:
                name = ne["name"]
                canonical = name.split("/")[0]  # PCRF/PCF → PCRF
                prev_raw = (prev_canonical.get(canonical) or
                           prev_canonical.get(name) or name)
                prev_attrs = prev_nes_raw.get(prev_raw, {})
                curr_attrs = ne.get("attributes", {})
                ne_diff = {}
                for k, v in curr_attrs.items():
                    pv = prev_attrs.get(k)
                    if pv is not None and str(v) != str(pv):
                        ne_diff[k] = {"from": str(pv), "to": str(v)}
                if ne_diff:
                    ne_diffs[name] = ne_diff

        has_changes = bool(changed_attrs or ne_diffs)
        first_run = previous is None

        return {
            "hasPrevious": previous is not None,
            "isFirstRun": first_run,
            "hasChanges": has_changes,
            "changedAttributes": changed_attrs,
            "networkElementDiffs": ne_diffs,
        }

    def build_model(self, subscriber_id: str, svc: str, all_chars: dict,
                    network_elements: list[dict], version: int = 0) -> dict:
        # Merge all NE attributes into characteristics so subsequent
        # MERGE gap-fill and DIFF have complete context — not just the
        # sparse request-level all_chars from unstructured text.
        merged_chars = dict(all_chars)
        for ne in network_elements:
            for k, v in ne.get("attributes", {}).items():
                if k not in merged_chars and k != "status":
                    sv = str(v)
                    if not sv.startswith("default_") and not sv.startswith("<"):
                        merged_chars[k] = v
        return {
            "subscriber_id": subscriber_id,
            "service_type": svc,
            "characteristics": merged_chars,
            "network_elements": [
                {"name": ne["name"], "type": ne["type"],
                 "attributes": dict(ne.get("attributes", {}))}
                for ne in network_elements
            ],
            "version": version,
            "last_updated": datetime.utcnow().isoformat(),
        }

service_models = ServiceModelStore(cache)

# ====================================================================
# Subscriber Lock — prevents concurrent modification race conditions
# ====================================================================
class SubscriberLock:
    """Per-subscriber advisory lock using diskcache (SQLite-backed).

    Design:
    - Lock key: lock:sub:{subscriber_id}
    - Value: {worker_id, acquired_at, ttl_seconds}
    - TTL: 30s (prevents deadlock if worker crashes)
    - Non-blocking acquire with retry (default 5s budget)
    - Re-entrant within same worker
    """

    LOCK_TTL = 30  # seconds
    RETRY_DELAY = 0.1  # seconds
    MAX_RETRIES = 50   # 5 seconds total

    def __init__(self, cache: diskcache.Cache):
        self._cache = cache
        self._local = threading.local()

    def acquire(self, subscriber_id: str, worker_id: str):
        """Context-manager-able acquire. Returns True/False."""
        return _LockContext(self, subscriber_id, worker_id)

    def _try_acquire(self, lock_key: str, worker_id: str) -> bool:
        for _ in range(self.MAX_RETRIES):
            existing = self._cache.get(lock_key)
            now = time.time()
            if existing is None:
                self._cache.set(lock_key,
                    {"worker_id": worker_id, "acquired_at": now},
                    expire=self.LOCK_TTL)
                return True
            if now - existing.get("acquired_at", 0) > self.LOCK_TTL:
                self._cache.set(lock_key,
                    {"worker_id": worker_id, "acquired_at": now},
                    expire=self.LOCK_TTL)
                return True
            if existing.get("worker_id") == worker_id:
                return True  # re-entrant
            time.sleep(self.RETRY_DELAY)
        return False

    def _release(self, lock_key: str, worker_id: str):
        existing = self._cache.get(lock_key)
        if existing and existing.get("worker_id") == worker_id:
            self._cache.delete(lock_key)

    def force_release(self, subscriber_id: str):
        lock_key = f"lock:sub:{subscriber_id}"
        self._cache.delete(lock_key)


class _LockContext:
    """Context manager returned by SubscriberLock.acquire()."""
    def __init__(self, lock: SubscriberLock, subscriber_id: str, worker_id: str):
        self._lock = lock
        self._key = f"lock:sub:{subscriber_id}"
        self._worker = worker_id
        self._acquired = False

    def __enter__(self):
        self._acquired = self._lock._try_acquire(self._key, self._worker)
        return self._acquired

    def __exit__(self, *args):
        if self._acquired:
            self._lock._release(self._key, self._worker)
        return False


subscriber_lock = SubscriberLock(cache)


def extract_subscriber_id(prompt: str, is_json: bool, all_chars: dict) -> str:
    """Extract a stable subscriber identifier from the request."""
    if is_json:
        try:
            data = json.loads(prompt)
            # TMF640: serviceId or msisdn
            sid = data.get("serviceId") or data.get("externalId")
            if sid:
                return sid
        except: pass
    # Fall back to msisdn from characteristics
    msisdn = all_chars.get("msisdn")
    if msisdn:
        return f"MSISDN-{msisdn}"
    # Last resort: hash the prompt
    return f"SUB-{hashlib.sha256(prompt.encode()).hexdigest()[:12].upper()}"


def flatten_plan_params(plan: dict) -> dict:
    """Flatten nested workflow-keyed params into a single flat dict.

    LLMs often produce params like:
      {"HLR_Provisioning": {"msisdn": "...", "imsi": "..."},
       "IMS_Registration": {"msisdn": "...", "codec_profile": "..."}}
    But downstream consumers (MERGE, NE builder, pattern learn) expect flat:
      {"msisdn": "...", "imsi": "...", "codec_profile": "..."}

    Idempotent: if params are already flat (no sub-dicts), returns unchanged.
    """
    params = plan.get("params", {})
    if not params:
        return plan
    # Check if any top-level value is a dict → nested
    if any(isinstance(v, dict) for v in params.values()):
        flat = {}
        for v in params.values():
            if isinstance(v, dict):
                flat.update(v)
        if flat:
            plan["params"] = flat
    return plan


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
    started_at: str = ""

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

KB_DIR = "/opt/data/telecom-orchestrator/knowledge-base"

# ====================================================================
# RDF-Inspired Pattern Engine
# ====================================================================
# Patterns are modeled as named graphs of triples: (subject, predicate, object).
# Subjects are service patterns; predicates are OWL-inspired relationships;
# objects are resources, workflows, attribute constraints, or literal values.
#
# Example triple set for a mobile-voice retail/gold pattern:
#   pattern:mobile-retail-gold   rdf:type              service:MobileVoice
#   pattern:mobile-retail-gold   orch:hasSegment       "retail"
#   pattern:mobile-retail-gold   orch:hasSlaTier       "gold"
#   pattern:mobile-retail-gold   orch:requiresResource res:HLR-HSS
#   res:HLR-HSS                  orch:provisionedBy    wf:HLR_Provisioning
#   res:HLR-HSS                  orch:hasAttribute     [msisdn, imsi, subscriber_profile]
#   orch:hasAttribute            rdfs:domain           orch:Resource
#   orch:hasAttribute            rdfs:range            xsd:string
#   msisdn                       rdf:type              orch:InstanceAttribute
#   customerSegment              rdf:type              orch:ServiceAttribute
#
# InstanceAttributes (msisdn, imsi, pe_ip) are excluded from cache keys —
# they identify specific subscriber/device instances, not service patterns.
# ServiceAttributes (segment, sla, product) define the pattern identity.

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta

@dataclass
class PatternNode:
    """A named pattern capturing a service type + its resource graph."""
    id: str
    service_type: str
    label: str
    characteristics: dict  # service-defining characteristics (segment, sla, product)
    triples: list  # list of [subject, predicate, object] — RDF-like assertions
    resources: list  # derived resource bindings with attributes
    confidence: float = 0.3
    use_count: int = 0
    created_at: str = ""
    last_used: str = ""
    source: str = "auto"  # "auto" | "teach" | "kb"

    def to_dict(self):
        return {
            "id": self.id, "service_type": self.service_type, "label": self.label,
            "characteristics": self.characteristics, "triples": self.triples,
            "resources": self.resources, "confidence": round(self.confidence, 2),
            "use_count": self.use_count, "created_at": self.created_at,
            "last_used": self.last_used, "source": self.source,
        }


class PatternEngine:
    """RDF-inspired pattern store with learning, confidence scoring, and KB reasoning."""

    INSTANCE_ATTRS = {"msisdn", "imsi", "imei", "pe_ip", "hostname", "serviceid",
                       "serial", "loopback", "management_ip"}

    def __init__(self, cache: diskcache.Cache):
        self.cache = cache
        self._index: dict[str, list[str]] = {}  # service_type → [pattern_ids]
        self._load_index()

    def _load_index(self):
        self._index = self.cache.get("orch:idx:patterns", {})

    def _save_index(self):
        self.cache.set("orch:idx:patterns", self._index)

    def _key(self, pid: str) -> str:
        return f"orch:pat:{pid}"

    # ── QUERY ──────────────────────────────────────────────

    def lookup(self, service_type: str, characteristics: dict) -> Optional[PatternNode]:
        """Find best-matching pattern for given characteristics. Returns None if no match."""
        candidates = []
        for pid in self._index.get(service_type, []):
            pat = self._load(pid)
            if pat is None:
                continue
            score = self._match_score(pat.characteristics, characteristics)
            if score > 0:
                candidates.append((score, pat))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], -x[1].confidence))
        return candidates[0][1]

    def _match_score(self, pat_chars: dict, req_chars: dict) -> float:
        """Jaccard-like match: how many service-defining chars match.
        Empty pat_chars (KB-seeded wildcard) matches any request at 0.25 confidence."""
        pat_keys = set(pat_chars.keys())
        req_keys = set(k for k in req_chars if k not in self.INSTANCE_ATTRS)
        if not pat_keys:
            return 0.25  # wildcard — KB-seeded pattern, low confidence
        if not req_keys:
            return 1.0  # no service-defining chars in request → match anything
        intersection = 0
        for k in req_keys & pat_keys:
            if str(pat_chars[k]) == str(req_chars.get(k, "")):
                intersection += 1
        union = len(req_keys | pat_keys)
        return intersection / max(union, 1)

    # ── LEARN ──────────────────────────────────────────────

    def learn(self, service_type: str, characteristics: dict,
              plan: dict, all_chars: dict = None, source: str = "auto") -> PatternNode:
        """Create a new pattern from a cache miss + orchestration plan.
        all_chars includes instance identifiers (msisdn/imsi) for complete resource storage."""
        # Derive service-defining chars (exclude instance identifiers)
        svc_chars = {k: v for k, v in characteristics.items()
                     if k.lower() not in self.INSTANCE_ATTRS}
        pid = f"pat:{service_type}:{hashlib.sha256(json.dumps(svc_chars,sort_keys=True).encode()).hexdigest()[:12]}"

        now = datetime.utcnow().isoformat()
        devices = plan.get("devices", [])
        workflows = plan.get("workflows", [])
        params = plan.get("params", {})
        full_chars = all_chars or {}  # includes msisdn/imsi for complete resource attributes

        # Build RDF triples from plan
        triples = [
            [pid, "rdf:type", f"service:{service_type.capitalize()}Voice" if service_type == "mobile" else f"service:{service_type.upper()}"],
        ]
        for k, v in svc_chars.items():
            triples.append([pid, f"orch:has{k}", str(v)])

        # Build resource entries with attribute inference from KB
        sr = SERVICE_RESOURCES.get(service_type, SERVICE_RESOURCES["mobile"])
        kb_resources = {r["type"]: r for r in sr["required_resources"]}
        resources = []
        for i, dev in enumerate(devices):
            wf = workflows[i] if i < len(workflows) else "Configuration"
            rid = f"res:{dev.replace('/','-').replace(' ','_')}"
            triples.append([pid, "orch:requiresResource", rid])
            triples.append([rid, "orch:provisionedBy", f"wf:{wf}"])

            # Infer attributes from KB
            kb_res = None
            for kb_type, kb_def in kb_resources.items():
                if any(p in dev.lower() for p in kb_type.lower().replace("/"," ").split()):
                    kb_res = kb_def; break
            attrs = {}
            if kb_res:
                for attr in kb_res.get("attributes", []):
                    if attr in params:
                        val = str(params[attr])
                    elif attr in full_chars:
                        val = str(full_chars[attr])
                    else:
                        val = f"<{attr}>"  # placeholder — resolved at orchestration time
                    attrs[attr] = val
                    triples.append([rid, "orch:hasAttribute", f"{attr}={val}"])
            else:
                for k, v in params.items():
                    attrs[k] = str(v)
            resources.append({"name": dev, "workflow": wf,
                              "role": kb_res.get("role","") if kb_res else "",
                              "attributes": attrs})

        node = PatternNode(
            id=pid, service_type=service_type,
            label=f"{service_type} | {svc_chars.get('customerSegment','?')}/{svc_chars.get('slaTier','?')}",
            characteristics=svc_chars, triples=triples,
            resources=resources, confidence=0.3, use_count=1,
            created_at=now, last_used=now, source=source,
        )
        self._save(node)
        self._index_pattern(node)
        logger.info("Pattern learned: %s (confidence=%.2f, %d triples)", pid, node.confidence, len(triples))
        return node

    def reinforce(self, pattern: PatternNode) -> PatternNode:
        """Boost confidence on cache hit. Diminishing returns after 0.9."""
        pattern.use_count += 1
        pattern.last_used = datetime.utcnow().isoformat()
        if pattern.confidence < 0.9:
            pattern.confidence = min(0.95, pattern.confidence + 0.05)
        elif pattern.confidence < 0.98:
            pattern.confidence = min(0.98, pattern.confidence + 0.005)
        self._save(pattern)
        return pattern

    def teach(self, triples: list, source: str = "teach") -> PatternNode:
        """Manual knowledge injection — high confidence, can override auto-learned."""
        svc_type = "mobile"
        chars = {}
        for s, p, o in triples:
            if p.startswith("orch:has") and not p.endswith("Resource"):
                chars[p.replace("orch:has", "")] = o
            if p == "rdf:type" and o.startswith("service:"):
                raw = o.replace("service:", "").lower()
                # Normalize: MobileVoice → mobile, L3VPN → l3vpn
                for sv in ["mobile", "l3vpn", "sdwan", "broadband"]:
                    if sv in raw: svc_type = sv; break
                if svc_type == "mobile" and "voice" not in raw:
                    pass  # keep default
        pid = f"pat:taught:{hashlib.sha256(json.dumps(triples,sort_keys=True).encode()).hexdigest()[:12]}"
        now = datetime.utcnow().isoformat()
        label = f"{svc_type} | " + " / ".join(f"{k}={v}" for k,v in list(chars.items())[:3])
        node = PatternNode(
            id=pid, service_type=svc_type, label=label,
            characteristics=chars, triples=triples, resources=[],
            confidence=0.9, use_count=0, created_at=now, last_used=now, source=source,
        )
        self._save(node)
        self._index_pattern(node)
        logger.info("Pattern taught: %s (confidence=%.2f)", pid, node.confidence)
        return node

    # ── PATTERN INSPECTION ─────────────────────────────────

    def list_all(self) -> list[dict]:
        """Return all known patterns with metadata."""
        result = []
        for svc_type, pids in self._index.items():
            for pid in pids:
                pat = self._load(pid)
                if pat:
                    result.append({
                        "id": pat.id, "service_type": pat.service_type,
                        "label": pat.label, "confidence": round(pat.confidence, 2),
                        "use_count": pat.use_count, "triples_count": len(pat.triples),
                        "source": pat.source, "last_used": pat.last_used,
                    })
        return sorted(result, key=lambda x: (-x["confidence"], -x["use_count"]))

    def get(self, pid: str) -> Optional[dict]:
        pat = self._load(pid)
        return pat.to_dict() if pat else None

    # ── INTERNAL ───────────────────────────────────────────

    def _save(self, node: PatternNode):
        self.cache.set(self._key(node.id), node)

    def _load(self, pid: str) -> Optional[PatternNode]:
        """Load pattern with runtime validation.
        Rejects patterns with empty resources, < 3 triples, or unreadable data."""
        try:
            node = self.cache.get(self._key(pid))
        except Exception:
            logger.warning("Runtime: unreadable pattern %s — deleting", pid)
            self._unindex(pid)
            return None
        if node is None:
            return None
        if not hasattr(node, 'resources') or not node.resources:
            logger.warning("Runtime: empty pattern %s (no resources) — deleting", pid)
            self._unindex(pid)
            return None
        if not hasattr(node, 'triples') or len(node.triples) < 3:
            logger.warning("Runtime: skeleton pattern %s (%d triples) — deleting",
                          pid, len(getattr(node, 'triples', [])))
            self._unindex(pid)
            return None
        # Check for default_* contamination in resource attributes
        def_count = 0
        for r in getattr(node, 'resources', []):
            for v in r.get('attributes', {}).values():
                if str(v).startswith("default_"):
                    def_count += 1
        if def_count > 0:
            # Pattern can still be used (attribute names are correct even if
            # values are placeholders), but log warning so we know it needs
            # refresh from a successful LLM run.
            logger.warning(
                "Runtime: pattern %s has %d default_* resource attrs — "
                "will be refreshed on next cache-miss LLM run", pid, def_count)
        return node

    def _unindex(self, pid: str):
        """Remove a pattern ID from the index and delete its cache entry."""
        for svc, pid_list in self._index.items():
            if pid in pid_list:
                pid_list.remove(pid)
        self._save_index()
        key = self._key(pid)
        if key in self.cache:
            del self.cache[key]

    def _index_pattern(self, node: PatternNode):
        if node.service_type not in self._index:
            self._index[node.service_type] = []
        if node.id not in self._index[node.service_type]:
            self._index[node.service_type].append(node.id)
        self._save_index()


# Global pattern engine
patterns = PatternEngine(cache)


# ====================================================================
# DSL Engine — YAML-defined deterministic service orchestration
# ====================================================================
# The DSL cache provides static, explicitly-authored orchestration
# templates as an alternative to the auto-learning Pattern Engine.
# Each service (mobile, l3vpn, sdwan, broadband) has YAML DSL files
# under knowledge-base/dsl-definitions/ that define:
#   - Service definition (TMF properties, lifecycle, relationships)
#   - Network elements (devices, prefetch workflows, attributes)
#   - Operations (activate, modify, etc. with supporting services)
#   - Consumer errors (error codes per lifecycle state)
#
# DSL expressions use ~path syntax to reference request characteristics:
#   ~request.characteristic[msisdn].value  → "447700123456"
#   ~request.characteristic[apn].value     → "ims.gold.mnc015.mcc234.gprs"
#
# When selected, the DSL engine ALWAYS returns a plan for any known
# service type — it is a deterministic template engine, not a
# probabilistic matcher.

import yaml
import jsonschema

# ── DSL Schema Validation ────────────────────────────────────────
# Schemas live under knowledge-base/system-docs/dsl-specification-schema/schemas/
# Each schema defines a configType const that maps to the DSL YAML configType field.
# The DSLEngine loads schemas once at startup and validates every YAML file on load.


def _load_dsl_schemas() -> dict[str, dict]:
    """Load all DSL JSON schemas from the schema directory.

    Returns a dict mapping configType const → (schema, filename).
    Called once at DSLEngine startup.
    """
    schemas = {}
    schema_dir = os.path.join(KB_DIR, "system-docs/dsl-specification-schema/schemas")
    if not os.path.isdir(schema_dir):
        logger.warning("DSL schema directory not found: %s", schema_dir)
        return schemas

    for fname in os.listdir(schema_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(schema_dir, fname)
        try:
            with open(path) as f:
                schema = json.load(f)
            ct = schema.get("properties", {}).get("configType", {}).get("const")
            if ct:
                schemas[ct] = {"schema": schema, "filename": fname,
                               "required": schema.get("required", []),
                               "title": schema.get("title", fname)}
                logger.debug("DSL schema: %s → %s (%s)", ct, fname,
                            schema.get("title", ""))
        except Exception as e:
            logger.error("DSL: failed to load schema %s: %s", fname, e)

    logger.info("DSL: loaded %d schemas (%s)",
               len(schemas), ", ".join(schemas.keys()))
    return schemas


class DSLEngine:
    """YAML DSL-based deterministic service orchestration engine.

    Loads DSL definitions from knowledge-base/dsl-definitions/ at startup
    and validates every YAML file against its JSON Schema from
    knowledge-base/system-docs/dsl-specification-schema/schemas/.

    On lookup, constructs an orchestration plan by resolving ~expression
    references against request characteristics.  Tracks _if_ condition
    evaluation per NE and reports provenance (template file, version,
    schema validation status) in the patternMatch output.
    """

    INSTANCE_ATTRS = {"msisdn", "imsi", "imei", "pe_ip", "hostname",
                       "serviceid", "serial", "loopback", "management_ip"}

    # ~expression regex: ~path.to.value
    DYN_EXPR = re.compile(r'^~(.*)$')

    def __init__(self, dsl_dir: str = None):
        self._dsl_dir = dsl_dir or f"{KB_DIR}/dsl-definitions"
        self._definitions: dict[str, dict] = {}  # svc → merged DSL
        self._loaded = False
        self._schemas: dict[str, dict] = {}  # configType → {schema, filename, ...}
        self._validation_log: list[dict] = []  # load-time validation issues

    # ── LOAD ──────────────────────────────────────────────

    def load(self) -> dict[str, dict]:
        """Load and index all DSL YAML files with schema validation.

        Returns the loaded definitions.
        """
        if self._loaded:
            return self._definitions

        # Step 1: Load JSON schemas
        self._schemas = _load_dsl_schemas()
        self._validation_log.clear()

        # Step 2: Load the DSL index
        index_path = f"{self._dsl_dir}/dsl-index.yaml"
        try:
            with open(index_path) as f:
                idx = yaml.safe_load(f)
        except Exception as e:
            logger.error("DSL: failed to load index %s: %s", index_path, e)
            return {}

        dsl_index = idx.get("dsl_index", {}) if idx else {}

        for svc, files in dsl_index.items():
            definition = {
                "service_type": svc,
                "domain": files.get("domain", ""),
                "detection_keywords": files.get("detection_keywords", []),
                "service_definition": None,
                "network_elements": [],
                "operations": None,
                "consumer_errors": None,
                "_provenance": {},  # per-file metadata
            }

            # Load service definition
            sd_file = files.get("service_definition")
            if sd_file:
                sd = self._load_yaml_validated(f"{self._dsl_dir}/{sd_file}")
                if sd:
                    definition["service_definition"] = sd

            # Load network elements
            ne_file = files.get("network_elements")
            if ne_file:
                ne_data = self._load_yaml_validated(f"{self._dsl_dir}/{ne_file}")
                if ne_data:
                    nes = ne_data.get("network_elements", ne_data.get("networkElements", []))
                    parsed = []
                    for entry in nes:
                        for name, spec in entry.items():
                            prefetch = spec.get("prefetch", {})
                            net_chars = spec.get("networkCharacteristics", {})
                            # Merge NE-level _if_ with prefetch-level _if_
                            ne_conditions = list(spec.get("_if_", []))
                            prefetch_conditions = prefetch.get("_if_", [])
                            if isinstance(prefetch_conditions, str):
                                prefetch_conditions = [prefetch_conditions]
                            all_conditions = ne_conditions + prefetch_conditions
                            parsed.append({
                                "name": name,
                                "workflow": prefetch.get("workflow", f"{name}_Config").split("/")[-1].replace(".sw.yaml", ""),
                                "id": spec.get("id", f"{name}-01"),
                                "state": spec.get("state", "active"),
                                "attributes": [k for k in net_chars.keys()
                                              if not k.startswith("_")],
                                "conditions": all_conditions,
                                "_source_file": ne_file,
                            })
                    definition["network_elements"] = parsed

            # Load operations
            ops_file = files.get("operations")
            if ops_file:
                ops = self._load_yaml_validated(f"{self._dsl_dir}/{ops_file}")
                if ops:
                    definition["operations"] = ops

            # Load consumer errors
            ce_file = files.get("consumer_errors")
            if ce_file:
                ce = self._load_yaml_validated(f"{self._dsl_dir}/{ce_file}")
                if ce:
                    definition["consumer_errors"] = ce

            self._definitions[svc] = definition
            logger.info("DSL: loaded %s → %d NEs (%s)",
                       svc, len(definition["network_elements"]),
                       ", ".join(n["name"] for n in definition["network_elements"]))

        # Step 3: Report validation summary
        if self._validation_log:
            issues_by_file = {}
            for entry in self._validation_log:
                f = entry.get("file", "?")
                issues_by_file.setdefault(f, []).append(entry)
            for fpath, issues in issues_by_file.items():
                logger.warning("DSL validation: %s — %d issue(s): %s",
                              os.path.basename(fpath), len(issues),
                              "; ".join(i.get("message", "?")[:80] for i in issues[:3]))
        else:
            logger.info("DSL: all YAML files passed schema validation ✓")

        self._loaded = True
        return self._definitions

    def _load_yaml_validated(self, path: str) -> dict | None:
        """Load a YAML file and validate against its JSON Schema.

        Validation is advisory — failures are logged but the YAML is still
        returned so the engine can operate with partially-valid data.
        """
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.error("DSL: failed to load %s: %s", path, e)
            self._validation_log.append({
                "file": path, "severity": "error",
                "message": f"YAML parse failed: {e}",
            })
            return None

        if not isinstance(data, dict):
            logger.error("DSL: %s is not a mapping", path)
            return None

        # Determine expected configType and schema
        ct = data.get("configType", "")
        schema_info = self._schemas.get(ct)

        if not schema_info:
            issue = f"Unknown configType '{ct}' — no matching schema loaded"
            logger.warning("DSL: %s — %s", os.path.basename(path), issue)
            self._validation_log.append({
                "file": path, "severity": "warning",
                "message": issue,
            })
            return data  # return anyway — best-effort

        # Validate required fields
        required = schema_info.get("required", [])
        missing = [r for r in required if r not in data]
        if missing:
            issue = f"Missing required fields: {missing}"
            logger.warning("DSL: %s — %s (schema: %s)",
                          os.path.basename(path), issue, schema_info["filename"])
            self._validation_log.append({
                "file": path, "severity": "warning",
                "message": issue,
                "schema": schema_info["filename"],
            })

        # Full JSON Schema validation
        try:
            jsonschema.validate(instance=data, schema=schema_info["schema"])
        except jsonschema.ValidationError as e:
            issue = f"Schema violation: {e.message}"[:120]
            logger.warning("DSL: %s — %s (at %s)",
                          os.path.basename(path), issue, " → ".join(str(p) for p in e.absolute_path))
            self._validation_log.append({
                "file": path, "severity": "warning",
                "message": issue,
                "schema_path": " → ".join(str(p) for p in e.absolute_path),
                "schema": schema_info["filename"],
            })
        except jsonschema.SchemaError as e:
            logger.error("DSL: schema %s is invalid: %s", schema_info["filename"], e)

        return data

    # ── QUERY ──────────────────────────────────────────────

    def lookup(self, service_type: str, characteristics: dict,
               operation: str = "activate") -> dict | None:
        """Populate the DSL templates against the request.

        DSL architecture (from schemas):
          1. Service DSL — master template that flattens the incoming request
             by resolving all ~request.characteristic[key].value references.
          2. Intent DSL (operations.yaml) — per-operation mapping of
             supporting services, each with parentToChildRelationship
             (supports/relatesTo/creates) and service characteristics.
          3. Network Elements — reference data defining physical/virtual NEs,
             each with a prefetch.workflow (CNCF Serverless Workflow .sw.yaml)
             and network characteristics.

        The connection between supporting services and NEs comes from telecom
        domain knowledge — not from an invented matching algorithm.

        Returns a DSL template dict with populated service definition,
        intent mapping, and NE references.
        """
        if not self._loaded:
            self.load()

        dsl = self._definitions.get(service_type)
        if not dsl:
            logger.info("DSL: no definition for service=%s", service_type)
            return None

        # ── Populate Service DSL ──
        sd = dsl.get("service_definition") or {}
        populated_sd = self._resolve_template(
            sd, characteristics, operation,
            exclude_keys={"configType", "version", "systemCode", "tmfProperties"}
        ) if sd else {}

        # Extract TMF metadata
        tmf = sd.get("tmfProperties", {}) if sd else {}
        system_code = sd.get("systemCode", service_type)
        version = sd.get("version", "?")

        # ── Populate Intent DSL ──
        ops_dsl = dsl.get("operations") or {}
        intent = self._populate_intent(ops_dsl, characteristics, operation)

        # ── NE reference data ──
        nes = dsl.get("network_elements", [])
        # Include all NEs with resolved characteristics (no matching/filtering)
        populated_nes = []
        for ne in nes:
            ne_name = ne["name"]
            ne_workflow = ne.get("workflow", "")
            ne_attrs = ne.get("attributes", [])
            conditions = ne.get("conditions", [])
            source_file = ne.get("_source_file", "")

            # Check _if_ conditions
            decision = "INCLUDE"
            skip_reason = None
            if conditions:
                if not self._eval_conditions(conditions, characteristics, operation=operation):
                    decision = "SKIP"
                    skip_reason = "Condition(s) not met"

            # Resolve NE attributes from request characteristics
            resolved_attrs = {}
            for attr in ne_attrs:
                val = characteristics.get(attr)
                if val is not None and not str(val).startswith("default_"):
                    resolved_attrs[attr] = val
                else:
                    resolved_attrs[attr] = f"<{attr}>"

            populated_nes.append({
                "name": ne_name,
                "workflow": ne_workflow,
                "decision": decision,
                "skip_reason": skip_reason,
                "conditions": list(conditions),
                "attributes": resolved_attrs,
                "ne_id": ne.get("id", ""),
                "state": ne.get("state", "active"),
                "source_file": source_file,
            })

        # Build the populated DSL plan
        included_nes = [n for n in populated_nes if n["decision"] == "INCLUDE"]
        skipped_nes = [n for n in populated_nes if n["decision"] == "SKIP"]

        plan = {
            "workflows": [n["workflow"] for n in included_nes],
            "params": {k: v for n in included_nes for k, v in n["attributes"].items()},
            "devices": [n["name"] for n in included_nes],
            "_dsl_template": {
                "service_type": service_type,
                "operation": operation,
                "system_code": system_code,
                "version": version,
                "tmf_name": tmf.get("name", ""),
                "tmf_description": tmf.get("description", ""),
                "populated_service_definition": populated_sd,
                "intent": intent,
                "network_elements": populated_nes,
            },
        }
        logger.info("DSL: populated template for %s/%s → %d NEs included, %d skipped",
                   service_type, operation, len(included_nes), len(skipped_nes))
        return plan

    def _populate_intent(self, ops_dsl: dict, characteristics: dict,
                         operation: str) -> dict:
        """Extract and populate the Intent DSL for a given operation."""
        lifecycle = ops_dsl.get("lifecycle", {}) or {}
        ack = lifecycle.get("acknowledged", {}) or {}
        op_services = ack.get("supportingServices", [])

        intent = {
            "operation": operation,
            "lifecycle_stage": "acknowledged",
            "supporting_services": [],
        }

        for entry in op_services:
            if not isinstance(entry, dict):
                continue
            for svc_name, svc_def in entry.items():
                relationship = svc_def.get("parentToChildRelationship", "supports")
                inner_services = svc_def.get("supportingServices", [])
                resolved_chars = {}
                for inner in inner_services:
                    sc = inner.get("serviceCharacteristics", {})
                    for attr, expr in sc.items():
                        if attr.startswith("_"):
                            continue
                        resolved = self._resolve_expr_value(
                            str(expr), characteristics)
                        resolved_chars[attr] = resolved

                intent["supporting_services"].append({
                    "name": svc_name,
                    "relationship": relationship,
                    "characteristics": resolved_chars,
                })

        return intent

    def _resolve_template(self, template: dict, chars: dict,
                          operation: str,
                          exclude_keys: set = None) -> dict:
        """Recursively resolve ~expressions in a template dict."""
        if exclude_keys is None:
            exclude_keys = set()
        result = {}

        # Top-level: include metadata keys that carry template provenance
        for key in ("configType", "version", "systemCode"):
            if key in template:
                result[key] = template[key]

        # Resolve tmfProperties (keep structure, resolve ~expressions in values)
        tmf = template.get("tmfProperties", {})
        if tmf:
            result["tmfProperties"] = self._resolve_dict_values(
                tmf, chars, exclude_keys={"configType"})

        # Resolve lifecycle
        lc = template.get("lifecycle", {})
        if lc:
            result["lifecycle"] = self._resolve_dict_values(
                lc, chars, exclude_keys={"configType"})

        # Resolve variables (substitute ~expressions)
        vars_dict = template.get("variables", {})
        if vars_dict:
            result["variables"] = {}
            for k, v in vars_dict.items():
                if isinstance(v, str) and v.startswith("~"):
                    result["variables"][k] = self._resolve_expr_value(v, chars)
                else:
                    result["variables"][k] = v

        # Resolve shortcuts
        shortcuts = template.get("shortcuts", {})
        if shortcuts:
            result["shortcuts"] = shortcuts

        # Resolve outstanding
        outstanding = template.get("outstanding", {})
        if outstanding:
            result["outstanding"] = self._resolve_dict_values(
                outstanding, chars, exclude_keys={"configType"})

        # Preserve entityRelationship, serviceRelationship as-is
        for rel_key in ("entityRelationship", "serviceRelationship"):
            if rel_key in template:
                result[rel_key] = template[rel_key]

        return result

    def _resolve_dict_values(self, d: dict, chars: dict,
                             exclude_keys: set = None) -> dict:
        """Recursively resolve ~expressions in dict values."""
        if exclude_keys is None:
            exclude_keys = set()
        result = {}
        for k, v in d.items():
            if k.startswith("_") or k in exclude_keys:
                result[k] = v
            elif isinstance(v, dict):
                result[k] = self._resolve_dict_values(v, chars, exclude_keys)
            elif isinstance(v, list):
                result[k] = [
                    self._resolve_dict_values(item, chars, exclude_keys)
                    if isinstance(item, dict)
                    else (self._resolve_expr_value(str(item), chars)
                          if isinstance(item, str) and item.startswith("~")
                          else item)
                    for item in v
                ]
            elif isinstance(v, str) and v.startswith("~"):
                result[k] = self._resolve_expr_value(v, chars)
            else:
                result[k] = v
        return result

    def _resolve_expr_value(self, expr: str, chars: dict) -> str:
        """Resolve a single ~request.characteristic[key].value expression."""
        m = re.match(r"~request\.characteristic\[(\w+)\]\.value", expr)
        if m:
            attr = m.group(1)
            val = chars.get(attr, "")
            if val is not None and str(val) != "" and not str(val).startswith("default_"):
                return str(val)
            return f"<{attr}>"  # unresolved placeholder
        return expr  # not a recognized expression, return as-is

    def _eval_conditions(self, conditions: list, chars: dict,
                          operation: str = "activate") -> bool:
        """Evaluate DSL _if_ conditions against request context.

        Supports expressions:
          ~request.characteristic[key].value == 'val'
          ~request.characteristic[key].value != 'val'
          ~request.action == 'activate'
          ~request.operation == 'activate'

        All conditions must pass (AND logic).
        """
        for cond in conditions:
            cond = str(cond)
            # ── ~request.action == 'value' ──
            m = re.match(r"~request\.action\s*==\s*['\"](.+)['\"]", cond)
            if m:
                if operation != m.group(1):
                    return False
                continue
            m = re.match(r"~request\.action\s*!=\s*['\"](.+)['\"]", cond)
            if m:
                if operation == m.group(1):
                    return False
                continue
            m = re.match(r"~request\.operation\s*==\s*['\"](.+)['\"]", cond)
            if m:
                if operation != m.group(1):
                    return False
                continue
            m = re.match(r"~request\.operation\s*!=\s*['\"](.+)['\"]", cond)
            if m:
                if operation == m.group(1):
                    return False
                continue

            # ── ~request.characteristic[key].value == 'value' ──
            m = re.match(r"~request\.characteristic\[(\w+)\]\.value\s*==\s*['\"](.+)['\"]", cond)
            if m:
                attr, expected = m.group(1), m.group(2)
                actual = str(chars.get(attr, ""))
                if actual != expected:
                    return False
                continue
            m = re.match(r"~request\.characteristic\[(\w+)\]\.value\s*!=\s*['\"](.+)['\"]", cond)
            if m:
                attr, not_expected = m.group(1), m.group(2)
                actual = str(chars.get(attr, ""))
                if actual == not_expected:
                    return False
                continue
        return True

    # ── EXPRESSION RESOLUTION ──────────────────────────────

    def resolve_expr(self, expr: str, chars: dict, all_chars: dict) -> str:
        """Resolve ~request.characteristic[key].value expressions against chars."""
        m = self.DYN_EXPR.match(str(expr))
        if not m:
            return str(expr)
        path = m.group(1)
        # Parse: ~request.characteristic[msisdn].value
        attr_match = re.match(r"request\.characteristic\[(\w+)\]\.value", path)
        if attr_match:
            attr = attr_match.group(1)
            val = all_chars.get(attr) or chars.get(attr, "")
            return str(val)
        return str(expr)

    def to_pattern_match(self, service_type: str) -> dict:
        """Build a patternMatch structure for the UI (DSL mode).

        Includes DSL provenance: template file, version, schema used,
        and validation status from load time.
        """
        dsl = self._definitions.get(service_type, {})
        sd = dsl.get("service_definition", {}) or {}

        # Collect file-level provenance
        source_files = []
        for ne in dsl.get("network_elements", []):
            sf = ne.get("_source_file", "")
            if sf and sf not in source_files:
                source_files.append(sf)

        # Schema validation status for this service's files
        schema_status = "unknown"
        schema_warnings = []
        for entry in self._validation_log:
            f = entry.get("file", "")
            if any(sf in f for sf in source_files):
                schema_warnings.append(entry.get("message", ""))
        if not source_files:
            schema_status = "no files loaded"
        elif schema_warnings:
            schema_status = f"warnings ({len(schema_warnings)} issue(s))"
        else:
            schema_status = "validated ✓"

        return {
            "result": "DSL",
            "patternId": f"dsl:{service_type}",
            "patternLabel": f"DSL → {dsl.get('domain', service_type)}",
            "confidence": 1.0,  # DSL is always authoritative
            "useCount": 0,
            "triplesCount": 0,
            "resourcesCount": len(dsl.get("network_elements", [])),
            "compareLogic": "DSL template — deterministic mapping (no Jaccard matching)",
            "requestChars": {},
            "patternChars": {},
            "matchedKeys": [],
            "mismatchedKeys": [],
            "extraKeys": [],
            "excludedInstanceAttrs": sorted(self.INSTANCE_ATTRS),
            "score": 1.0,
            # ── DSL provenance metadata ──
            "dslProvenance": {
                "serviceType": service_type,
                "domain": dsl.get("domain", ""),
                "templateVersion": sd.get("version", "unknown"),
                "systemCode": sd.get("systemCode", ""),
                "sourceFiles": source_files,
                "schemaStatus": schema_status,
                "schemaWarnings": schema_warnings[:5] if schema_warnings else [],
                "totalNEsDefined": len(dsl.get("network_elements", [])),
            },
        }


# Global DSL engine
dsl_engine = DSLEngine()

# Cache engine selection (default: "pattern" — can be toggled via API)
_cache_engine: str = "pattern"  # "pattern" | "dsl"


def set_cache_engine(engine: str):
    """Set the active cache engine: 'pattern' or 'dsl'."""
    global _cache_engine
    if engine not in ("pattern", "dsl"):
        raise ValueError(f"Unknown cache engine: {engine}")
    _cache_engine = engine
    logger.info("Cache engine switched to: %s", engine)


def get_cache_engine() -> str:
    return _cache_engine


def seed_kb_patterns():
    """Pre-seed pattern store from KB resource definitions.

    Each KB service definition becomes a base pattern with correct attribute
    lists.  Confidence starts at 0.25 (auto-seeded) and increases when real
    orchestrations confirm the pattern.  This means even the first unstructured
    request hits the cache and gets KB-derived attribute names correct — no
    default_* placeholders ever reach the NE builder.
    """
    for svc, sr in SERVICE_RESOURCES.items():
        devices = []
        workflows = []
        # Build KB-based plan: device names, workflows, and attribute placeholders
        all_attrs = {}
        for r in sr["required_resources"]:
            dev = r["type"].replace("/", "-")  # HLR/HSS → HLR-HSS
            devices.append(dev)
            core_type = r["type"].split("/")[0]  # HLR
            wf = WF_MAP.get(core_type, f"{core_type}_Configuration")
            workflows.append(wf)
            for attr in r["attributes"]:
                if attr not in all_attrs:
                    all_attrs[attr] = f"<{attr}>"  # placeholder — resolved at orchestration time

        plan = {"workflows": workflows, "params": all_attrs, "devices": devices}

        # Build characteristics from KB (empty for now — matches any request)
        chars = {}

        # Learn the KB-seeded pattern
        existing = patterns._index.get(svc, [])
        if not existing:
            patterns.learn(svc, chars, plan, all_chars={}, source="kb")
            # Reset confidence to 0.25 for KB seeds
            for pid in patterns._index.get(svc, []):
                pat = patterns._load(pid)
                if pat and pat.source == "kb":
                    pat.confidence = 0.25
                    patterns._save(pat)
                    logger.info("KB seed pattern: %s (svc=%s, %d NEs)",
                                pid, svc, len(devices))


KB_DIR = "/opt/data/telecom-orchestrator/knowledge-base"

# Service-to-KB resource mapping (derived from core ontology §4)
SERVICE_RESOURCES = {
    "mobile": {
        "domain": "Voice / Mobile Core",
        "standards": ["3GPP TS 29.002 (MAP/HLR)", "3GPP TS 23.040 (SMS)", "GSMA IR.92 (VoLTE)",
                      "3GPP TS 23.401 (EPC)", "3GPP TS 29.274 (GTPv2-C)"],
        "required_resources": [
            {"type": "HLR/HSS", "role": "Subscriber registry", "attributes": ["msisdn", "imsi", "subscriber_profile", "roaming_profile"]},
            {"type": "IMS-Core", "role": "VoLTE/VoWiFi call control", "attributes": ["msisdn", "imsi", "volte_enabled", "codec_profile"]},
            {"type": "PCRF/PCF", "role": "Policy & charging rules", "attributes": ["apn", "qos_profile", "charging_rule", "bandwidth_limit"]},
            {"type": "SMSC", "role": "SMS store-and-forward", "attributes": ["msisdn", "routing", "validity_period"]},
            {"type": "MSC/MME", "role": "Mobility management", "attributes": ["msisdn", "imsi", "location_area", "tac"]},
            {"type": "SBC", "role": "Session border control", "attributes": ["sip_domain", "codec_list", "media_handling"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE",
    },
    "l3vpn": {
        "domain": "MPLS L3VPN",
        "standards": ["RFC 4364 (MPLS BGP VPNs)", "RFC 8299 (L3VPN YANG Service Model)", "MEF 6.2 (EVC Services)"],
        "required_resources": [
            {"type": "PE Router", "role": "Provider Edge — VRF termination", "attributes": ["vrf_name", "rd", "rt_import", "rt_export", "bgp_peer"]},
            {"type": "Route Reflector", "role": "BGP route distribution", "attributes": ["cluster_id", "peer_group", "asn"]},
            {"type": "VRF Instance", "role": "Virtual routing table", "attributes": ["vrf_name", "rd", "route_targets", "interfaces"]},
            {"type": "NMS", "role": "Monitoring & assurance", "attributes": ["snmp_community", "syslog_server", "netflow_collector"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE",
    },
    "sdwan": {
        "domain": "SD-WAN Overlay",
        "standards": ["MEF 70 (SD-WAN Service Attributes)", "RFC 7348 (VXLAN)"],
        "required_resources": [
            {"type": "vCPE/uCPE", "role": "Edge device", "attributes": ["transport_links", "encryption", "app_policy", "wan_interfaces"]},
            {"type": "SD-WAN Controller", "role": "Centralized policy & orchestration", "attributes": ["policy_set", "site_list", "template"]},
            {"type": "Orchestrator", "role": "Zero-touch provisioning", "attributes": ["ztp_url", "bootstrap_config", "license_key"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE",
    },
    "broadband": {
        "domain": "Fixed Broadband",
        "standards": ["TR-069 (CWMP)", "TR-383 (Common YANG)"],
        "required_resources": [
            {"type": "OLT", "role": "Optical line terminal", "attributes": ["ont_model", "vlan", "speed_profile", "dba_profile"]},
            {"type": "BNG/BRAS", "role": "Broadband network gateway", "attributes": ["ip_pool", "subscriber_profile", "qos_policy"]},
            {"type": "RADIUS", "role": "AAA server", "attributes": ["nas_identifier", "shared_secret", "auth_method"]},
            {"type": "EMS", "role": "Element management", "attributes": ["snmp_community", "trap_destinations"]},
        ],
        "lifecycle": "DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE",
    },
}

# Shared NE-type → workflow name mapping (derived from KB standards).
# Used by seed_kb_patterns() and _fallback_plan() — single source of truth.
WF_MAP = {
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

# Seed KB-derived patterns on module load (must be after SERVICE_RESOURCES)
seed_kb_patterns()

# ====================================================================
# Lifecycle Notification MCP — TMF641-compliant state change events
# ====================================================================
class LifecycleNotifier:
    """Emits TMF641 ServiceOrderMilestoneEvent and ServiceOrderStateChangeEvent
    notifications as the request progresses through the KB-defined lifecycle.

    Each service type has a lifecycle string in SERVICE_RESOURCES, parsed from KB.
    All events follow the TMF641 v4.1.0 notification schema.

    References:
      - knowledge-base/reference/tmf-notification-schemas.md
      - TMF641_Service_Ordering_Management_API_v4.1.0_swagger.json
    """

    # TMF641 canonical order states
    ORDER_IN_PROGRESS = "inProgress"
    ORDER_COMPLETED = "completed"
    ORDER_FAILED = "failed"

    def __init__(self):
        self._notifications: list[dict] = []

    def parse_lifecycle(self, svc: str) -> list[str]:
        """Extract ordered lifecycle states from KB."""
        sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
        lc = sr.get("lifecycle", "")
        states = [s.strip() for s in lc.split("→")]
        return [s for s in states if s]

    def _base_event(self, event_type: str, order_id: str, correlation_id: str,
                    domain: str = "ServiceFulfillment",
                    priority: str = "normal") -> dict:
        """Build the base TMF notification envelope."""
        now = datetime.utcnow().isoformat() + "Z"
        return {
            "eventId": f"evt-{order_id}-{event_type.split('Event')[0]}",
            "eventTime": now,
            "eventType": event_type,
            "correlationId": correlation_id,
            "domain": domain,
            "priority": priority,
            "timeOcurred": now,
        }

    def emit_milestone(self, state: str, svc: str, order_id: str,
                       correlation_id: str, description: str = "",
                       status: str = "achieved") -> dict:
        """Emit a TMF641 ServiceOrderMilestoneEvent for a lifecycle state.

        Milestones mark in-progress stages without changing the order state.
        The order remains 'inProgress' throughout provisioning.
        """
        now = datetime.utcnow().isoformat() + "Z"
        event = self._base_event("ServiceOrderMilestoneEvent", order_id,
                                 correlation_id)
        event["title"] = f"Milestone: {state}"
        event["description"] = description or f"Service order reached milestone: {state}"
        event["event"] = {
            "serviceOrder": {
                "id": order_id,
                "href": f"/api/tmf641/serviceOrder/{order_id}",
                "state": self.ORDER_IN_PROGRESS,
                "externalId": order_id,
                "category": svc,
                "milestone": [
                    {
                        "id": f"ms-{order_id}-{state}",
                        "name": state,
                        "description": description or f"State transition: {state}",
                        "message": f"Orchestrator reached lifecycle state: {state}",
                        "milestoneDate": now,
                        "status": status,
                    }
                ],
            }
        }
        self._notifications.append(event)
        return event

    def emit_state_change(self, to_state: str, svc: str, order_id: str,
                          correlation_id: str, description: str = "") -> dict:
        """Emit a TMF641 ServiceOrderStateChangeEvent.

        Used for the final ACTIVE state transition — changes order from
        'inProgress' to 'completed'.
        """
        now = datetime.utcnow().isoformat() + "Z"
        event = self._base_event("ServiceOrderStateChangeEvent", order_id,
                                 correlation_id)
        event["title"] = f"Order {to_state}"
        event["description"] = description or f"Service order state changed to: {to_state}"
        event["event"] = {
            "serviceOrder": {
                "id": order_id,
                "href": f"/api/tmf641/serviceOrder/{order_id}",
                "state": to_state,
                "externalId": order_id,
                "category": svc,
                "completionDate": now if to_state == self.ORDER_COMPLETED else None,
            }
        }
        self._notifications.append(event)
        return event

    def flush(self) -> list[dict]:
        """Return all notifications emitted and clear buffer."""
        result = list(self._notifications)
        self._notifications.clear()
        return result

    def build_notification_trace(self, order_id: str, svc: str,
                                  subscriber_id: str, t0: float,
                                  step_fn) -> int:
        """Walk the KB lifecycle and emit milestone + state change notifications.

        All states except the last → ServiceOrderMilestoneEvent (order inProgress)
        Final ACTIVE state → ServiceOrderStateChangeEvent (order completed)

        Returns count of notifications emitted.
        """
        states = self.parse_lifecycle(svc)
        correlation_id = f"corr-{order_id}"
        count = 0

        for i, state in enumerate(states):
            is_final = (i == len(states) - 1)

            if is_final:
                # Final state (ACTIVE) → ServiceOrderStateChangeEvent
                notif = self.emit_state_change(
                    self.ORDER_COMPLETED, svc, order_id, correlation_id,
                    f"Service provisioning complete. Final state: {state}. "
                    f"All network elements configured and verified."
                )
                step_fn("NOTIFY", "done",
                    f"TMF Notification — StateChange → {notif['event']['serviceOrder']['state']}",
                    f"Goal: Emit TMF641 ServiceOrderStateChangeEvent per spec.\\n"
                    f"Input: Final lifecycle state={state}\\n"
                    f"Expected: Transition order from inProgress → completed\\n"
                    f"Actual: Event {notif['eventId']} emitted with state={notif['event']['serviceOrder']['state']}\\n"
                    f"Output: TMF641-compliant notification with correlationId={correlation_id}.",
                    "cyan", "📬")
            else:
                # Intermediate state → ServiceOrderMilestoneEvent
                notif = self.emit_milestone(
                    state, svc, order_id, correlation_id,
                    f"Orchestrator provisioning: {state}. "
                    f"Service type={svc}, subscriber={subscriber_id}."
                )
                step_fn("NOTIFY", "done",
                    f"TMF Notification — Milestone: {state}",
                    f"Goal: Emit TMF641 ServiceOrderMilestoneEvent per spec.\\n"
                    f"Input: Lifecycle state={state} (stage {i+1}/{len(states)})\\n"
                    f"Expected: Record milestone, order remains inProgress\\n"
                    f"Actual: Milestone {notif['eventId']} recorded — order state=inProgress\\n"
                    f"Output: TMF641-compliant milestone notification with correlationId={correlation_id}.",
                    "cyan", "📬")
            count += 1

        return count


lifecycle_notifier = LifecycleNotifier()


def validate_and_repair_cache():
    """Startup cache integrity check — global cross-item scan.

    Runs once on module load.  Per-item corruption is handled at runtime by
    ServiceModelStore.get() and PatternEngine._load().  This startup scan
    handles cross-item issues that need a full index traversal:
      - Duplicate subscribers (two keys for same MSISDN)
      - Stale index entries pointing to deleted patterns
      - Orphan patterns (in cache but not in index)

    Delegates per-model and per-pattern validation to the runtime guards.
    Logs everything for audit.
    """
    repairs = 0

    # ── 1. Scan subscriber models: use runtime guard, track MSISDNs for dedup ──
    msisdn_index = {}  # real MSISDN → [subscriber_ids]
    for key in list(cache):
        if not key.startswith("orch:sub:"):
            continue
        sub_id = key.replace("orch:sub:", "")
        # Delegate per-model validation to runtime guard
        model = service_models.get(sub_id)
        if model is None:
            # Runtime guard deleted it (fully corrupt / unreadable)
            repairs += 1
            continue

        # Track MSISDN for duplicate detection
        msisdn_val = (model.get("characteristics", {}).get("msisdn", ""))
        if msisdn_val and not str(msisdn_val).startswith("default_") and not str(msisdn_val).startswith("<"):
            ver = model.get("version", 0)
            msisdn_index.setdefault(msisdn_val, []).append((key, ver, False))

    # ── 2. Detect and merge duplicate subscribers ──
    for msisdn, entries in msisdn_index.items():
        if len(entries) <= 1:
            continue
        # Sort by version descending
        entries.sort(key=lambda e: -e[1])
        keep_key, keep_ver, _ = entries[0]
        logger.warning(
            "Duplicate subscriber for MSISDN=%s: %d entries found. "
            "Keeping %s (v%d); deleting %d duplicates.",
            msisdn, len(entries), keep_key.replace("orch:sub:", ""),
            keep_ver, len(entries) - 1)
        for dup_key, dup_ver, _ in entries[1:]:
            service_models.delete(dup_key.replace("orch:sub:", ""))
            repairs += 1

    # ── 3. Validate pattern index integrity ──
    idx = cache.get("orch:idx:patterns", {})
    stale_svcs = []
    for svc, pid_list in list(idx.items()):
        valid_pids = []
        for pid in pid_list:
            # Delegate per-pattern validation to runtime guard
            pat = patterns._load(pid)
            if pat is not None:
                valid_pids.append(pid)
            else:
                repairs += 1
        if valid_pids:
            idx[svc] = valid_pids
        else:
            stale_svcs.append(svc)
    for svc in stale_svcs:
        del idx[svc]
    cache.set("orch:idx:patterns", idx)

    # ── 4. Scan for orphan patterns (in cache but not in index) ──
    indexed_pids = {pid for pid_list in idx.values() for pid in pid_list}
    for key in list(cache):
        if key.startswith("orch:pat:") and key != "orch:idx:patterns":
            pid = key.replace("orch:pat:", "")
            if pid not in indexed_pids:
                # Delegate validation to runtime guard before indexing
                pat = patterns._load(pid)
                if pat is not None and hasattr(pat, 'service_type'):
                    logger.warning("Orphan pattern %s (not in index) — re-indexing", pid)
                    patterns._index_pattern(pat)
                    repairs += 1
                # else: _load already deleted it

    if repairs:
        logger.info("Cache integrity: %d cross-item issues repaired", repairs)
    else:
        logger.info("Cache integrity: OK — no cross-item issues found")


validate_and_repair_cache()


def load_kb_context(svc: str) -> str:
    """Load domain knowledge from KB files relevant to the service type."""
    context_parts = []

    # Read core ontology — extract service taxonomy section
    onto_path = f"{KB_DIR}/ontologies/core-ontology.md"
    try:
        with open(onto_path) as f:
            onto = f.read()
        # Extract relevant service section
        for section in onto.split("## "):
            if "Service Taxonomy" in section or "Resource Taxonomy" in section:
                context_parts.append(section[:1500])
    except Exception:
        pass

    # Read standards reference
    std_path = f"{KB_DIR}/reference/standards-index.md"
    try:
        with open(std_path) as f:
            standards = f.read()
        # Extract mobile-related standards
        relevant = []
        for line in standards.split("\n"):
            low = line.lower()
            if any(w in low for w in [svc, "mobile", "voice", "hlr", "ims", "pcrf", "volte", "3gpp", "msisdn"]):
                relevant.append(line)
        if relevant:
            context_parts.append("Relevant Standards:\n" + "\n".join(relevant[:20]))
    except Exception:
        context_parts.append(KB_DOCS.get(svc, "Generic provisioning standards"))

    # Add structured resource knowledge
    sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
    context_parts.append(f"\nService Domain: {sr['domain']}")
    context_parts.append(f"Required Network Elements ({len(sr['required_resources'])}):")
    for r in sr['required_resources']:
        context_parts.append(f"  - {r['type']}: {r['role']} (attrs: {', '.join(r['attributes'])})")
    context_parts.append(f"Lifecycle: {sr['lifecycle']}")

    return "\n".join(context_parts)

# ====================================================================
# Deepseek Client (via hermes CLI)
# ====================================================================
def call_deepseek(prompt: str, timeout: int = 120) -> str:
    """Call Deepseek via hermes CLI. Returns the model's text response."""
    env = {}
    # Read API key from hermes .env
    env_path = "/opt/data/.env"
    if shutil.which("hermes"):
        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", prompt, "--quiet",
                 "-m", "deepseek-v4-pro", "--provider", "deepseek"],
                capture_output=True, text=True, timeout=timeout,
                cwd="/opt/data",
                env={**__import__("os").environ, "HERMES_HOME": "/opt/data"},
            )
            # Strip session_id line from output
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


def detect_operation(text: str, is_json: bool = False) -> str:
    """Detect the operation from the request (activate/modify/delete/suspend/resume)."""
    t = text.lower()
    if is_json:
        try:
            data = json.loads(t)
            # TMF640: check action field
            action = data.get("action", "")
            if action:
                return action.lower()
        except Exception:
            pass
    # Unstructured / keyword-based detection
    if any(w in t for w in ["delete", "remove", "deactivate", "cancel"]):
        return "delete"
    if any(w in t for w in ["modify", "update", "change", "upgrade", "downgrade"]):
        return "modify"
    if any(w in t for w in ["suspend", "pause"]):
        return "suspend"
    if any(w in t for w in ["resume", "reactivate", "restore"]):
        return "resume"
    return "activate"  # default

# ====================================================================
# Pipeline Engine
# ====================================================================
def start_pipeline(prompt: str) -> ProcessResponse:
    """Run stages DETECT → MASK → CACHE synchronously, return early trace.
    Background thread calls finish_pipeline() for LLM → VERIFY."""
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
                 "Goal: Validate and classify the incoming request format.\n"
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
    operation = detect_operation(prompt, is_json)  # detect intent operation
    # Build characteristics dict for pattern matching (exclude instance identifiers)
    chars = {}
    all_chars = {}  # includes instance attrs for full provisioning
    if is_json:
        try:
            data = json.loads(prompt)
            for c in data.get("characteristic", []):
                name = c.get("name", c.get("key", ""))
                val = str(c.get("value", ""))
                all_chars[name] = val
                if name.lower() in patterns.INSTANCE_ATTRS:
                    continue
                chars[name] = val
        except: pass
    else:
        # Unstructured: use masked text hash so different intents get different keys
        chars["text_hash"] = hashlib.sha256(masked_text.encode()).hexdigest()[:16]
        # Populate all_chars from token_map so subscriber identity can be resolved
        # (critical: without this, every unstructured request gets a fresh hash ID)
        for tok, real in token_map.items():
            if tok.startswith("VAR_MSISDN_"):
                all_chars["msisdn"] = real
                break  # first MSISDN is the subscriber anchor
            elif tok.startswith("VAR_IP_"):
                all_chars[f"ip_{tok}"] = real

    # --- Extract subscriber identity and load previous service model ---
    subscriber_id = extract_subscriber_id(prompt, is_json, all_chars)
    previous_model = service_models.get(subscriber_id)

    # === CACHE ENGINE SELECTION ===
    engine = get_cache_engine()
    pattern_match = None  # structured match info for UI

    if engine == "dsl":
        # ── DSL Engine: deterministic YAML template matching ──
        # Ensure DSL definitions are loaded (lazy on first use)
        dsl_engine.load()
        plan = dsl_engine.lookup(svc, all_chars, operation=operation)
        pattern_match = dsl_engine.to_pattern_match(svc)

        if plan and plan.get("devices"):
            # Cascade all_chars into the DSL plan params (fill real values)
            cascaded = 0
            pp = plan.get("params", {})
            for k, v in all_chars.items():
                sv = str(v)
                if not sv.startswith("default_") and not sv.startswith("<"):
                    pp[k] = v
                    cascaded += 1
            plan["params"] = pp

            dsl_domain = pattern_match.get("patternLabel", svc)
            dsl_prov = pattern_match.get("dslProvenance", {})
            dsl_template = plan.get("_dsl_template", {})
            populated_nes = dsl_template.get("network_elements", [])
            included_nes = [n for n in populated_nes if n["decision"] == "INCLUDE"]
            skipped_nes = [n for n in populated_nes if n["decision"] == "SKIP"]

            trace_detail = (
                f"Goal: Populate Service DSL template with request characteristics.\\n"
                f"Input: service_type={svc}, operation={operation}, {len(all_chars)} characteristics\\n"
                f"Expected: Resolve ~expressions in Service DSL → Intent DSL → NE references\\n"
                f"Actual: DSL template populated — {dsl_prov.get('systemCode', svc)} {dsl_prov.get('templateVersion', '?')}\\n"
                f"  Schema: {dsl_prov.get('schemaStatus', '?')}\\n"
                f"  {len(included_nes)} NEs included: {', '.join(n['name'] for n in included_nes)}\\n"
            )
            if skipped_nes:
                ne_skips = "\\n".join(
                    f"    ✗ {n['name']}: {n['skip_reason']}"
                    for n in skipped_nes
                )
                trace_detail += (
                    f"  {len(skipped_nes)} NEs skipped (_if_ conditions not met):\\n"
                    f"{ne_skips}\\n"
                )
            trace_detail += (
                f"  {len(plan['workflows'])} workflows\\n"
                f"  {len(plan['params'])} params (incl. {cascaded} cascaded from request)\\n"
                f"  Templates: authoritative YAML DSL (score=1.0)\\n"
                f"Output: Populated DSL template with {len(plan['devices'])} network elements.\\n"
                f"⏱ 0ms LLM latency — DSL is the plan."
            )
            step("CACHE", "done", f"DSL Cache — {dsl_domain} ✓",
                 trace_detail, "green", "📋")
            llm_used = False
            pattern_hit = None
        else:
            # DSL exists but produced empty plan — fall through to LLM
            step("CACHE", "done", "DSL Cache — MISS (Empty Plan)",
                 f"Goal: Build plan from DSL templates.\\n"
                 f"Actual: DSL returned no devices — falling back to LLM.",
                 "amber", "📡")
            plan = None
            llm_used = True
            pattern_hit = None

    else:
        # ── Pattern Engine: RDF-based Jaccard matching (default) ──
        matched = patterns.lookup(svc, chars)
        if matched:
            patterns.reinforce(matched)
            plan = {"workflows": [r["workflow"] for r in matched.resources],
                    "params": {k: v for r in matched.resources for k, v in r["attributes"].items()},
                    "devices": [r["name"] for r in matched.resources]}

            # Immediately cascade request characteristics into the cached plan.
            if all_chars:
                cascaded = 0
                pp = plan.get("params", {})
                for k, v in all_chars.items():
                    sv = str(v)
                    if not sv.startswith("default_") and not sv.startswith("<"):
                        pp[k] = v
                        cascaded += 1
                if cascaded:
                    plan["params"] = pp
                    step("MERGE", "done", f"Sync-Phase Merge — {cascaded} Request Chars Cascaded",
                         f"Goal: Cascade request characteristics into cached plan before background dispatch.\\n"
                         f"Actual: {cascaded} characteristics from request overlaid onto {len(matched.resources)}-resource plan.\\n"
                         f"Output: Plan params now reflect current request, not stale cached values.",
                         "violet", "🔄")

            # Build detailed match comparison
            req_keys = {k for k in chars if k.lower() not in patterns.INSTANCE_ATTRS}
            pat_keys = set(matched.characteristics.keys())
            matched_keys = {k for k in req_keys & pat_keys if str(chars.get(k,"")) == str(matched.characteristics.get(k,""))}
            mismatched_keys = (req_keys & pat_keys) - matched_keys
            extra_keys = req_keys - pat_keys
            pattern_match = {
                "result": "HIT",
                "patternId": matched.id,
                "patternLabel": matched.label,
                "confidence": round(matched.confidence, 2),
                "useCount": matched.use_count,
                "triplesCount": len(matched.triples),
                "resourcesCount": len(matched.resources),
                "compareLogic": "Jaccard similarity on service-defining characteristics",
                "requestChars": {k: str(v) for k, v in chars.items() if k.lower() not in patterns.INSTANCE_ATTRS},
                "patternChars": {k: str(v) for k, v in matched.characteristics.items()},
                "matchedKeys": sorted(matched_keys),
                "mismatchedKeys": sorted(mismatched_keys),
                "extraKeys": sorted(extra_keys),
                "excludedInstanceAttrs": sorted(k for k in chars if k.lower() in patterns.INSTANCE_ATTRS),
                "score": round(len(matched_keys) / max(len(req_keys | pat_keys), 1), 2),
            }
            compare_rows = []
            for k in sorted(req_keys | pat_keys):
                req_v = chars.get(k, "—")
                pat_v = matched.characteristics.get(k, "—")
                status = "✓" if str(req_v) == str(pat_v) else "✗" if k in req_keys and k in pat_keys else "?"
                compare_rows.append(f"  {status} {k}: request={req_v}  |  pattern={pat_v}")
            step("CACHE", "done", f"Pattern Match — {matched.id} ✓",
                 f"Goal: Query the RDF pattern store for a matching orchestration pattern.\\n"
                 f"Input: service_type={svc}, comparing {len(req_keys)} service-defining characteristics\\n"
                 f"Expected: Jaccard match against {len(patterns._index.get(svc,[]))} known {svc} patterns\\n"
                 f"Actual: Pattern HIT — {matched.label}\\n"
                 f"  Confidence: {matched.confidence:.0%} ({matched.use_count} uses)\\n"
                 f"  Score: {pattern_match['score']:.0%} ({len(matched_keys)}/{len(req_keys|pat_keys)} keys match)\\n"
                 + "\\n".join(compare_rows) + "\\n\\n"
                 + (f"  Instance attrs excluded: {', '.join(pattern_match['excludedInstanceAttrs'])}\\n" if pattern_match['excludedInstanceAttrs'] else "")
                 + f"Output: Pre-validated plan with {len(matched.resources)} network elements.\\n"
                 f"⏱ 0ms LLM latency.",
                 "green", "⚡")
            llm_used = False
            pattern_hit = matched
        else:
            all_pats = patterns.list_all()
            same_svc = [p for p in all_pats if p["service_type"] == svc]
            req_keys = {k for k in chars if k.lower() not in patterns.INSTANCE_ATTRS}
            pattern_match = {
                "result": "MISS",
                "patternsInStore": len(all_pats),
                "patternsForService": len(same_svc),
                "requestChars": {k: str(v) for k, v in chars.items() if k.lower() not in patterns.INSTANCE_ATTRS},
                "excludedInstanceAttrs": sorted(k for k in chars if k.lower() in patterns.INSTANCE_ATTRS),
                "compareLogic": "Jaccard similarity on service-defining characteristics",
            }
            step("CACHE", "done", "Pattern Store — MISS",
                 f"Goal: Query the RDF pattern store for a matching orchestration pattern.\\n"
                 f"Input: service_type={svc}, {len(req_keys)} service-defining characteristics\\n"
                 f"Request chars: {json.dumps(pattern_match['requestChars'])}\\n"
                 f"Expected: Find matching pattern via Jaccard similarity\\n"
                 f"Actual: No match — {len(same_svc)} patterns for '{svc}', {len(all_pats)} total in store\\n"
                 + (f"  Instance attrs excluded: {', '.join(pattern_match['excludedInstanceAttrs'])}\\n" if pattern_match['excludedInstanceAttrs'] else "")
                 + f"Output: Flag llm_used=True → Deepseek will reason from KB, then pattern will be learned.",
                 "amber", "📡")
            plan = None
            llm_used = True
            pattern_hit = None

    # --- STAGE 3 onward: dispatch to background ---
    docs = KB_DOCS.get(svc, "Generic provisioning standards")
    kb_context = load_kb_context(svc)
    step("LLM", "done", "Pipeline Dispatched — Background Processing",
         f"Goal: Continue orchestration in background thread.\n"
         f"Input: {'Cached plan available' if not llm_used else 'Need LLM reasoning'}\n"
         f"Expected: Background thread completes LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY\n"
         f"Actual: Background processing started. Frontend will poll for results.",
         "green", "⏳")

    result = ProcessResponse(order_id=order_id, format=fmt, status="processing",
                             trace=trace, total_ms=int((time.time()-t0)*1000),
                             started_at=datetime.utcnow().isoformat())

    # Extract state needed by background thread
    bg_state = {
        "order_id": order_id, "fmt": fmt, "svc": svc, "docs": docs,
        "kb_context": kb_context,
        "masked_text": masked_text, "token_map": token_map, "n_tokens": n_tokens,
        "llm_used": llm_used, "chars": chars, "all_chars": all_chars, "pattern_hit": pattern_hit,
        "pattern_match": pattern_match,
        "plan": plan, "t0": t0,
        "subscriber_id": subscriber_id, "previous_model": previous_model,
        "operation": operation,
    }
    with jobs_lock:
        jobs[order_id] = result
    executor.submit(_run_background, bg_state)
    return result


def _run_background(state: dict):
    """Complete the pipeline in a background thread — LLM → HYDRATE → VALIDATE → EXECUTE → VERIFY."""
    order_id = state["order_id"]
    try:
        _run_background_inner(state)
    except Exception:
        logger.exception("Background pipeline crashed for %s", order_id)
        with jobs_lock:
            if order_id in jobs:
                jobs[order_id].status = "error"
                jobs[order_id].trace.append(TraceStep(
                    stage="ERROR", status="error",
                    title="Background Pipeline Crashed",
                    detail=f"Unhandled exception in background thread. Check server logs.",
                    color="red", icon="💥",
                    elapsed_ms=int((time.time() - state["t0"]) * 1000)))


def _run_background_inner(state: dict):
    order_id = state["order_id"]
    svc = state["svc"]
    docs = state["docs"]
    kb_context = state["kb_context"]
    chars = state.get("chars", {})
    all_chars = state.get("all_chars", {})  # includes msisdn/imsi for full provisioning
    subscriber_id = state.get("subscriber_id", "unknown")
    previous_model = state.get("previous_model")
    pattern_hit = state.get("pattern_hit")
    pattern_match = state.get("pattern_match")
    operation = state.get("operation", "activate")
    masked_text = state["masked_text"]
    token_map = state["token_map"]
    n_tokens = state["n_tokens"]
    cache_key = state.get("cache_key")  # optional — not always in bg_state
    llm_used = state["llm_used"]
    plan = state["plan"]
    t0 = state["t0"]
    fmt = state["fmt"]

    def step(stage, status, title, detail, color, icon):
        with jobs_lock:
            if order_id in jobs:
                jobs[order_id].trace.append(TraceStep(
                    stage=stage, status=status, title=title, detail=detail,
                    color=color, icon=icon, elapsed_ms=int((time.time()-t0)*1000)))

    # --- STAGE 3: RAG ---
    sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
    ne_count = len(sr['required_resources'])
    ne_list = ", ".join(r['type'] for r in sr['required_resources'])
    step("RAG", "done", "Knowledge Base RAG — Domain Reasoning",
         f"Goal: Load domain knowledge from local KB files to determine required network elements.\\n"
         f"Input: Detected service type = '{svc}', mapped to domain '{sr['domain']}'\\n"
         f"Expected: Query core ontology + standards reference → determine required resources\\n"
         f"Actual: KB resolver identified {ne_count} required network elements from ontology:\\n"
         + "\\n".join(f"  • {r['type']} — {r['role']}" for r in sr['required_resources']) + "\\n\\n"
         f"Standards: {', '.join(sr['standards'][:3])}\\n"
         f"Lifecycle: {sr['lifecycle']}\\n"
         f"Output: Structured domain context injected into reasoning pipeline.",
         "blue", "📚")

    # --- STAGE 4: LLM ---
    if llm_used:
        llm_prompt = f"""You are a telecom orchestration engine. Generate an orchestration plan for this service request.

Domain Knowledge (from KB):
{kb_context[:4000]}

Request (SENSITIVE DATA MASKED):
{masked_text[:2000]}

Return ONLY valid JSON with this structure:
{{"workflows": ["..."], "params": {{...}}, "devices": ["..."]}}

The workflows, params, and devices MUST correspond to the network elements identified in the domain knowledge above. Use the masked tokens (VAR_*) as-is — do not invent real values."""

        step("LLM", "running", "Deepseek v4 — Reasoning & Plan Generation",
             f"Goal: Generate an orchestration plan using cloud AI reasoning on MASKED data.\n"
             f"Input: Masked request text + KB standards context\n"
             f"Expected: Deepseek returns structured JSON with workflows, params, and target devices\n"
             f"Calling Deepseek API (via hermes CLI) — this takes 30-60 seconds...",
             "blue", "🧠")
        logger.info("Calling Deepseek for %s (%d chars)", svc, len(llm_prompt))
        llm_response = call_deepseek(llm_prompt, timeout=90)

        if llm_response:
            try:
                plan = json.loads(llm_response)
            except json.JSONDecodeError:
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if json_match:
                    try:
                        plan = json.loads(json_match.group(0))
                    except:
                        plan = _fallback_plan(svc)
                else:
                    plan = _fallback_plan(svc)

            step("LLM", "done", "Deepseek v4 — Plan Generated ✓",
                 f"Goal: Generate an orchestration plan using cloud AI reasoning on MASKED data.\n"
                 f"Input: Masked request + KB standards → Deepseek v4 API (via hermes CLI)\n"
                 f"Expected: Valid JSON with workflows[], params{{}}, devices[]\n"
                 f"Actual: Deepseek returned {len(llm_response)} chars of structured JSON\n"
                 f"Output:\n  • {len(plan.get('workflows',[]))} workflows: {', '.join(plan.get('workflows',[])[:4])}\n"
                 f"  • {len(plan.get('params',{}))} configuration parameters\n"
                 f"  • Target devices: {', '.join(plan.get('devices',[])[:4])}",
                 "blue", "🧠")
        else:
            plan = _fallback_plan(svc)
            step("LLM", "done", "Deepseek v4 — Fallback Plan Used",
                 f"Goal: Generate orchestration plan via cloud AI.\n"
                 f"Input: Masked request + KB standards\n"
                 f"Expected: Deepseek returns structured JSON plan\n"
                 f"Actual: Deepseek did not respond.\n"
                 f"Output: Using pre-built {svc} template plan.",
                 "blue", "🧠")
    else:
        step("LLM", "done", "Deepseek v4 — Skipped (Cache Hit)",
             f"Goal: Generate orchestration plan (only if needed).\n"
             f"Input: Cache status = HIT\n"
             f"Expected: Skip LLM call entirely\n"
             f"Actual: LLM bypassed — cached plan retrieved.\n"
             f"Output: Pre-validated plan with {len(plan.get('workflows',[])) if plan else 0} workflows.",
             "green", "🧠")

    # --- Flatten nested params (LLMs often nest by workflow name) ---
    plan = flatten_plan_params(plan)

    # --- STAGE 5: HYDRATE ---
    if token_map:
        ps = json.dumps(plan)
        for tok, real in token_map.items():
            ps = ps.replace(tok, real)
        plan = json.loads(ps)
        step("HYDRATE", "done", "Local Parameter Hydration",
             f"Goal: Restore real infrastructure identifiers.\\n"
             f"Input: Plan with VAR_* tokens + local mapping ({n_tokens} entries)\\n"
             f"Expected: All tokens resolved to original values\\n"
             f"Actual: {n_tokens} tokens resolved.\\n"
             f"Output: Fully hydrated plan ready for execution.",
             "violet", "💧")
    else:
        step("HYDRATE", "done", "Local Parameter Hydration",
             f"Goal: Restore real identifiers if masked.\\n"
             f"Actual: No tokens to resolve.",
             "violet", "💧")

    # --- Populate all_chars from plan params for unstructured text ---
    # The sync phase only extracts msisdn from token_map.  The LLM has now
    # parsed the full request — harvest real characteristics so MERGE, DIFF,
    # and model storage have complete context for change detection.
    # IMPORTANT: skip default_* values — they are placeholders, not real data.
    if fmt == "unstructured" and plan and isinstance(plan.get("params"), dict):
        for k, v in plan["params"].items():
            sv = str(v)
            if k not in all_chars and not sv.startswith("default_"):
                all_chars[k] = v

    # --- MERGE: cascade request characteristics into cached/LLM plan ---
    # Two modes:
    #   1. With previous_model: cascade CHANGED values + fill gaps from prev model
    #   2. Without previous_model (first provisioning): cascade ALL request chars
    #      into the cached plan so it reflects the actual request, not stale
    #      values from a different subscriber's learned pattern.
    # --- ACQUIRE SUBSCRIBER LOCK ---
    # Prevents concurrent modifications to the same subscriber model.
    # If another worker is modifying this subscriber, we wait up to 5s.
    plan_params = plan.get("params", {})
    merged_count = 0
    filled_count = 0
    lock_held = False

    with subscriber_lock.acquire(subscriber_id, order_id) as lock_acquired:
        if not lock_acquired:
            step("LOCK", "error",
                 f"Subscriber Lock — TIMEOUT on {subscriber_id}",
                 f"Goal: Acquire exclusive lock for subscriber model modification.\\n"
                 f"Input: subscriber_id={subscriber_id}\\n"
                 f"Expected: Lock acquired within {SubscriberLock.MAX_RETRIES * SubscriberLock.RETRY_DELAY:.0f}s\\n"
                 f"Actual: Lock held by another worker after full retry budget.\\n"
                 f"Output: Aborting — subscriber is being modified concurrently.",
                 "red", "🔒")
            with jobs_lock:
                if order_id in jobs:
                    jobs[order_id].status = "blocked"
                    jobs[order_id].total_ms = int((time.time()-t0)*1000)
            return

        lock_held = True
        step("LOCK", "done",
             f"Subscriber Lock — Acquired ✓",
             f"Goal: Acquire exclusive lock on subscriber {subscriber_id}.\\n"
             f"Input: lock:sub:{subscriber_id}\\n"
             f"Expected: Lock free or available within retry budget\\n"
             f"Actual: Lock acquired — safe to modify model.\\n"
             f"Output: MERGE → VERIFY → STORE critical section protected.",
             "violet", "🔒")

        # Always cascade request characteristics into plan params
        if all_chars:
            for k, v in all_chars.items():
                sv = str(v)
                if not sv.startswith("default_") and not sv.startswith("<"):
                    plan_params[k] = v
                    merged_count += 1
        else:
            step("MERGE", "done", "Merge Skipped — No Request Chars",
                 f"Goal: Cascade request characteristics into plan.\\n"
                 f"Actual: all_chars is empty — nothing to cascade.\\n"
                 f"Plan params has {len(plan_params)} keys: {sorted(plan_params.keys())[:10]}",
                 "violet", "⏭️")

        # If we have a previous model, also cascade changed values and fill gaps
        if previous_model:
            prev_chars = previous_model.get("characteristics", {})
            for k, prev_v in prev_chars.items():
                if k not in all_chars and k not in plan_params:
                    sv = str(prev_v)
                    if not sv.startswith("default_"):
                        plan_params[k] = prev_v
                        filled_count += 1

        if merged_count or filled_count:
            plan["params"] = plan_params
            detail = f"Goal: Cascade request characteristics into plan.\\n"
            detail += f"Input: {merged_count} from request, {filled_count} from previous model"
            if previous_model:
                detail += f" v{previous_model.get('version','?')}"
            detail += f"\\nOutput: Plan params now complete — {len(plan_params)} attributes total."
            step("MERGE", "done", "Characteristic Merge — Plan Updated",
                 detail, "violet", "🔄")

        # --- STAGE 6: WRITE-THROUGH ---
        learned = None
        if llm_used:
            learned = patterns.learn(svc, chars, plan, all_chars=all_chars)
            step("CACHE", "done", "Pattern Learning — RDF Triples Written",
                 f"Goal: Persist new pattern as RDF graph for future matches.\\n"
                 f"Actual: Pattern {learned.id} learned.\\n"
                 f"Output: {len(learned.triples)} triples, {len(learned.resources)} resources, confidence={learned.confidence:.0%}.",
                 "green", "💾")
        else:
            step("CACHE", "done", "Pattern Learning",
                 "Goal: Persist new pattern if just learned.\\n"
                 "Actual: Pattern already exists — confidence reinforced by cache hit.",
                 "green", "💾")

        # --- STAGE 7: VALIDATE ---
        check_text = (json.dumps(plan) + " " + masked_text).lower()
        blocked = [kw for kw in BLOCKED_KEYWORDS if kw in check_text]
        if blocked:
            step("VALIDATE", "blocked", "Security Gateway — BLOCKED 🚫",
                 f"Goal: Prevent destructive commands from reaching devices.\\n"
                 f"Actual: BLOCKED — {', '.join(blocked)} detected.\\n"
                 f"Output: Transaction ABORTED. No devices touched.",
                 "red", "🚫")
            with jobs_lock:
                if order_id in jobs:
                    jobs[order_id].status = "blocked"
                    jobs[order_id].total_ms = int((time.time()-t0)*1000)
            return
        step("VALIDATE", "done", "Security Gateway — PASSED ✓",
             f"Goal: Validate plan against security guardrails.\\n"
             f"Actual: All checks PASSED.\\n"
             f"Output: Plan cleared for execution.",
             "green", "🔒")

        # --- STAGE 8: EXECUTE ---
        workflows = plan.get("workflows", [])
        devices = plan.get("devices", [f"DEV-{i}" for i in range(len(workflows))])
        step("EXECUTE", "done", "MCP Execution — Workflows Dispatched",
             f"Goal: Deploy validated plan to infrastructure.\\n"
             f"Actual: {len(workflows)} workflows completed.\\n"
             f"Output: Devices configured.",
             "amber", "⚙️")

        # --- STAGE 9: VERIFY ---
        svc_id = f"SVC-{uuid.uuid4().hex[:6].upper()}"

        # Build network element details from KB resource definitions + plan
        params = plan.get("params", {})
        sr2 = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
        kb_resources = {r["type"]: r for r in sr2["required_resources"]}
        # Build lookup of previous model NE attributes for gap-filling.
        prev_ne_attrs = {}
        if previous_model:
            for ne in previous_model.get("network_elements", []):
                name = ne["name"]
                prev_ne_attrs[name] = ne.get("attributes", {})
                canonical = name.split("/")[0]
                if canonical != name:
                    prev_ne_attrs[canonical] = ne.get("attributes", {})
        network_elements = []
        for i, dev in enumerate(devices):
            wf = workflows[i] if i < len(workflows) else "Configuration"
            kb_res = None
            for kb_type, kb_def in kb_resources.items():
                if any(p in dev.lower() for p in kb_type.lower().replace("/"," ").split()):
                    kb_res = kb_def
                    break
            attrs = {}
            if kb_res:
                for attr in kb_res.get("attributes", []):
                    if attr in params:
                        attrs[attr] = str(params[attr])
                    elif attr in all_chars:
                        attrs[attr] = str(all_chars[attr])
                    elif attr in chars:
                        attrs[attr] = str(chars[attr])
                    else:
                        prev_attrs = prev_ne_attrs.get(dev)
                        if prev_attrs is None:
                            canonical = dev.split("/")[0]
                            prev_attrs = prev_ne_attrs.get(canonical, {})
                        prev_val = (prev_attrs or {}).get(attr)
                        if prev_val is not None and not str(prev_val).startswith("default_"):
                            attrs[attr] = str(prev_val)
                        else:
                            attrs[attr] = f"default_{attr}"
                attrs["status"] = "Configured"
            else:
                for k, v in params.items():
                    attrs[k] = str(v) if not isinstance(v, list) else ", ".join(str(x) for x in v)
                attrs["status"] = "Configured"
            network_elements.append({
                "name": dev,
                "type": kb_res.get("type", dev) if kb_res else dev,
                "workflow": wf,
                "role": kb_res.get("role", "Network function") if kb_res else "Network function",
                "attributes": attrs,
            })

        # --- Service Model: compute diff, save, cross-validate ---
        subscriber_diff = service_models.compute_diff(previous_model, all_chars, network_elements)
        new_model = service_models.build_model(
            subscriber_id, svc, all_chars, network_elements,
            version=previous_model.get("version", 0) if previous_model else 0)
        service_models.save(subscriber_id, new_model)

        # --- KB-Driven Lifecycle Notifications ---
        notif_count = lifecycle_notifier.build_notification_trace(
            order_id, svc, subscriber_id, t0, step)

        # Collect all notifications
        notifications = lifecycle_notifier.flush()

        final_state = {"serviceId": svc_id, "state": "ACTIVE",
                       "workflowsExecuted": len(workflows), "resourcesProvisioned": len(params),
                       "networkElements": network_elements,
                       "patternId": learned.id if learned else (pattern_hit.id if pattern_hit else None),
                       "patternConfidence": round(learned.confidence if learned else (pattern_hit.confidence if pattern_hit else 0), 2),
                       "llmUsed": llm_used,
                       "patternMatch": pattern_match,
                       "subscriberId": subscriber_id,
                       "subscriberDiff": subscriber_diff,
                       "notificationCount": notif_count,
                       "notifications": notifications,
                       "dslTrace": plan.get("_dsl_template", {}).get("network_elements", []) if plan else [],
                       "dslPlan": {"workflows": plan.get("workflows", []), "devices": plan.get("devices", []), "params": plan.get("params", {})} if plan else {},
                       "dslOperation": operation,
                       "dslTemplate": plan.get("_dsl_template", {}) if plan else {}}
        step("VERIFY", "done", "Verification & Pattern Learning",
             f"Goal: Confirm service is active, persist model, cross-validate.\\n"
             f"Actual: Service {svc_id} ACTIVE — {len(network_elements)} network elements configured.\\n"
             + (f"Previous model: v{previous_model.get('version','?')} — {len(subscriber_diff.get('changedAttributes',{}))} characteristic changes, "
                f"{sum(1 for d in subscriber_diff.get('networkElementDiffs',{}).values() if d)} NE diffs.\\n" if previous_model else
                f"First provisioning — new service model v1 saved.\\n")
             + f"Notifications: {notif_count} lifecycle state transitions emitted.\\n"
             + f"Output: Model persisted. Lock released. Pipeline complete.",
             "green", "✅")

    # --- Lock auto-released here by context manager ---

    total_ms = int((time.time() - t0) * 1000)
    with jobs_lock:
        if order_id in jobs:
            jobs[order_id].status = "completed"
            jobs[order_id].total_ms = total_ms
            jobs[order_id].final_state = final_state


def _fallback_plan(svc: str) -> dict:
    """Generate plan from KB-derived SERVICE_RESOURCES when Deepseek unavailable.
    Uses WF_MAP for workflow names and <attr> placeholders — no hardcoded values."""
    sr = SERVICE_RESOURCES.get(svc, SERVICE_RESOURCES["mobile"])
    resources = sr["required_resources"]
    devices = [r["type"].replace("/", "-") for r in resources]
    workflows = [WF_MAP.get(d.replace("-HSS","").replace("-PCF","").replace("-MME",""),
                           f"{d}_Config") for d in devices]
    params = {}
    for r in resources:
        for attr in r["attributes"]:
            params[attr] = f"<{attr}>"  # placeholder — resolved at orchestration time
    return {"workflows": workflows, "params": params, "devices": devices}

# ====================================================================
# Routes
# ====================================================================
@app.post("/api/process", response_model=ProcessResponse)
async def process(request: ProcessRequest):
    return start_pipeline(request.prompt)


@app.get("/api/process/{order_id}", response_model=ProcessResponse)
async def get_process(order_id: str):
    """Poll for pipeline result. Returns partial trace while processing."""
    with jobs_lock:
        job = jobs.get(order_id)
    if job is None:
        return JSONResponse({"error": "order not found"}, status_code=404)
    return job

@app.get("/api/patterns")
async def list_patterns():
    """List all learned patterns with confidence and metadata."""
    return {"patterns": patterns.list_all()}

@app.get("/api/patterns/{pattern_id}")
async def get_pattern(pattern_id: str):
    """Get full pattern details including RDF triples."""
    pat = patterns.get(pattern_id)
    if pat is None:
        return JSONResponse({"error": "pattern not found"}, status_code=404)
    return pat

@app.post("/api/patterns/teach")
async def teach_pattern(request: dict):
    """Teach the engine a new pattern via RDF triples. High confidence."""
    triples = request.get("triples", [])
    if not triples:
        return JSONResponse({"error": "triples required"}, status_code=400)
    node = patterns.teach(triples)
    return {"status": "learned", "pattern": node.to_dict()}

@app.get("/api/samples")
async def get_samples():
    return {"samples": [
        {"label": "TMF640 — Activate Mobile Voice (Gold)",
         "text": '{"serviceId":"MSISDN-447700123456","action":"activate","characteristic":[{"name":"customerSegment","value":"retail"},{"name":"slaTier","value":"gold"},{"name":"productId","value":"mobile-voice"},{"name":"msisdn","value":"447700123456"},{"name":"imsi","value":"234151234567890"},{"name":"subscriber_profile","value":"Gold_VoLTE_IntlRoam"},{"name":"roaming_profile","value":"WorldZone1"},{"name":"volte_enabled","value":"true"},{"name":"codec_profile","value":"EVS_AMR-WB"},{"name":"apn","value":"ims.gold.mnc015.mcc234.gprs"},{"name":"qos_profile","value":"QCI-1_VoLTE"},{"name":"charging_rule","value":"Gold_Postpaid_VoLTE"},{"name":"bandwidth_limit","value":"unlimited"},{"name":"routing","value":"SMSC-Primary"},{"name":"validity_period","value":"72h"},{"name":"location_area","value":"LAC-0x4A2B"},{"name":"tac","value":"0x8C3D"},{"name":"sip_domain","value":"ims.mnc015.mcc234.3gppnetwork.org"},{"name":"codec_list","value":"EVS,AMR-WB,AMR-NB"},{"name":"media_handling","value":"rtp-proxy"}]}'},
        {"label": "TMF640 — Activate Mobile Data (Platinum)",
         "text": '{"serviceId":"MSISDN-447700654321","action":"activate","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"mobile-data"},{"name":"msisdn","value":"447700654321"},{"name":"imsi","value":"234159876543210"},{"name":"subscriber_profile","value":"Plat_5GSA_eMBB"},{"name":"roaming_profile","value":"Global"},{"name":"volte_enabled","value":"false"},{"name":"codec_profile","value":"AMR-WB"},{"name":"apn","value":"data.plat.mnc015.mcc234.gprs"},{"name":"qos_profile","value":"QCI-6_5QI-6"},{"name":"charging_rule","value":"Plat_Postpaid_Data_5G"},{"name":"bandwidth_limit","value":"10Gbps"},{"name":"routing","value":"SMSC-Secondary"},{"name":"validity_period","value":"168h"},{"name":"location_area","value":"LAC-0xB7E1"},{"name":"tac","value":"0x3F2A"},{"name":"sip_domain","value":"volte.mnc015.mcc234.3gppnetwork.org"},{"name":"codec_list","value":"AMR-WB,AMR-NB"},{"name":"media_handling","value":"srtp-end-to-end"}]}'},
        {"label": "Unstructured — Mobile Voice Activation",
         "text": "activate new mobile voice service for retail customer with gold SLA: MSISDN 447700123456, IMSI 234151234567890, enable VoLTE with EVS codec, international roaming WorldZone1, IMS APN ims.gold.mnc015.mcc234.gprs, QCI-1 QoS, postpaid charging, SIP domain ims.mnc015.mcc234.3gppnetwork.org, SMSC primary routing with 72h validity, location area LAC-0x4A2B, TAC 0x8C3D"},
        {"label": "TMF640 — Activate L3VPN (Enterprise Platinum)",
         "text": '{"serviceId":"svc-acme-sjc-l3vpn","action":"activate","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"prod-l3vpn-01"},{"name":"pe_ip","value":"10.1.1.1"},{"name":"bandwidth","value":"1000"},{"name":"vrf_name","value":"CUST-ACME-SJC-VRF"},{"name":"rd","value":"65001:101"},{"name":"rt_import","value":"65001:100"},{"name":"rt_export","value":"65001:100"},{"name":"bgp_peer","value":"10.1.1.2"},{"name":"cluster_id","value":"1.1.1.1"},{"name":"peer_group","value":"RR-CLIENTS"},{"name":"asn","value":"65001"},{"name":"route_targets","value":"65001:100,65001:200"},{"name":"interfaces","value":"Gi0/0/1,Gi0/0/2"},{"name":"snmp_community","value":"acme-ro-v3"},{"name":"syslog_server","value":"10.100.1.10"},{"name":"netflow_collector","value":"10.100.1.20:2055"}]}'},
        {"label": "TMF640 — Activate SD-WAN (Dual Transport)",
         "text": '{"serviceId":"sdwan-branches-apac","action":"activate","characteristic":[{"name":"customerSegment","value":"enterprise"},{"name":"slaTier","value":"platinum"},{"name":"productId","value":"prod-sdwan-01"},{"name":"transport_links","value":"MPLS-100M,Internet-500M,4G-backup"},{"name":"encryption","value":"IPSec-AES256-GCM"},{"name":"app_policy","value":"VoIP-priority,SaaS-optimized,BestEffort"},{"name":"wan_interfaces","value":"ge0/0-MPLS,ge0/1-INET,cellular0/0"},{"name":"policy_set","value":"Platinum-APAC-v3"},{"name":"site_list","value":"Tokyo,Singapore,Sydney,Bangkok"},{"name":"template","value":"sdwan-dual-transport-v4"},{"name":"ztp_url","value":"https://ztp.enterprise.net/boot/v4"},{"name":"bootstrap_config","value":"base-config-platinum.yaml"},{"name":"license_key","value":"ENT-SDWAN-PLAT-APAC-2026"}]}'},
        {"label": "TMF641 — ServiceOrder Broadband (FTTH Silver)",
         "text": '{"externalId":"CRM-98765","category":"Broadband","action":"add","characteristic":[{"name":"customerSegment","value":"retail"},{"name":"slaTier","value":"silver"},{"name":"productId","value":"prod-ftth-100m"},{"name":"ont_model","value":"Huawei-HG8245W5"},{"name":"vlan","value":"100"},{"name":"speed_profile","value":"100M-20M"},{"name":"dba_profile","value":"Type3-NSR"},{"name":"ip_pool","value":"POOL-RETAIL-SILVER"},{"name":"subscriber_profile","value":"Residential-Silver"},{"name":"qos_policy","value":"Silver-BestEffort"},{"name":"nas_identifier","value":"BNG-SJC-01"},{"name":"shared_secret","value":"a7f3b9c2e1"},{"name":"auth_method","value":"PAP"},{"name":"snmp_community","value":"ems-readonly-v2"},{"name":"trap_destinations","value":"10.200.1.10:162,10.200.1.11:162"}]}'},
        {"label": "Security Test — Blocked Keyword",
         "text": "activate mobile service 447700123456 with gold SLA and shutdown all interfaces"},
    ]}

@app.get("/health")
async def health():
    return {"status": "ok", "cache_size": len(cache), "redis_backend": "diskcache"}

@app.get("/api/notifications/{order_id}")
async def get_notifications(order_id: str):
    """Retrieve TMF lifecycle notifications for a completed order."""
    with jobs_lock:
        job = jobs.get(order_id)
    if job is None:
        return JSONResponse({"error": "order not found"}, status_code=404)
    if job.final_state is None:
        return JSONResponse({"notifications": [], "message": "Pipeline still processing"}, status_code=200)
    return {
        "orderId": order_id,
        "notifications": job.final_state.get("notifications", []),
        "count": job.final_state.get("notificationCount", 0),
    }


# ====================================================================
# Cache Engine Configuration API
# ====================================================================
@app.get("/api/config/cache")
async def get_cache_config():
    """Get current cache engine and available engines."""
    engine = get_cache_engine()
    # DSL metadata is only relevant when DSL is the active engine.
    # When pattern is active, return null to prevent cross-contamination.
    if engine == "dsl":
        # Ensure DSL definitions are loaded (lazy on first access)
        dsl_engine.load()
        dsl_loaded = dsl_engine._loaded
        dsl_defs = list(dsl_engine._definitions.keys()) if dsl_loaded else []
        dsl_validation = dsl_engine._validation_log if dsl_loaded else []
        dsl_meta = {
            "dslLoaded": dsl_loaded,
            "dslDefinitions": dsl_defs,
            "dslSchemasLoaded": len(dsl_engine._schemas),
            "dslValidationIssues": len(dsl_validation),
            "dslValidationLog": [
                {"file": e.get("file", "").split("/")[-1], "severity": e.get("severity", ""),
                 "message": e.get("message", ""), "schema": e.get("schema", "")}
                for e in dsl_validation[:20]
            ],
        }
    else:
        dsl_meta = {
            "dslLoaded": False,
            "dslDefinitions": [],
            "dslSchemasLoaded": 0,
            "dslValidationIssues": 0,
            "dslValidationLog": [],
        }
    return {
        "engine": engine,
        "availableEngines": ["pattern", "dsl"],
        "description": {
            "pattern": "RDF-inspired auto-learning pattern store with Jaccard matching",
            "dsl": "YAML DSL deterministic templates — always HIT for known services",
        },
        **dsl_meta,
    }


@app.post("/api/config/cache")
async def set_cache_config(request: dict):
    """Set the active cache engine: 'pattern' or 'dsl'."""
    engine = request.get("engine", "")
    if engine not in ("pattern", "dsl"):
        return JSONResponse(
            {"error": f"Unknown engine '{engine}'. Use 'pattern' or 'dsl'."},
            status_code=400)
    try:
        set_cache_engine(engine)
        return {
            "status": "ok",
            "engine": engine,
            "message": f"Cache engine switched to: {engine}",
        }
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ====================================================================
# DSL Definitions API
# ====================================================================
@app.get("/api/dsl/definitions")
async def list_dsl_definitions():
    """List all loaded DSL service definitions."""
    dsl_engine.load()
    result = {}
    for svc, dsl in dsl_engine._definitions.items():
        nes = dsl.get("network_elements", [])
        result[svc] = {
            "domain": dsl.get("domain", ""),
            "networkElementCount": len(nes),
            "networkElements": [
                {
                    "name": n["name"],
                    "workflow": n["workflow"],
                    "attributes": n.get("attributes", []),
                    "conditions": n.get("conditions", []),
                }
                for n in nes
            ],
        }
    return {"definitions": result}


@app.get("/api/dsl/plan/{service_type}")
async def get_dsl_plan(service_type: str):
    """Preview the DSL plan for a given service type (no request context)."""
    dsl_engine.load()
    plan = dsl_engine.lookup(service_type, {})
    if plan is None:
        return JSONResponse(
            {"error": f"No DSL definition for service type: {service_type}"},
            status_code=404)
    return {"serviceType": service_type, "plan": plan}

@app.post("/api/locks/release")
async def release_lock(request: dict):
    """Admin endpoint: force-release a subscriber lock."""
    subscriber_id = request.get("subscriberId", "")
    if not subscriber_id:
        return JSONResponse({"error": "subscriberId required"}, status_code=400)
    subscriber_lock.force_release(subscriber_id)
    return {"status": "released", "subscriberId": subscriber_id}

@app.get("/api/locks/status")
async def lock_status():
    """List all active subscriber locks."""
    locks = []
    for key in list(cache):
        if key.startswith("lock:sub:"):
            val = cache.get(key)
            if val:
                locks.append({
                    "key": key,
                    "subscriberId": key.replace("lock:sub:", ""),
                    "workerId": val.get("worker_id", "?"),
                    "acquiredAt": val.get("acquired_at", 0),
                    "ageSeconds": round(time.time() - val.get("acquired_at", time.time()), 1),
                })
    return {"activeLocks": len(locks), "locks": locks}

# Serve static frontend
@app.get("/")
async def index():
    return FileResponse("/opt/data/telecom-orchestrator/poc/static/index.html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

app.mount("/static", StaticFiles(directory="/opt/data/telecom-orchestrator/poc/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting production PoC server on 0.0.0.0:8090")
    uvicorn.run(app, host="0.0.0.0", port=8090)
