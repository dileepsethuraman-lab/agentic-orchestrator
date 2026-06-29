package com.telecom.orchestrator.store;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * YAML DSL-based deterministic service orchestration engine.
 *
 * <p>Loads DSL definitions from {@code knowledge-base/dsl-definitions/}
 * and constructs orchestration plans by mapping request characteristics
 * onto DSL-defined network element templates.  Unlike the PatternStore,
 * this is a deterministic template engine — always HIT for known services.</p>
 *
 * <p>Mirrors {@code DSLEngine} in the Python PoC.</p>
 */
public class DSLStore {

    private static final Logger log = LoggerFactory.getLogger(DSLStore.class);

    private static final ObjectMapper YAML_MAPPER =
            new ObjectMapper(new YAMLFactory());

    /** Directory containing DSL YAML files. */
    private final Path dslDir;

    /** Service type → merged DSL definition. */
    private final Map<String, Map<String, Object>> definitions = new LinkedHashMap<>();

    /** Whether DSL files have been loaded. */
    private boolean loaded = false;

    public DSLStore() {
        this(Path.of("knowledge-base", "dsl-definitions"));
    }

    public DSLStore(Path dslDir) {
        this.dslDir = dslDir;
    }

    // ──────────────────────────────────────────────
    //  Loading
    // ──────────────────────────────────────────────

    /**
     * Load and index all DSL YAML files from the DSL directory.
     * Idempotent — subsequent calls are no-ops.
     *
     * @return the loaded definitions
     */
    @SuppressWarnings("unchecked")
    public Map<String, Map<String, Object>> load() {
        if (loaded) {
            return definitions;
        }

        Path indexFile = dslDir.resolve("dsl-index.yaml");
        if (!Files.exists(indexFile)) {
            log.error("DSL index not found: {}", indexFile);
            return definitions;
        }

        Map<String, Object> index;
        try {
            index = YAML_MAPPER.readValue(indexFile.toFile(), Map.class);
        } catch (Exception e) {
            log.error("Failed to load DSL index {}: {}", indexFile, e.getMessage());
            return definitions;
        }

        Map<String, Object> dslIndex =
                (Map<String, Object>) index.getOrDefault("dsl_index",
                        Collections.emptyMap());

        for (var entry : dslIndex.entrySet()) {
            String svc = entry.getKey();
            Map<String, Object> files =
                    (Map<String, Object>) entry.getValue();

            Map<String, Object> definition = new LinkedHashMap<>();
            definition.put("service_type", svc);
            definition.put("domain", files.getOrDefault("domain", ""));
            definition.put("network_elements", new ArrayList<Map<String, Object>>());

            // Load network elements
            String neFile = (String) files.get("network_elements");
            if (neFile != null) {
                Map<String, Object> neData =
                        loadYaml(dslDir.resolve(neFile));
                if (neData != null) {
                    List<Map<String, Object>> nes =
                            (List<Map<String, Object>>) neData.getOrDefault(
                                    "network_elements",
                                    neData.getOrDefault("networkElements",
                                            Collections.emptyList()));
                    List<Map<String, Object>> parsed = new ArrayList<>();
                    for (Map<String, Object> entry2 : nes) {
                        for (var neEntry : entry2.entrySet()) {
                            String name = neEntry.getKey();
                            Map<String, Object> spec =
                                    (Map<String, Object>) neEntry.getValue();

                            Map<String, Object> prefetch =
                                    (Map<String, Object>) spec.getOrDefault(
                                            "prefetch", Collections.emptyMap());
                            String workflow = (String) prefetch.getOrDefault(
                                    "workflow", name + "_Config");
                            // Strip path prefix: workflows/FOO.sw.yaml → FOO
                            int slash = workflow.lastIndexOf('/');
                            if (slash >= 0) {
                                workflow = workflow.substring(slash + 1);
                            }
                            if (workflow.endsWith(".sw.yaml")) {
                                workflow = workflow.substring(0, workflow.length() - 8);
                            } else if (workflow.endsWith(".yaml")) {
                                workflow = workflow.substring(0, workflow.length() - 5);
                            }

                            Map<String, Object> netChars =
                                    (Map<String, Object>) spec.getOrDefault(
                                            "networkCharacteristics",
                                            Collections.emptyMap());
                            List<String> attributes = new ArrayList<>();
                            for (String key : netChars.keySet()) {
                                if (!key.startsWith("_")) {
                                    attributes.add(key);
                                }
                            }

                            Map<String, Object> parsedNE = new LinkedHashMap<>();
                            parsedNE.put("name", name);
                            parsedNE.put("workflow", workflow);
                            parsedNE.put("id", spec.getOrDefault("id", name + "-01"));
                            parsedNE.put("state", spec.getOrDefault("state", "active"));
                            parsedNE.put("attributes", attributes);
                            parsedNE.put("conditions",
                                    spec.getOrDefault("_if_", Collections.emptyList()));
                            parsed.add(parsedNE);
                        }
                    }
                    definition.put("network_elements", parsed);
                }
            }

            definitions.put(svc, definition);
            List<Map<String, Object>> parsedNes =
                    (List<Map<String, Object>>) definition.get("network_elements");
            log.info("DSL: loaded {} → {} NEs", svc, parsedNes.size());
        }

        loaded = true;
        return definitions;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> loadYaml(Path path) {
        try {
            return YAML_MAPPER.readValue(path.toFile(), Map.class);
        } catch (Exception e) {
            log.error("DSL: failed to load {}: {}", path, e.getMessage());
            return null;
        }
    }

    // ──────────────────────────────────────────────
    //  Query
    // ──────────────────────────────────────────────

    /**
     * Build an orchestration plan from DSL definitions.
     *
     * @param serviceType     canonical service type (mobile, l3vpn, etc.)
     * @param characteristics request characteristics (may include instance attrs)
     * @return plan {@code {workflows, params, devices}}, or {@code null}
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> lookup(String serviceType,
                                       Map<String, Object> characteristics) {
        if (!loaded) {
            load();
        }

        Map<String, Object> dsl = definitions.get(serviceType);
        if (dsl == null) {
            return null;
        }

        List<Map<String, Object>> nes =
                (List<Map<String, Object>>) dsl.get("network_elements");
        if (nes == null || nes.isEmpty()) {
            return null;
        }

        List<String> devices = new ArrayList<>();
        List<String> workflows = new ArrayList<>();
        Map<String, Object> params = new LinkedHashMap<>();

        for (Map<String, Object> ne : nes) {
            String name = (String) ne.get("name");
            String workflow = (String) ne.get("workflow");
            List<String> neAttrs =
                    (List<String>) ne.getOrDefault("attributes", Collections.emptyList());

            // Evaluate conditions
            List<String> conditions =
                    (List<String>) ne.getOrDefault("conditions", Collections.emptyList());
            if (!conditions.isEmpty()) {
                if (!evalConditions(conditions, characteristics)) {
                    continue;
                }
            }

            devices.add(name);
            if (!workflows.contains(workflow)) {
                workflows.add(workflow);
            }

            // Resolve attributes from characteristics
            for (String attr : neAttrs) {
                if (params.containsKey(attr)) {
                    continue;
                }
                Object val = characteristics.get(attr);
                if (val != null) {
                    String sv = String.valueOf(val);
                    if (!sv.startsWith("default_") && !sv.startsWith("<")) {
                        params.put(attr, val);
                        continue;
                    }
                }
                params.put(attr, "<" + attr + ">");
            }
        }

        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("workflows", workflows);
        plan.put("params", params);
        plan.put("devices", devices);

        log.info("DSL: built plan for {} → {} NEs, {} wfs, {} params",
                serviceType, devices.size(), workflows.size(), params.size());
        return plan;
    }

    private boolean evalConditions(List<String> conditions,
                                    Map<String, Object> chars) {
        for (String cond : conditions) {
            if (cond.contains("==")) {
                String[] parts = cond.split("\\s*==\\s*");
                if (parts.length == 2) {
                    String expectedVal = parts[1].replaceAll("^['\"]|['\"]$", "");
                    // Extract attribute name from ~request.characteristic[ATTR].value
                    String attr = extractAttrFromExpr(parts[0]);
                    if (attr != null) {
                        String actual = String.valueOf(chars.getOrDefault(attr, ""));
                        if (!expectedVal.equals(actual)) {
                            return false;
                        }
                    }
                }
            }
        }
        return true;
    }

    private String extractAttrFromExpr(String expr) {
        // ~request.characteristic[ATTR].value
        int start = expr.indexOf('[');
        int end = expr.indexOf(']');
        if (start >= 0 && end > start) {
            return expr.substring(start + 1, end);
        }
        return null;
    }

    // ──────────────────────────────────────────────
    //  Inspection
    // ──────────────────────────────────────────────

    /** Return all loaded DSL definitions (shallow). */
    @SuppressWarnings("unchecked")
    public Map<String, Object> listAll() {
        if (!loaded) {
            load();
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (var entry : definitions.entrySet()) {
            Map<String, Object> dsl = entry.getValue();
            List<Map<String, Object>> nes =
                    (List<Map<String, Object>>) dsl.get("network_elements");
            Map<String, Object> info = new LinkedHashMap<>();
            info.put("domain", dsl.get("domain"));
            info.put("networkElementCount", nes != null ? nes.size() : 0);
            List<Map<String, Object>> neList = new ArrayList<>();
            if (nes != null) {
                for (Map<String, Object> ne : nes) {
                    neList.add(Map.of(
                            "name", ne.get("name"),
                            "workflow", ne.get("workflow")));
                }
            }
            info.put("networkElements", neList);
            result.put(entry.getKey(), info);
        }
        return Map.of("definitions", result);
    }

    /** Check whether DSL definitions have been loaded. */
    public boolean isLoaded() {
        return loaded;
    }

    /** Return the names of loaded service definitions. */
    public List<String> getServiceNames() {
        if (!loaded) {
            load();
        }
        return List.copyOf(definitions.keySet());
    }
}
