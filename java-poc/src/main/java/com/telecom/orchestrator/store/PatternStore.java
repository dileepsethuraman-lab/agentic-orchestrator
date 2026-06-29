package com.telecom.orchestrator.store;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.telecom.orchestrator.models.PatternNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;
import java.util.Locale;

/**
 * RDF-inspired pattern engine with Jaccard matching, learning,
 * reinforcement, and knowledge-base seeding.
 *
 * <p>Persists patterns as JSON blobs in an H2 database via
 * {@link JdbcTemplate}. Maintains a secondary index for fast
 * lookup by service type.</p>
 */
public class PatternStore {

    private static final Logger log = LoggerFactory.getLogger(PatternStore.class);

    private static final ObjectMapper MAPPER = new ObjectMapper();

    // ──────────────────────────────────────────────
    //  Instance attributes excluded from matching
    // ──────────────────────────────────────────────
    public static final Set<String> INSTANCE_ATTRS = Set.of(
            "msisdn", "imsi", "imei", "pe_ip",
            "hostname", "serviceid", "serial",
            "loopback", "management_ip", "text_hash"
    );

    private final JdbcTemplate jdbc;

    // ──────────────────────────────────────────────
    //  Constructor  –  ensures tables exist
    // ──────────────────────────────────────────────
    public PatternStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        initSchema();
    }

    private void initSchema() {
        jdbc.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id    TEXT PRIMARY KEY,
                    data  TEXT NOT NULL
                )
                """);
        jdbc.execute("""
                CREATE TABLE IF NOT EXISTS pattern_index (
                    svc_type  TEXT NOT NULL,
                    pid       TEXT NOT NULL,
                    PRIMARY KEY (svc_type, pid)
                )
                """);
    }

    // ──────────────────────────────────────────────
    //  Public API
    // ──────────────────────────────────────────────

    /**
     * Find the best-matching pattern for the given service type and
     * request characteristics.  Uses Jaccard similarity on
     * service-defining keys (excluding {@link #INSTANCE_ATTRS}).
     *
     * @return the best {@link PatternNode} or {@code null}
     */
    public PatternNode lookup(String serviceType,
                              Map<String, Object> characteristics) {
        List<String> pids = jdbc.queryForList(
                "SELECT pid FROM pattern_index WHERE svc_type = ?",
                String.class, serviceType.toLowerCase(Locale.ROOT));

        if (pids.isEmpty()) {
            return null;
        }

        // Derive service-defining request chars
        Map<String, Object> reqServiceChars = filterServiceChars(characteristics);

        PatternNode best = null;
        double bestScore = -1.0;

        for (String pid : pids) {
            PatternNode node = loadNode(pid);
            if (node == null) {
                continue; // purged during validation
            }
            Map<String, Object> patServiceChars = filterServiceChars(
                    node.characteristics);
            double score = matchScore(patServiceChars, reqServiceChars);
            if (score > bestScore) {
                bestScore = score;
                best = node;
            }
        }

        return best;
    }

    /**
     * Jaccard similarity between two characteristic maps.
     *
     * <ul>
     *   <li>Empty {@code patChars} → 0.25</li>
     *   <li>Empty {@code reqChars} → 1.0</li>
     * </ul>
     */
    public double matchScore(Map<String, Object> patChars,
                             Map<String, Object> reqChars) {
        return _matchScore(patChars, reqChars);
    }

    /**
     * Learn (or update) a pattern from observed characteristics and
     * an orchestration plan.  Derives service-defining characteristics
     * by stripping instance attributes, builds RDF triples from the
     * plan, and infers resources from the {@link KnowledgeBase}.
     *
     * @param serviceType     canonical service type
     * @param characteristics all characteristics (including instance attrs)
     * @param plan            orchestration plan ({@code workflows, params, devices, service})
     * @param allChars        reserved for future use
     * @param source          origin label (e.g. {@code "live"}, {@code "kb"})
     * @return the persisted {@link PatternNode}
     */
    public PatternNode learn(String serviceType,
                             Map<String, Object> characteristics,
                             Map<String, Object> plan,
                             Map<String, Object> allChars,
                             String source) {
        String svcType = serviceType.toLowerCase(Locale.ROOT);

        // Derive service-defining characteristics
        Map<String, Object> svcChars = filterServiceChars(characteristics);

        // Generate deterministic pid
        String pid = generatePid(svcType, svcChars);

        // Build RDF triples from plan
        List<List<String>> triples = buildTriplesFromPlan(svcType, plan);

        // Infer resources from KnowledgeBase
        List<Map<String, Object>> resources = inferResources(svcType);

        PatternNode node = new PatternNode();
        node.id = pid;
        node.serviceType = svcType;
        node.label = svcType + ":" + pid.substring(pid.lastIndexOf(':') + 1);
        node.characteristics = new LinkedHashMap<>(svcChars);
        node.triples = triples;
        node.resources = resources;
        node.confidence = 0.3;
        node.useCount = 1;
        node.source = source != null ? source : "auto";
        node.createdAt = Instant.now().toString();
        node.lastUsed = Instant.now().toString();

        saveNode(node);
        indexNode(svcType, pid);

        log.info("Learned pattern {} (confidence={}, triples={})",
                pid, node.confidence, triples.size());
        return node;
    }

    /**
     * Reinforce an existing pattern: increment use-count, boost
     * confidence, and update the last-used timestamp.
     */
    public PatternNode reinforce(PatternNode node) {
        node.useCount++;
        if (node.confidence < 0.9) {
            node.confidence = Math.min(node.confidence + 0.05, 0.95);
        } else {
            node.confidence = Math.min(node.confidence + 0.005, 0.98);
        }
        node.lastUsed = Instant.now().toString();
        saveNode(node);
        log.debug("Reinforced pattern {} → confidence={}, useCount={}",
                node.id, node.confidence, node.useCount);
        return node;
    }

    /**
     * Teach a pattern directly from a list of RDF triples.
     * Extracts the service type and characteristics from the triple
     * structure.
     */
    public PatternNode teach(List<List<String>> triples, String source) {
        String svcType = extractServiceType(triples);
        Map<String, Object> chars = extractCharacteristics(triples);

        String pid = generatePid(svcType, chars);

        List<Map<String, Object>> resources = inferResources(svcType);

        PatternNode node = new PatternNode();
        node.id = pid;
        node.serviceType = svcType;
        node.label = svcType + ":" + pid.substring(pid.lastIndexOf(':') + 1);
        node.characteristics = new LinkedHashMap<>(chars);
        node.triples = new ArrayList<>(triples);
        node.resources = resources;
        node.confidence = 0.9;
        node.useCount = 1;
        node.source = source != null ? source : "teach";
        node.createdAt = Instant.now().toString();
        node.lastUsed = Instant.now().toString();

        saveNode(node);
        indexNode(svcType, pid);

        log.info("Taught pattern {} (source={})", pid, source);
        return node;
    }

    /** Return all stored patterns as maps. */
    public List<Map<String, Object>> listAll() {
        List<String> ids = jdbc.queryForList(
                "SELECT id FROM patterns", String.class);
        List<Map<String, Object>> results = new ArrayList<>();
        for (String id : ids) {
            Map<String, Object> node = get(id);
            if (node != null) {
                results.add(node);
            }
        }
        return results;
    }

    /** Return a single pattern by id, or {@code null}. */
    public Map<String, Object> get(String pid) {
        PatternNode node = loadNode(pid);
        return node != null ? node.toDict() : null;
    }

    /**
     * Seed the pattern store from the {@link KnowledgeBase}.
     * For every service type defined in {@code SERVICE_RESOURCES},
     * builds a plan, calls {@link #learn} with empty characteristics
     * and source {@code "kb"}, then resets the confidence to 0.25.
     */
    public void seedFromKB() {
        int count = 0;
        for (var entry : KnowledgeBase.SERVICE_RESOURCES.entrySet()) {
            String svcType = entry.getKey();
            KnowledgeBase.ServiceResourceDef def = entry.getValue();

            // Build a plan from the KB definition
            Map<String, Object> plan = buildPlanFromKB(svcType, def);

            // Learn with empty characteristics
            PatternNode node = learn(svcType,
                    Collections.emptyMap(),
                    plan,
                    Collections.emptyMap(),
                    "kb");

            // KB-seeded templates serve as device/attribute lookups, NOT cache hits
            if (node != null) {
                node.confidence = 0.0;
                saveNode(node);
                log.info("KB seed template: {} (svc={}, {} NEs) — confidence=0, MISS on lookup",
                        node.id, node.serviceType, node.resources != null ? node.resources.size() : 0);
                count++;
            }
        }
        log.info("seedFromKB: seeded {} patterns", count);
    }

    // ──────────────────────────────────────────────
    //  Internal helpers
    // ──────────────────────────────────────────────

    /** Exclude {@link #INSTANCE_ATTRS} from the given map. */
    private Map<String, Object> filterServiceChars(
            Map<String, Object> chars) {
        if (chars == null || chars.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<String, Object> filtered = new LinkedHashMap<>();
        for (var entry : chars.entrySet()) {
            if (!INSTANCE_ATTRS.contains(entry.getKey().toLowerCase(Locale.ROOT))) {
                filtered.put(entry.getKey(), entry.getValue());
            }
        }
        return filtered;
    }

    /**
     * Jaccard similarity: |intersection| / |union|.
     *
     * <ul>
     *   <li>Empty {@code patChars} → 0.25</li>
     *   <li>Empty {@code reqChars} → 1.0</li>
     * </ul>
     */
    private double _matchScore(Map<String, Object> patChars,
                               Map<String, Object> reqChars) {
        Set<String> patKeys = patChars != null
                ? patChars.keySet().stream()
                    .filter(k -> !INSTANCE_ATTRS.contains(k.toLowerCase(Locale.ROOT)))
                    .collect(Collectors.toSet())
                : Collections.emptySet();
        Set<String> reqKeys = reqChars != null
                ? reqChars.keySet().stream()
                    .filter(k -> !INSTANCE_ATTRS.contains(k.toLowerCase(Locale.ROOT)))
                    .collect(Collectors.toSet())
                : Collections.emptySet();

        // Edge cases per spec
        if (patKeys.isEmpty()) {
            return 0.0;  // KB-seeded wildcard — device template, NOT a cache hit
        }
        if (reqKeys.isEmpty()) {
            return 1.0;
        }

        Set<String> intersection = new HashSet<>(patKeys);
        intersection.retainAll(reqKeys);

        Set<String> union = new HashSet<>(patKeys);
        union.addAll(reqKeys);

        if (union.isEmpty()) {
            return 0.0;  // both empty — no service-defining chars
        }

        return (double) intersection.size() / (double) union.size();
    }

    /** Generate a deterministic pattern id from service type and chars. */
    private String generatePid(String svcType,
                               Map<String, Object> chars) {
        // Sort keys for determinism
        Map<String, Object> sorted = new TreeMap<>(chars != null ? chars
                : Collections.emptyMap());
        String json;
        try {
            json = MAPPER.writeValueAsString(sorted);
        } catch (JsonProcessingException e) {
            json = sorted.toString();
        }
        String hash = sha256(json).substring(0, 12);
        return "pat:" + svcType + ":" + hash;
    }

    /** SHA-256 hex digest. */
    private String sha256(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-256 not available", e);
        }
    }

    // ──────────────────────────────────────────────
    //  Triple building
    // ──────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private List<List<String>> buildTriplesFromPlan(
            String svcType, Map<String, Object> plan) {
        List<List<String>> triples = new ArrayList<>();

        if (plan == null) {
            return triples;
        }

        // Workflow steps
        Object workflowsObj = plan.get("workflows");
        if (workflowsObj instanceof List<?> wfs) {
            for (Object wf : wfs) {
                triples.add(List.of(svcType,
                        "rdf:workflow", String.valueOf(wf)));
            }
        }

        // Devices
        Object devicesObj = plan.get("devices");
        if (devicesObj instanceof List<?> devs) {
            for (Object dev : devs) {
                String devName = String.valueOf(dev);
                triples.add(List.of(devName,
                        "rdf:deployedIn", svcType));
            }
        }

        // Params — structured as Map<deviceName, Map<key, value>>
        Object paramsObj = plan.get("params");
        if (paramsObj instanceof Map<?, ?> params) {
            for (var entry : ((Map<String, ?>) params).entrySet()) {
                String devName = entry.getKey();
                Object paramMap = entry.getValue();
                if (paramMap instanceof Map<?, ?> pm) {
                    for (var pEntry : ((Map<String, ?>) pm).entrySet()) {
                        triples.add(List.of(devName,
                                "rdf:param:" + pEntry.getKey(),
                                String.valueOf(pEntry.getValue())));
                    }
                }
            }
        }

        return triples;
    }

    // ──────────────────────────────────────────────
    //  Knowledge-base resource inference
    // ──────────────────────────────────────────────

    private List<Map<String, Object>> inferResources(String svcType) {
        List<Map<String, Object>> resources = new ArrayList<>();
        KnowledgeBase.ServiceResourceDef def =
                KnowledgeBase.SERVICE_RESOURCES.get(svcType);
        if (def == null) {
            return resources;
        }

        for (KnowledgeBase.ResourceDef rd : def.requiredResources()) {
            Map<String, Object> res = new LinkedHashMap<>();
            res.put("type", rd.type());
            res.put("role", rd.role());
            res.put("attributes", rd.attributes());
            resources.add(res);
        }
        return resources;
    }

    /** Build a plan map from a KB {@link KnowledgeBase.ServiceResourceDef}. */
    private Map<String, Object> buildPlanFromKB(
            String svcType,
            KnowledgeBase.ServiceResourceDef def) {
        Map<String, Object> plan = new LinkedHashMap<>();

        // Workflows from lifecycle string
        List<String> workflows = new ArrayList<>();
        if (def.lifecycle() != null) {
            for (String step : def.lifecycle().split("→")) {
                workflows.add(step.trim());
            }
        }
        plan.put("workflows", workflows);

        // Devices
        List<String> devices = new ArrayList<>();
        Map<String, Map<String, Object>> params = new LinkedHashMap<>();
        for (KnowledgeBase.ResourceDef rd : def.requiredResources()) {
            devices.add(rd.type());
            Map<String, Object> attrMap = new LinkedHashMap<>();
            for (String attr : rd.attributes()) {
                if (!INSTANCE_ATTRS.contains(attr.toLowerCase(Locale.ROOT))) {
                    attrMap.put(attr, "default_" + attr);
                }
            }
            if (!attrMap.isEmpty()) {
                params.put(rd.type(), attrMap);
            }
        }
        plan.put("devices", devices);
        plan.put("params", params);
        plan.put("service", svcType);

        return plan;
    }

    /** Extract the canonical service type from a list of triples. */
    private String extractServiceType(List<List<String>> triples) {
        // Strategy: find the subject of the first "rdf:workflow" triple,
        // or the first subject overall.
        for (List<String> triple : triples) {
            if (triple.size() >= 3
                    && "rdf:workflow".equals(triple.get(1))) {
                return triple.get(0).toLowerCase(Locale.ROOT);
            }
        }
        // Fallback: use the first triple's subject
        if (!triples.isEmpty() && !triples.get(0).isEmpty()) {
            return triples.get(0).get(0).toLowerCase(Locale.ROOT);
        }
        return "unknown";
    }

    /** Extract characteristics from triples (param predicates). */
    private Map<String, Object> extractCharacteristics(
            List<List<String>> triples) {
        Map<String, Object> chars = new LinkedHashMap<>();
        for (List<String> triple : triples) {
            if (triple.size() >= 3) {
                String predicate = triple.get(1);
                if (predicate != null
                        && predicate.startsWith("rdf:param:")) {
                    String key = predicate.substring("rdf:param:".length());
                    chars.put(key, triple.get(2));
                }
            }
        }
        return chars;
    }

    // ──────────────────────────────────────────────
    //  Persistence
    // ──────────────────────────────────────────────

    private void saveNode(PatternNode node) {
        String json;
        try {
            json = MAPPER.writeValueAsString(nodeToMap(node));
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize pattern {}: {}", node.id,
                    e.getMessage());
            return;
        }
        jdbc.update(
                "MERGE INTO patterns (id, data) VALUES (?, ?)",
                node.id, json);
    }

    private void indexNode(String svcType, String pid) {
        jdbc.update(
                "MERGE INTO pattern_index (svc_type, pid) VALUES (?, ?)",
                svcType, pid);
    }

    /**
     * Load a node with runtime validation.
     * Rejects patterns with null/empty resources, fewer than 3 triples,
     * or deserialization errors.  Logs warnings for {@code default_*}
     * contamination.
     *
     * @return the validated {@link PatternNode}, or {@code null} if
     *         the pattern was purged
     */
    @SuppressWarnings("unchecked")
    private PatternNode loadNode(String pid) {
        List<String> rows = jdbc.queryForList(
                "SELECT data FROM patterns WHERE id = ?",
                String.class, pid);

        if (rows.isEmpty()) {
            // Stale index entry — clean up
            jdbc.update("DELETE FROM pattern_index WHERE pid = ?", pid);
            return null;
        }

        String json = rows.get(0);
        Map<String, Object> raw;
        try {
            raw = MAPPER.readValue(json, Map.class);
        } catch (JsonProcessingException e) {
            log.warn("Deserialization error for pattern {} – deleting", pid);
            jdbc.update("DELETE FROM patterns WHERE id = ?", pid);
            jdbc.update("DELETE FROM pattern_index WHERE pid = ?", pid);
            return null;
        }

        // ── Validation ──────────────────────────
        List<Map<String, Object>> resources =
                (List<Map<String, Object>>) raw.get("resources");
        if (resources == null) {
            log.warn("Pattern {} has null resources – deleting", pid);
            purge(pid);
            return null;
        }
        if (resources.isEmpty()) {
            log.warn("Pattern {} has empty resources – deleting", pid);
            purge(pid);
            return null;
        }

        List<List<String>> triples =
                (List<List<String>>) raw.get("triples");
        if (triples == null || triples.size() < 3) {
            log.warn("Pattern {} has <3 triples – deleting", pid);
            purge(pid);
            return null;
        }

        // ── default_* contamination check ───────
        checkDefaultContamination(pid,
                (Map<String, Object>) raw.get("characteristics"));

        // ── Assemble node ───────────────────────
        PatternNode node = new PatternNode();
        node.id = (String) raw.get("id");
        node.serviceType = (String) raw.get("service_type");
        node.label = (String) raw.get("label");
        node.characteristics = raw.containsKey("characteristics")
                ? new LinkedHashMap<>((Map<String, Object>)
                        raw.get("characteristics"))
                : new LinkedHashMap<>();
        node.triples = triples;
        node.resources = resources;
        node.confidence = raw.containsKey("confidence")
                ? ((Number) raw.get("confidence")).doubleValue() : 0.3;
        node.useCount = raw.containsKey("use_count")
                ? ((Number) raw.get("use_count")).intValue() : 1;
        node.createdAt = (String) raw.get("created_at");
        node.lastUsed = (String) raw.get("last_used");
        node.source = (String) raw.getOrDefault("source", "auto");

        return node;
    }

    private void purge(String pid) {
        jdbc.update("DELETE FROM patterns WHERE id = ?", pid);
        jdbc.update("DELETE FROM pattern_index WHERE pid = ?", pid);
    }

    private void checkDefaultContamination(String pid,
                                           Map<String, Object> chars) {
        if (chars == null) return;
        for (var entry : chars.entrySet()) {
            Object val = entry.getValue();
            if (val instanceof String s && s.startsWith("default_")) {
                log.warn("Pattern {} contains default_* value: {}={}",
                        pid, entry.getKey(), s);
            }
        }
    }

    /** Convert a PatternNode to a serializable map. */
    private Map<String, Object> nodeToMap(PatternNode node) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("id", node.id);
        map.put("service_type", node.serviceType);
        map.put("label", node.label);
        map.put("characteristics", node.characteristics);
        map.put("triples", node.triples);
        map.put("resources", node.resources);
        map.put("confidence", node.confidence);
        map.put("use_count", node.useCount);
        map.put("created_at", node.createdAt);
        map.put("last_used", node.lastUsed);
        map.put("source", node.source);
        return map;
    }
}
