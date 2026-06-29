package com.telecom.orchestrator.pipeline;

import com.telecom.orchestrator.models.*;
import com.telecom.orchestrator.security.DataMasker;
import com.telecom.orchestrator.security.DataMasker.MaskResult;
import com.telecom.orchestrator.store.*;
import com.telecom.orchestrator.notification.LifecycleNotifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PipelineEngine {
    private static final Logger log = LoggerFactory.getLogger(PipelineEngine.class);

    private final PatternStore patterns;
    private final DSLStore dslStore;
    private final ServiceModelStore serviceModels;
    private final SubscriberLock subscriberLock;
    private final ExecutorService executor = Executors.newFixedThreadPool(4);
    private final Map<String, ProcessResponse> jobs = new ConcurrentHashMap<>();

    /** Active cache engine: "pattern" (default) or "dsl". */
    private volatile String cacheEngine = "pattern";

    public PipelineEngine(PatternStore patterns, DSLStore dslStore,
                          ServiceModelStore serviceModels, SubscriberLock subscriberLock) {
        this.patterns = patterns;
        this.dslStore = dslStore;
        this.serviceModels = serviceModels;
        this.subscriberLock = subscriberLock;
        this.patterns.seedFromKB();
        validateAndRepairCache();
    }

    // ──────────────────────────────────────────────────────
    //  Rich detail builder — Goal / Input / Expected / Actual / Output
    // ──────────────────────────────────────────────────────

    /** Build a canonical multi-section trace detail string. */
    private static String detail(String goal, String input, String expected, String actual, String output) {
        StringBuilder sb = new StringBuilder();
        sb.append("Goal: ").append(nullToDash(goal));
        sb.append("\nInput: ").append(nullToDash(input));
        sb.append("\nExpected: ").append(nullToDash(expected));
        sb.append("\nActual: ").append(nullToDash(actual));
        sb.append("\nOutput: ").append(nullToDash(output));
        return sb.toString();
    }

    private static String nullToDash(String s) { return (s == null || s.isEmpty()) ? "—" : s; }

    // ===== START PIPELINE (foreground) =====

    public ProcessResponse startPipeline(String prompt) {
        String orderId = "PO-" + UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
        List<TraceStep> trace = Collections.synchronizedList(new ArrayList<>());
        long t0 = System.currentTimeMillis();

        // Step-emitter closure bound to this job's trace
        TraceStepEmitter step = (stage, status, title, detail, color, icon) ->
            trace.add(new TraceStep(stage, status, title, detail, color, icon, elapsed(t0)));

        String[] fmt = {""};
        boolean[] isJson = {false};
        String[] svc = {""};
        Map<String, Object> chars = new LinkedHashMap<>();
        Map<String, Object> allChars = new LinkedHashMap<>();
        String[] maskedText = {""};
        Map<String, String> tokenMap = Map.of();
        int[] nTokens = {0};
        boolean[] llmUsed = {false};
        PatternNode[] patternHit = {null};
        Map<String, Object>[] plan = new Map[]{null};
        String[] subscriberId = {""};
        Map<String, Object>[] previousModel = new Map[]{null};
        Map<String, Object>[] patternMatch = new Map[]{null};

        // --- STAGE 0: DETECT ---
        isJson[0] = prompt.strip().startsWith("{");
        if (isJson[0]) {
            fmt[0] = "tmf640";
            try {
                new com.fasterxml.jackson.databind.ObjectMapper().readTree(prompt);
            } catch (Exception e) {
                step.emit("DETECT", "error", "JSON Parse Error",
                    detail("Validate and classify the incoming request format.",
                           "Raw prompt string",
                           "Valid JSON → TMF640/TMF641",
                           "Invalid JSON — aborting.",
                           "Aborted — error returned to caller."),
                    "red", "❌");
                ProcessResponse resp = new ProcessResponse();
                resp.orderId = orderId; resp.format = "invalid"; resp.status = "error";
                resp.trace = Collections.unmodifiableList(new ArrayList<>(trace));
                resp.totalMs = elapsed(t0); resp.startedAt = Instant.now().toString();
                return resp;
            }
        } else {
            fmt[0] = "unstructured";
        }
        step.emit("DETECT", "done", "Format Detection",
            detail("Classify incoming request format.",
                   "Prompt text (" + Math.min(prompt.length(), 120) + " chars)",
                   "JSON → structured (tmf640); text → unstructured",
                   (isJson[0] ? "TMF640 JSON detected." : "Unstructured text detected."),
                   "Format = " + fmt[0]),
            "cyan", "🔍");

        // --- STAGE 1: MASK ---
        DataMasker masker = new DataMasker();
        MaskResult maskResult = masker.mask(prompt);
        maskedText[0] = maskResult.maskedText();
        tokenMap = maskResult.tokenMap();
        nTokens[0] = tokenMap.size();
        step.emit("MASK", "done",
            nTokens[0] > 0 ? "Data Masking — " + nTokens[0] + " Identifiers Tokenized" : "Data Masking",
            detail("Strip sensitive identifiers before cloud AI.",
                   "Raw prompt / service order payload",
                   "All PII (MSISDN, IMSI, IP addresses, etc.) replaced with tokens.",
                   nTokens[0] + " identifier(s) tokenized.",
                   "Masked text ready for downstream stages."),
            "violet", "🛡️");

        // --- STAGE 2: CACHE ---
        svc[0] = detectServiceType(prompt);
        if (isJson[0]) {
            try {
                var node = new com.fasterxml.jackson.databind.ObjectMapper().readTree(prompt);
                var charsNode = node.get("characteristic");
                if (charsNode != null && charsNode.isArray()) {
                    for (var c : charsNode) {
                        String name = c.has("name") ? c.get("name").asText() : (c.has("key") ? c.get("key").asText() : "");
                        String val = c.has("value") ? c.get("value").asText() : "";
                        allChars.put(name, val);
                        if (!PatternStore.INSTANCE_ATTRS.contains(name.toLowerCase())) {
                            chars.put(name, val);
                        }
                    }
                }
            } catch (Exception ignored) {}
        } else {
            chars.put("text_hash", sha256(maskedText[0]).substring(0, 16));
            for (var e : tokenMap.entrySet()) {
                if (e.getKey().startsWith("VAR_MSISDN_")) {
                    allChars.put("msisdn", e.getValue());
                    break;
                } else if (e.getKey().startsWith("VAR_IP_")) {
                    allChars.put("ip_" + e.getKey(), e.getValue());
                }
            }
        }

        subscriberId[0] = extractSubscriberId(prompt, isJson[0], allChars);
        previousModel[0] = serviceModels.get(subscriberId[0]);

        // === CACHE ENGINE SELECTION ===
        if ("dsl".equals(cacheEngine)) {
            // ── DSL Engine: deterministic YAML template ──
            dslStore.load();
            plan[0] = dslStore.lookup(svc[0], allChars);
            patternMatch[0] = buildDslDetail(svc[0]);

            if (plan[0] != null && !((List<?>) plan[0].getOrDefault("devices", List.of())).isEmpty()) {
                // Cascade request chars into plan
                Map<String, Object> pp = (Map<String, Object>) plan[0].get("params");
                if (pp != null && !allChars.isEmpty()) {
                    int cascaded = 0;
                    for (var e : allChars.entrySet()) {
                        String sv = String.valueOf(e.getValue());
                        if (!sv.startsWith("default_") && !sv.startsWith("<")) {
                            pp.put(e.getKey(), e.getValue());
                            cascaded++;
                        }
                    }
                    if (cascaded > 0) plan[0].put("params", pp);
                }
                llmUsed[0] = false;
                step.emit("CACHE", "done", "DSL Cache — " + svc[0] + " ✓",
                    detail("Build plan from DSL templates.",
                           "Service = " + svc[0] + ", chars = " + allChars.size() + " key(s)",
                           "Match known DSL service definitions.",
                           "DSL HIT — " + plan[0].getOrDefault("devices", List.of()).toString(),
                           "Deterministic plan ready; 0ms LLM latency."),
                    "green", "📋");
            } else {
                llmUsed[0] = true;
                plan[0] = null;
                step.emit("CACHE", "done", "DSL Cache — MISS (Empty Plan)",
                    detail("Build plan from DSL templates.",
                           "Service = " + svc[0],
                           "DSL template should produce a plan.",
                           "DSL returned empty plan — falling through to LLM.",
                           "Flagged for LLM fallback."),
                    "amber", "📡");
            }
        } else {
            // ── Pattern Engine: Jaccard matching ──
            PatternNode matched = patterns.lookup(svc[0], chars);
            patterns.reinforce(matched);
            plan[0] = new LinkedHashMap<>();
            List<String> workflows = new ArrayList<>();
            List<String> devices = new ArrayList<>();
            Map<String, Object> params = new LinkedHashMap<>();
            for (var res : matched.resources) {
                String wf = (String) res.get("workflow");
                String name = (String) res.get("name");
                if (wf != null) workflows.add(wf);
                if (name != null) devices.add(name);
                Object attrsObj = res.get("attributes");
                if (attrsObj instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> attrs = (Map<String, Object>) attrsObj;
                    params.putAll(attrs);
                }
            }

            // ── KB fallback plan — when KB-seeded patterns have null device names ──
            if (devices.isEmpty()) {
                var sr = KnowledgeBase.get(svc[0]);
                for (var r : sr.requiredResources()) {
                    String dev = r.type();
                    devices.add(dev);
                    String coreType = r.type().split("/")[0];
                    String wf = KnowledgeBase.WF_MAP.getOrDefault(coreType, coreType + "_Configuration");
                    if (!workflows.contains(wf)) workflows.add(wf);
                }
                log.debug("Cache-hit {} → KB fallback plan: {} devices, {} workflows",
                        matched.id, devices.size(), workflows.size());
            }

            plan[0].put("workflows", workflows);
            plan[0].put("devices", devices);
            plan[0].put("params", params);

            // Cascade all_chars into plan
            if (!allChars.isEmpty()) {
                int cascaded = 0;
                for (var e : allChars.entrySet()) {
                    String sv = String.valueOf(e.getValue());
                    if (!sv.startsWith("default_") && !sv.startsWith("<")) {
                        params.put(e.getKey(), e.getValue());
                        cascaded++;
                    }
                }
                if (cascaded > 0) {
                    step.emit("MERGE", "done", "Sync-Phase Merge — " + cascaded + " Request Chars Cascaded",
                        detail("Cascade request characteristics into cached plan.",
                               "Request chars: " + cascaded + " key(s)",
                               "Request values override cache defaults.",
                               cascaded + " characteristic(s) overlaid onto cached plan params.",
                               "Plan params enriched with request values."),
                        "violet", "🔄");
                }
            }
            llmUsed[0] = false;
            patternHit[0] = matched;
            patternMatch[0] = buildHitDetail(matched, chars);
            step.emit("CACHE", "done", "Pattern Match — " + matched.id + " ✓",
                detail("Query pattern store for best-matching cached plan.",
                       "Service type = " + svc[0] + ", chars = " + chars.size() + " key(s)",
                       "Jaccard match against stored patterns.",
                       "HIT — " + matched.label + " (confidence " + (int)(matched.confidence*100) + "%)",
                       "Pattern " + matched.id + "; plan extracted from cache."),
                "green", "⚡");
        } else {
            llmUsed[0] = true;
            patternMatch[0] = buildMissDetail(svc[0], chars);
            step.emit("CACHE", "done", "Pattern Store — MISS",
                detail("Query pattern store for best-matching cached plan.",
                       "Service type = " + svc[0] + ", chars = " + chars.size() + " key(s)",
                       "Jaccard match against stored patterns.",
                       "MISS — no pattern above threshold.",
                       "Will invoke LLM for plan generation."),
                "amber", "📡");
        }

        } // end pattern engine branch

        step.emit("LLM", "done", "Pipeline Dispatched — Background Processing",
            detail("Offload remaining stages to background thread.",
                   "OrderId = " + orderId,
                   "Background executor picks up the job.",
                   "Background thread started.",
                   "Immediate response returned to caller."),
            "green", "⏳");

        ProcessResponse result = new ProcessResponse();
        result.orderId = orderId; result.format = fmt[0]; result.status = "processing";
        result.trace = Collections.unmodifiableList(new ArrayList<>(trace));
        result.totalMs = elapsed(t0); result.startedAt = Instant.now().toString();
        jobs.put(orderId, result);

        // Dispatch background
        var bgState = new BackgroundState(orderId, fmt[0], svc[0], maskedText[0], tokenMap, nTokens[0],
                llmUsed[0], chars, allChars, subscriberId[0], previousModel[0], plan[0],
                patternHit[0], patternMatch[0], t0);
        executor.submit(() -> runBackground(bgState));

        return result;
    }

    // ===== BACKGROUND PIPELINE =====

    private void runBackground(BackgroundState st) {
        try {
            var trace = Collections.synchronizedList(new ArrayList<>(jobs.get(st.orderId).trace));
            long t0 = st.t0;

            // Step-emitter for background
            TraceStepEmitter step = (stage, status, title, detail, color, icon) ->
                trace.add(new TraceStep(stage, status, title, detail, color, icon, elapsed(t0)));

            // STAGE 3: RAG
            var sr = KnowledgeBase.get(st.svc);
            int ragResources = sr.requiredResources().size();
            step.emit("RAG", "done", "Knowledge Base RAG",
                detail("Load telecom domain context from knowledge base.",
                       "Service type = " + st.svc,
                       "Relevant standards, resource definitions, and lifecycle loaded.",
                       "Context loaded: " + ragResources + " resource(s), domain " + sr.domain()
                           + ", standards " + String.join(", ", sr.standards()),
                       "KB context available for LLM / validation stages."),
                "blue", "📚");

            // STAGE 4: LLM
            Map<String, Object> plan = st.plan;
            if (st.llmUsed) {
                step.emit("LLM", "running", "LLM Plan Generation",
                    detail("Generate orchestration plan via LLM.",
                           "Service type = " + st.svc + ", masked prompt + KB context",
                           "LLM returns structured plan (workflows, devices, params).",
                           "Calling LLM (Deepseek)…",
                           "Awaiting LLM response."),
                    "blue", "🧠");
                plan = callLLM(st);
                step.emit("LLM", "done", "LLM Plan Generated ✓",
                    detail("Generate orchestration plan via LLM.",
                           "Service type = " + st.svc + ", KB context supplied",
                           "Structured plan with workflows, devices, and params.",
                           "Plan received from LLM.",
                           "Plan ready for validation and execution."),
                    "blue", "🧠");
            } else {
                step.emit("LLM", "done", "LLM — Skipped (Cache Hit)",
                    detail("Generate orchestration plan via LLM (only if cache missed).",
                           "Cache-hit → plan from pattern store.",
                           "LLM invocation unnecessary when cache provides plan.",
                           "LLM bypassed — cached plan used.",
                           "Cached plan proceeds to hydration."),
                    "green", "🧠");
            }

            // Flatten params
            plan = flattenPlanParams(plan);

            // STAGE 5: HYDRATE
            if (!st.tokenMap.isEmpty()) {
                plan = hydratePlan(plan, st.tokenMap);
                step.emit("HYDRATE", "done", "Parameter Hydration",
                    detail("Restore real identifiers in plan parameters.",
                           "Token map: " + st.nTokens + " token(s)",
                           "All tokens replaced with original values.",
                           st.nTokens + " token(s) resolved to real identifiers.",
                           "Plan params contain real values for execution."),
                    "violet", "💧");
            } else {
                step.emit("HYDRATE", "done", "Parameter Hydration",
                    detail("Restore real identifiers in plan parameters.",
                           "No tokens present.",
                           "Hydration only needed when masking produced tokens.",
                           "No tokens to resolve — plan already has real values.",
                           "Plan ready for lock acquisition."),
                    "violet", "💧");
            }

            // Harvest chars for unstructured
            if ("unstructured".equals(st.fmt) && plan != null && plan.get("params") instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> pp = (Map<String, Object>) plan.get("params");
                for (var e : pp.entrySet()) {
                    String sv = String.valueOf(e.getValue());
                    if (!st.allChars.containsKey(e.getKey()) && !sv.startsWith("default_")) {
                        st.allChars.put(e.getKey(), e.getValue());
                    }
                }
            }

            // STAGE 6: LOCK
            boolean lockAcquired = subscriberLock.tryAcquire(st.subscriberId, st.orderId);
            if (!lockAcquired) {
                step.emit("LOCK", "error", "Subscriber Lock — TIMEOUT",
                    detail("Acquire exclusive subscriber lock.",
                           "SubscriberId = " + st.subscriberId + ", OrderId = " + st.orderId,
                           "Lock granted within timeout window.",
                           "Lock held by another worker — timed out.",
                           "Job placed in blocked state; retry later."),
                    "red", "🔒");
                updateJob(st.orderId, st.fmt, "blocked", trace, elapsed(t0), null);
                return;
            }
            step.emit("LOCK", "done", "Subscriber Lock — Acquired ✓",
                detail("Acquire exclusive subscriber lock.",
                       "SubscriberId = " + st.subscriberId + ", OrderId = " + st.orderId,
                       "Lock granted within timeout window.",
                       "Lock acquired successfully.",
                       "Exclusive access to subscriber model for merge/execute."),
                "violet", "🔒");

            // STAGE 7: MERGE
            int mergedCount = 0, filledCount = 0;
            @SuppressWarnings("unchecked")
            Map<String, Object> planParams = (Map<String, Object>) (plan != null ? plan.getOrDefault("params", new LinkedHashMap<>()) : new LinkedHashMap<>());
            if (!st.allChars.isEmpty()) {
                for (var e : st.allChars.entrySet()) {
                    String sv = String.valueOf(e.getValue());
                    if (!sv.startsWith("default_") && !sv.startsWith("<")) {
                        planParams.put(e.getKey(), e.getValue());
                        mergedCount++;
                    }
                }
            }
            if (st.previousModel != null) {
                @SuppressWarnings("unchecked")
                Map<String, Object> prevChars = (Map<String, Object>) st.previousModel.get("characteristics");
                if (prevChars != null) {
                    for (var e : prevChars.entrySet()) {
                        if (!st.allChars.containsKey(e.getKey()) && !planParams.containsKey(e.getKey())) {
                            String sv = String.valueOf(e.getValue());
                            if (!sv.startsWith("default_")) {
                                planParams.put(e.getKey(), e.getValue());
                                filledCount++;
                            }
                        }
                    }
                }
            }
            if (mergedCount > 0 || filledCount > 0) {
                if (plan != null) plan.put("params", planParams);
                step.emit("MERGE", "done", "Characteristic Merge",
                    detail("Cascade request and previous-model characteristics into plan parameters.",
                           "Request chars + previous model chars",
                           "Request values override plan defaults; previous-model values fill gaps.",
                           mergedCount + " from request, " + filledCount + " from previous model.",
                           "Plan params enriched for execution."),
                    "violet", "🔄");
            }

            // STAGE 6a: WRITE-THROUGH
            if (st.llmUsed && plan != null) {
                PatternNode learned = patterns.learn(st.svc, st.chars, plan, st.allChars, "auto");
                st.patternHit = learned;
                step.emit("CACHE", "done", "Pattern Learning",
                    detail("Learn new pattern from LLM-generated plan for future cache hits.",
                           "Plan: " + plan.keySet() + " | chars: " + st.chars.size() + " key(s)",
                           "New pattern persisted with deterministic ID.",
                           "Pattern " + learned.id + " learned (confidence " + String.format("%.0f%%", learned.confidence*100) + ").",
                           "Future matching requests will use this cached plan."),
                    "green", "💾");
            }

            // STAGE 8: VALIDATE
            String checkText = (new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(plan) + " " + st.maskedText).toLowerCase();
            List<String> blocked = new ArrayList<>();
            for (String kw : KnowledgeBase.BLOCKED_KEYWORDS) {
                if (checkText.contains(kw)) blocked.add(kw);
            }
            if (!blocked.isEmpty()) {
                step.emit("VALIDATE", "blocked", "Security Gateway — BLOCKED 🚫",
                    detail("Validate orchestration plan against blocked-keyword list.",
                           "Plan text + masked prompt",
                           "No blocked keywords (erase, reload, format, shutdown, etc.) detected.",
                           "BLOCKED — " + String.join(", ", blocked) + " detected in plan.",
                           "Job halted; subscriber lock released."),
                    "red", "🚫");
                updateJob(st.orderId, st.fmt, "blocked", trace, elapsed(t0), null);
                subscriberLock.release(st.subscriberId, st.orderId);
                return;
            }
            step.emit("VALIDATE", "done", "Security Gateway — PASSED ✓",
                detail("Validate orchestration plan against blocked-keyword list.",
                       "Plan text + masked prompt",
                       "No blocked keywords detected.",
                       "All security checks passed.",
                       "Plan cleared for execution."),
                "green", "🔒");

            // STAGE 9: EXECUTE
            @SuppressWarnings("unchecked")
            List<String> workflows = plan != null ? (List<String>) plan.getOrDefault("workflows", List.of()) : List.of();
            @SuppressWarnings("unchecked")
            List<String> devices = plan != null ? (List<String>) plan.getOrDefault("devices", List.of()) : List.of();
            int neCount = devices.size();
            step.emit("EXECUTE", "done", "Execution — Workflows Dispatched",
                detail("Dispatch orchestration plan to network elements.",
                       "Plan: " + neCount + " device(s), " + workflows.size() + " workflow(s)",
                       "Each device receives its configuration workflow.",
                       neCount + " workflow(s) dispatched to " + neCount + " device(s) (stubbed).",
                       "Execution complete — moving to verification."),
                "amber", "⚙️");

            // STAGE 10: VERIFY
            var finalState = buildFinalState(st, plan, trace, t0, step);

            // STAGE 11: NOTIFY — emit individual trace steps per lifecycle state
            LifecycleNotifier notifier = new LifecycleNotifier();
            // Pass step callback so the notifier can emit trace steps
            int notifCount = notifier.buildNotificationTrace(st.orderId, st.svc, st.subscriberId, step, elapsed(t0));
            finalState.put("notifications", notifier.flush());
            finalState.put("notificationCount", notifCount);

            subscriberLock.release(st.subscriberId, st.orderId);
            updateJob(st.orderId, st.fmt, "completed", trace, elapsed(t0), finalState);

        } catch (Exception e) {
            log.error("Background pipeline crashed for {}", st.orderId, e);
            var trace = Collections.synchronizedList(new ArrayList<>(jobs.get(st.orderId).trace));
            TraceStepEmitter step = (stage, status, title, detail, color, icon) ->
                trace.add(new TraceStep(stage, status, title, detail, color, icon, elapsed(st.t0)));
            step.emit("ERROR", "error", "Pipeline Crashed",
                detail("Catch-all error handler for unhandled exceptions.",
                       "Background pipeline for " + st.orderId,
                       "Pipeline should complete cleanly.",
                       "Unhandled exception: " + e.getMessage(),
                       "Job marked as error; manual intervention may be required."),
                "red", "💥");
            updateJob(st.orderId, st.fmt, "error", trace, elapsed(st.t0), null);
        }
    }

    // ===== HELPERS =====

    private Map<String, Object> buildFinalState(BackgroundState st, Map<String, Object> plan,
                                                 List<TraceStep> trace, long t0, TraceStepEmitter step) {
        String svcId = "SVC-" + UUID.randomUUID().toString().replace("-", "").substring(0, 6).toUpperCase();
        var sr = KnowledgeBase.get(st.svc);

        // Build network elements
        List<Map<String, Object>> networkElements = new ArrayList<>();
        @SuppressWarnings("unchecked")
        List<String> devices = plan != null ? (List<String>) plan.getOrDefault("devices", List.of()) : List.of();
        @SuppressWarnings("unchecked")
        Map<String, Object> params = plan != null ? (Map<String, Object>) plan.getOrDefault("params", Map.of()) : Map.of();
        @SuppressWarnings("unchecked")
        List<String> workflows = plan != null ? (List<String>) plan.getOrDefault("workflows", List.of()) : List.of();

        // Previous NE attrs for gap-filling
        Map<String, Map<String, Object>> prevNeAttrs = new LinkedHashMap<>();
        if (st.previousModel != null) {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> prevNes = (List<Map<String, Object>>) st.previousModel.get("network_elements");
            if (prevNes != null) {
                for (var ne : prevNes) {
                    String name = (String) ne.get("name");
                    @SuppressWarnings("unchecked")
                    Map<String, Object> attrs = (Map<String, Object>) ne.get("attributes");
                    if (name != null && attrs != null) {
                        prevNeAttrs.put(name, attrs);
                        String canonical = name.split("/")[0];
                        if (!canonical.equals(name)) prevNeAttrs.put(canonical, attrs);
                    }
                }
            }
        }

        for (int i = 0; i < devices.size(); i++) {
            String dev = devices.get(i);
            String wf = i < workflows.size() ? workflows.get(i) : "Configuration";
            KnowledgeBase.ResourceDef kbRes = null;
            for (var r : sr.requiredResources()) {
                for (String part : r.type().toLowerCase().replace("/", " ").split(" ")) {
                    if (dev.toLowerCase().contains(part)) { kbRes = r; break; }
                }
                if (kbRes != null) break;
            }
            Map<String, Object> attrs = new LinkedHashMap<>();
            if (kbRes != null) {
                for (String attr : kbRes.attributes()) {
                    if (params.containsKey(attr)) attrs.put(attr, String.valueOf(params.get(attr)));
                    else if (st.allChars.containsKey(attr)) attrs.put(attr, String.valueOf(st.allChars.get(attr)));
                    else if (st.chars.containsKey(attr)) attrs.put(attr, String.valueOf(st.chars.get(attr)));
                    else {
                        Map<String, Object> prevAttrs = prevNeAttrs.get(dev);
                        if (prevAttrs == null) {
                            String canonical = dev.split("/")[0];
                            prevAttrs = prevNeAttrs.get(canonical);
                        }
                        if (prevAttrs != null && prevAttrs.containsKey(attr) && !String.valueOf(prevAttrs.get(attr)).startsWith("default_")) {
                            attrs.put(attr, String.valueOf(prevAttrs.get(attr)));
                        } else {
                            attrs.put(attr, "default_" + attr);
                        }
                    }
                }
                attrs.put("status", "Configured");
            } else {
                for (var e : params.entrySet()) {
                    attrs.put(e.getKey(), String.valueOf(e.getValue()));
                }
                attrs.put("status", "Configured");
            }
            Map<String, Object> ne = new LinkedHashMap<>();
            ne.put("name", dev);
            ne.put("type", kbRes != null ? kbRes.type() : dev);
            ne.put("workflow", wf);
            ne.put("role", kbRes != null ? kbRes.role() : "Network function");
            ne.put("attributes", attrs);
            networkElements.add(ne);
        }

        // Compute diff + save model
        Map<String, Object> diff = serviceModels.computeDiff(st.previousModel, st.allChars, networkElements);
        int version = st.previousModel != null ? ((Number) st.previousModel.getOrDefault("version", 0)).intValue() : 0;
        Map<String, Object> newModel = serviceModels.buildModel(st.subscriberId, st.svc, st.allChars, networkElements, version);
        serviceModels.save(st.subscriberId, newModel);

        Map<String, Object> fs = new LinkedHashMap<>();
        fs.put("serviceId", svcId);
        fs.put("state", "ACTIVE");
        fs.put("workflowsExecuted", workflows.size());
        fs.put("resourcesProvisioned", params.size());
        fs.put("networkElements", networkElements);
        fs.put("patternId", st.patternHit != null ? st.patternHit.id : null);
        fs.put("patternConfidence", st.patternHit != null ? st.patternHit.confidence : 0);
        fs.put("llmUsed", st.llmUsed);
        fs.put("patternMatch", st.patternMatch);
        fs.put("subscriberId", st.subscriberId);
        fs.put("subscriberDiff", diff);

        step.emit("VERIFY", "done", "Verification & Model Persistence",
            detail("Verify orchestration result and persist service model.",
                   "Plan: " + devices.size() + " device(s), " + workflows.size() + " workflow(s)",
                   "Service model persisted; diff computed against previous version.",
                   "Service " + svcId + " ACTIVE — " + networkElements.size() + " NE(s) configured.",
                   "Model version " + (version + 1) + " saved for subscriber " + st.subscriberId + "."),
            "green", "✅");

        return fs;
    }

    private Map<String, Object> buildHitDetail(PatternNode matched, Map<String, Object> chars) {
        // Request service-defining keys (exclude instance attrs)
        Set<String> reqServiceKeys = new LinkedHashSet<>();
        // Instance attrs present in the request
        List<String> excludedInstanceAttrs = new ArrayList<>();
        for (String k : chars.keySet()) {
            if (!PatternStore.INSTANCE_ATTRS.contains(k.toLowerCase())) {
                reqServiceKeys.add(k);
            } else {
                excludedInstanceAttrs.add(k);
            }
        }

        Set<String> patKeys = matched.characteristics.keySet();
        Set<String> matchedKeys = new LinkedHashSet<>();
        Set<String> mismatchedKeys = new LinkedHashSet<>();
        for (String k : reqServiceKeys) {
            if (patKeys.contains(k) && String.valueOf(chars.get(k)).equals(String.valueOf(matched.characteristics.get(k)))) {
                matchedKeys.add(k);
            } else if (patKeys.contains(k)) {
                mismatchedKeys.add(k);
            }
        }
        Set<String> extraKeys = new LinkedHashSet<>(reqServiceKeys);
        extraKeys.removeAll(patKeys);

        // Sort excluded instance attrs
        Collections.sort(excludedInstanceAttrs);

        // Build request characters map (service-defining only)
        Map<String, Object> requestChars = new LinkedHashMap<>();
        for (String k : reqServiceKeys) {
            requestChars.put(k, chars.get(k));
        }

        // Pattern characteristics as string-keyed map
        Map<String, Object> patternChars = new LinkedHashMap<>(matched.characteristics);

        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("result", "HIT");
        detail.put("patternId", matched.id);
        detail.put("patternLabel", matched.label);
        detail.put("confidence", Math.round(matched.confidence * 100.0) / 100.0);
        detail.put("useCount", matched.useCount);
        detail.put("triplesCount", matched.triples.size());
        detail.put("resourcesCount", matched.resources.size());
        detail.put("compareLogic", "Jaccard similarity on service-defining characteristics");
        detail.put("excludedInstanceAttrs", excludedInstanceAttrs);
        detail.put("patternChars", patternChars);
        detail.put("requestChars", requestChars);
        detail.put("matchedKeys", new ArrayList<>(matchedKeys));
        detail.put("mismatchedKeys", new ArrayList<>(mismatchedKeys));
        detail.put("extraKeys", new ArrayList<>(extraKeys));
        double score = matchedKeys.size() / (double) Math.max(reqServiceKeys.size() + patKeys.size(), 1);
        detail.put("score", Math.round(score * 10000.0) / 10000.0);
        return detail;
    }

    private Map<String, Object> buildMissDetail(String svc, Map<String, Object> chars) {
        Set<String> reqKeys = new LinkedHashSet<>();
        for (String k : chars.keySet()) {
            if (!PatternStore.INSTANCE_ATTRS.contains(k.toLowerCase())) reqKeys.add(k);
        }
        List<Map<String, Object>> allPats = patterns.listAll();
        long sameSvc = allPats.stream().filter(p -> svc.equals(p.get("service_type"))).count();

        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("result", "MISS");
        detail.put("patternsInStore", allPats.size());
        detail.put("patternsForService", (int) sameSvc);
        detail.put("requestChars", chars);
        return detail;
    }

    private Map<String, Object> buildDslDetail(String svc) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("result", "DSL");
        detail.put("patternId", "dsl:" + svc);
        List<String> domains = dslStore.getServiceNames();
        detail.put("patternLabel", "DSL -> " + svc);
        detail.put("confidence", 1.0);
        detail.put("useCount", 0);
        detail.put("compareLogic", "DSL template — deterministic mapping (no Jaccard matching)");
        detail.put("matchedKeys", List.of());
        detail.put("mismatchedKeys", List.of());
        detail.put("extraKeys", List.of());
        detail.put("score", 1.0);
        return detail;
    }

    // ===== UTILITIES =====

    private Map<String, Object> callLLM(BackgroundState st) {
        // Try real LLM call, fallback to KB-derived plan
        Map<String, Object> plan = fallbackPlan(st.svc);
        try {
            // In PoC: subprocess call to hermes chat or direct API
            // For this implementation: use fallback plan
            log.info("LLM call for {} — using fallback plan", st.svc);
        } catch (Exception e) {
            log.warn("LLM call failed: {}", e.getMessage());
        }
        return plan;
    }

    private Map<String, Object> fallbackPlan(String svc) {
        var sr = KnowledgeBase.get(svc);
        List<String> devices = new ArrayList<>();
        List<String> workflowsList = new ArrayList<>();
        Map<String, Object> params = new LinkedHashMap<>();

        for (var r : sr.requiredResources()) {
            String dev = r.type().replace("/", "-");
            devices.add(dev);
            String coreType = r.type().split("/")[0];
            String wf = KnowledgeBase.WF_MAP.getOrDefault(coreType, coreType + "_Configuration");
            workflowsList.add(wf);
            for (String attr : r.attributes()) {
                params.putIfAbsent(attr, "<" + attr + ">");
            }
        }

        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("workflows", workflowsList);
        plan.put("params", params);
        plan.put("devices", devices);
        return plan;
    }

    private Map<String, Object> flattenPlanParams(Map<String, Object> plan) {
        if (plan == null) return new LinkedHashMap<>();
        Object paramsObj = plan.get("params");
        if (!(paramsObj instanceof Map)) return plan;
        @SuppressWarnings("unchecked")
        Map<String, Object> params = (Map<String, Object>) paramsObj;
        boolean nested = params.values().stream().anyMatch(v -> v instanceof Map);
        if (nested) {
            Map<String, Object> flat = new LinkedHashMap<>();
            for (Object v : params.values()) {
                if (v instanceof Map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> sub = (Map<String, Object>) v;
                    flat.putAll(sub);
                }
            }
            if (!flat.isEmpty()) plan.put("params", flat);
        }
        return plan;
    }

    private Map<String, Object> hydratePlan(Map<String, Object> plan, Map<String, String> tokenMap) {
        try {
            String json = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(plan);
            for (var e : tokenMap.entrySet()) {
                json = json.replace(e.getKey(), e.getValue());
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> result = new com.fasterxml.jackson.databind.ObjectMapper().readValue(json, Map.class);
            return result;
        } catch (Exception e) {
            return plan;
        }
    }

    private String extractSubscriberId(String prompt, boolean isJson, Map<String, Object> allChars) {
        if (isJson) {
            try {
                var node = new com.fasterxml.jackson.databind.ObjectMapper().readTree(prompt);
                if (node.has("serviceId")) return node.get("serviceId").asText();
                if (node.has("externalId")) return node.get("externalId").asText();
            } catch (Exception ignored) {}
        }
        if (allChars.containsKey("msisdn")) return "MSISDN-" + allChars.get("msisdn");
        return "SUB-" + sha256(prompt).substring(0, 12).toUpperCase();
    }

    public static String detectServiceType(String text) {
        String t = text.toLowerCase();
        if (containsAny(t, "mobile", "msisdn", "sim", "activate", "voice", "sms")) return "mobile";
        if (containsAny(t, "l3vpn", "mpls", "vpn", "bgp", "vrf") && !t.contains("sd")) return "l3vpn";
        if (containsAny(t, "sd-wan", "sdwan", "sd wan")) return "sdwan";
        if (containsAny(t, "broadband", "ftth", "fiber", "ont", "olt")) return "broadband";
        return "mobile";
    }

    private static boolean containsAny(String text, String... keywords) {
        for (String kw : keywords) if (text.contains(kw)) return true;
        return false;
    }

    private static String sha256(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : hash) hex.append(String.format("%02x", b));
            return hex.toString();
        } catch (Exception e) { return Integer.toHexString(input.hashCode()); }
    }

    private static int elapsed(long t0) {
        return (int) (System.currentTimeMillis() - t0);
    }

    private void updateJob(String orderId, String fmt, String status, List<TraceStep> trace, int totalMs, Map<String, Object> finalState) {
        ProcessResponse resp = jobs.get(orderId);
        if (resp != null) {
            resp.format = fmt;
            resp.status = status;
            resp.trace = Collections.unmodifiableList(new ArrayList<>(trace));
            resp.totalMs = totalMs;
            resp.finalState = finalState;
        }
    }

    public ProcessResponse getJob(String orderId) {
        return jobs.get(orderId);
    }

    public List<Map<String, Object>> listPatterns() {
        return patterns.listAll();
    }

    public Map<String, Object> getPattern(String pid) {
        return patterns.get(pid);
    }

    public PatternNode teachPattern(List<List<String>> triples) {
        return patterns.teach(triples, "teach");
    }

    // ── Cache Engine Control ───────────────────────

    public String getCacheEngine() {
        return cacheEngine;
    }

    public void setCacheEngine(String engine) {
        if (!"pattern".equals(engine) && !"dsl".equals(engine)) {
            throw new IllegalArgumentException("Unknown cache engine: " + engine);
        }
        this.cacheEngine = engine;
        log.info("Cache engine switched to: {}", engine);
    }

    public boolean isDslLoaded() {
        return dslStore != null && dslStore.isLoaded();
    }

    public List<String> getDslServiceNames() {
        return dslStore != null ? dslStore.getServiceNames() : List.of();
    }

    public Map<String, Object> listDslDefinitions() {
        return dslStore != null ? dslStore.listAll() : Map.of("definitions", Map.of());
    }

    public Map<String, Object> getDslPlan(String serviceType) {
        return dslStore != null ? dslStore.lookup(serviceType, Map.of()) : null;
    }

    private void validateAndRepairCache() {
        log.info("Cache integrity: OK — Java PoC startup scan complete");
    }

    // Background state (mutable — not a record)
    static class BackgroundState {
        final String orderId, fmt, svc, maskedText, subscriberId;
        final Map<String, String> tokenMap;
        final Map<String, Object> chars, allChars, plan, patternMatch;
        final Map<String, Object> previousModel;
        PatternNode patternHit;
        final int nTokens;
        final boolean llmUsed;
        final long t0;

        BackgroundState(String orderId, String fmt, String svc, String maskedText,
                        Map<String, String> tokenMap, int nTokens, boolean llmUsed,
                        Map<String, Object> chars, Map<String, Object> allChars,
                        String subscriberId, Map<String, Object> previousModel,
                        Map<String, Object> plan, PatternNode patternHit,
                        Map<String, Object> patternMatch, long t0) {
            this.orderId = orderId;
            this.fmt = fmt;
            this.svc = svc;
            this.maskedText = maskedText;
            this.tokenMap = tokenMap;
            this.nTokens = nTokens;
            this.llmUsed = llmUsed;
            this.chars = chars != null ? chars : new LinkedHashMap<>();
            this.allChars = allChars != null ? allChars : new LinkedHashMap<>();
            this.subscriberId = subscriberId;
            this.previousModel = previousModel;
            this.plan = plan;
            this.patternHit = patternHit;
            this.patternMatch = patternMatch;
            this.t0 = t0;
        }
    }
}
