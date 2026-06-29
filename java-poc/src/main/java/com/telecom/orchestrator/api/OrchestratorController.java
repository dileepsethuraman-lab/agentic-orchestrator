package com.telecom.orchestrator.api;

import com.telecom.orchestrator.models.ProcessRequest;
import com.telecom.orchestrator.models.ProcessResponse;
import com.telecom.orchestrator.pipeline.PipelineEngine;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
public class OrchestratorController {

    private final PipelineEngine engine;

    public OrchestratorController(PipelineEngine engine) {
        this.engine = engine;
    }

    @PostMapping("/api/process")
    public ProcessResponse process(@Valid @RequestBody ProcessRequest request) {
        return engine.startPipeline(request.prompt);
    }

    @GetMapping("/api/process/{orderId}")
    public ResponseEntity<?> getProcess(@PathVariable String orderId) {
        ProcessResponse job = engine.getJob(orderId);
        if (job == null) {
            return ResponseEntity.status(404).body(Map.of("error", "order not found"));
        }
        return ResponseEntity.ok(job);
    }

    @GetMapping("/api/patterns")
    public Map<String, Object> listPatterns() {
        return Map.of("patterns", engine.listPatterns());
    }

    @GetMapping("/api/patterns/{patternId}")
    public ResponseEntity<?> getPattern(@PathVariable String patternId) {
        Map<String, Object> pat = engine.getPattern(patternId);
        if (pat == null) {
            return ResponseEntity.status(404).body(Map.of("error", "pattern not found"));
        }
        return ResponseEntity.ok(pat);
    }

    @PostMapping("/api/patterns/teach")
    public ResponseEntity<?> teachPattern(@RequestBody Map<String, Object> request) {
        @SuppressWarnings("unchecked")
        List<List<String>> triples = (List<List<String>>) request.get("triples");
        if (triples == null || triples.isEmpty()) {
            return ResponseEntity.status(400).body(Map.of("error", "triples required"));
        }
        return ResponseEntity.ok(Map.of("status", "learned", "pattern", engine.teachPattern(triples).toDict()));
    }

    @GetMapping("/api/samples")
    public Map<String, Object> getSamples() {
        List<Map<String, String>> samples = new ArrayList<>();
        samples.add(Map.of("label", "TMF640 — Activate Mobile Voice (Gold)",
                "text", "{\"serviceId\":\"MSISDN-447700123456\",\"action\":\"activate\",\"characteristic\":[{\"name\":\"customerSegment\",\"value\":\"retail\"},{\"name\":\"slaTier\",\"value\":\"gold\"},{\"name\":\"msisdn\",\"value\":\"447700123456\"}]}"));
        samples.add(Map.of("label", "Unstructured — Mobile Voice Activation",
                "text", "activate new mobile voice service for retail customer with gold SLA: MSISDN 447700123456"));
        samples.add(Map.of("label", "TMF640 — Activate L3VPN (Enterprise Platinum)",
                "text", "{\"serviceId\":\"svc-acme-sjc-l3vpn\",\"action\":\"activate\",\"characteristic\":[{\"name\":\"customerSegment\",\"value\":\"enterprise\"},{\"name\":\"slaTier\",\"value\":\"platinum\"},{\"name\":\"vrf_name\",\"value\":\"CUST-ACME-SJC-VRF\"}]}"));
        samples.add(Map.of("label", "Security Test — Blocked Keyword",
                "text", "activate mobile service 447700123456 with gold SLA and shutdown all interfaces"));
        return Map.of("samples", samples);
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "cache_size", engine.listPatterns().size(), "backend", "H2/Spring Boot");
    }

    // ── Cache Engine Configuration ──────────────────────
    // Mirrors Python PoC POST /api/config/cache

    @GetMapping("/api/config/cache")
    public Map<String, Object> getCacheConfig() {
        String currentEngine = engine.getCacheEngine();
        // DSL metadata is only relevant when DSL is the active engine.
        // When pattern is active, return empty to prevent cross-contamination.
        boolean dslLoaded = "dsl".equals(currentEngine) && engine.isDslLoaded();
        List<String> dslDefinitions = "dsl".equals(currentEngine)
                ? engine.getDslServiceNames()
                : List.of();
        return Map.of(
            "engine", currentEngine,
            "availableEngines", List.of("pattern", "dsl"),
            "description", Map.of(
                "pattern", "RDF-inspired auto-learning pattern store with Jaccard matching",
                "dsl", "YAML DSL deterministic templates — always HIT for known services"
            ),
            "dslLoaded", dslLoaded,
            "dslDefinitions", dslDefinitions
        );
    }

    @PostMapping("/api/config/cache")
    public ResponseEntity<?> setCacheConfig(@RequestBody Map<String, Object> request) {
        String engine = (String) request.getOrDefault("engine", "");
        if (!"pattern".equals(engine) && !"dsl".equals(engine)) {
            return ResponseEntity.status(400).body(Map.of(
                "error", "Unknown engine '" + engine + "'. Use 'pattern' or 'dsl'."
            ));
        }
        engine.setCacheEngine(engine);
        return ResponseEntity.ok(Map.of(
            "status", "ok",
            "engine", engine,
            "message", "Cache engine switched to: " + engine
        ));
    }

    // ── DSL Definitions ─────────────────────────────────

    @GetMapping("/api/dsl/definitions")
    public Map<String, Object> listDslDefinitions() {
        return engine.listDslDefinitions();
    }

    @GetMapping("/api/dsl/plan/{serviceType}")
    public ResponseEntity<?> getDslPlan(@PathVariable String serviceType) {
        Map<String, Object> plan = engine.getDslPlan(serviceType);
        if (plan == null) {
            return ResponseEntity.status(404).body(Map.of(
                "error", "No DSL definition for service type: " + serviceType
            ));
        }
        return ResponseEntity.ok(Map.of(
            "serviceType", serviceType,
            "plan", plan
        ));
    }
}
