package com.telecom.orchestrator.store;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Instant;
import java.util.*;

/**
 * Persistent subscriber service models with runtime corruption detection.
 *
 * <p>Stores subscriber models as JSON blobs in an H2 table
 * ({@code subscriber_models}) via {@link JdbcTemplate}.  On every
 * {@link #get(String) load} the store inspects characteristics and
 * network-element attributes for corruption markers ({@code default_*}
 * keys, {@code <}… placeholder values) and either returns a clean model,
 * salvages a partially-corrupt one, or deletes a fully-corrupt entry to
 * force fresh provisioning.</p>
 */
public class ServiceModelStore {

    private static final Logger log = LoggerFactory.getLogger(ServiceModelStore.class);

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /** Minimum number of real (non-corrupt) network-element attributes
     *  required to consider a model salvageable. */
    static final int MIN_REAL_ATTRS = 3;

    private final JdbcTemplate jdbc;

    // ──────────────────────────────────────────────
    //  Constructor  –  ensures table exists
    // ──────────────────────────────────────────────

    public ServiceModelStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        initSchema();
    }

    private void initSchema() {
        jdbc.execute("""
                CREATE TABLE IF NOT EXISTS subscriber_models (
                    subscriber_id TEXT PRIMARY KEY,
                    data         TEXT NOT NULL
                )
                """);
    }

    // ──────────────────────────────────────────────
    //  Public API
    // ──────────────────────────────────────────────

    /**
     * Load and validate a stored subscriber model.
     *
     * <h3>Corruption detection</h3>
     * <ol>
     *   <li>If the DB row is absent → {@code null}.</li>
     *   <li>If the stored JSON is not a {@link Map} → delete row, return {@code null}.</li>
     *   <li>Count corruption markers (keys starting with {@code default_},
     *       values starting with {@code <}) in characteristics and every
     *       network element's attributes.</li>
     *   <li><b>total_corrupt == 0</b> → return clean model (fast path).</li>
     *   <li><b>Partially corrupt</b> (real NE attrs ≥ {@value #MIN_REAL_ATTRS}
     *       <em>and</em> not every characteristic is corrupt) → strip corrupt
     *       entries, log a warning, return salvaged model.</li>
     *   <li><b>Fully corrupt</b> → delete the row, return {@code null}
     *       (forces fresh provisioning).</li>
     * </ol>
     *
     * @param subscriberId subscriber identifier
     * @return the model map, a salvaged version of it, or {@code null}
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> get(String subscriberId) {
        List<String> rows = jdbc.query(
                "SELECT data FROM subscriber_models WHERE subscriber_id = ?",
                (rs, rowNum) -> rs.getString("data"),
                subscriberId);

        if (rows.isEmpty()) {
            return null;
        }

        String raw = rows.get(0);
        Map<String, Object> model;
        try {
            model = MAPPER.readValue(raw, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException e) {
            // Corrupt JSON – delete and force re-provision
            log.warn("Unparseable JSON for subscriber {} – deleting entry", subscriberId);
            delete(subscriberId);
            return null;
        }

        if (model == null) {
            delete(subscriberId);
            return null;
        }

        // ── Collect corruption stats ────────────────────

        Map<String, Object> characteristics = getMap(model, "characteristics");
        List<Map<String, Object>> networkElements = getListOfMaps(model, "network_elements");

        int corruptChars = countCorruptInMap(characteristics);
        int totalChars = characteristics != null ? characteristics.size() : 0;

        // Per-NE stats
        int totalCorruptNE = 0;
        int totalRealNE = 0;
        if (networkElements != null) {
            for (Map<String, Object> ne : networkElements) {
                int corrupt = countCorruptInMap(getMap(ne, "attributes"));
                int real = countRealInMap(getMap(ne, "attributes"));
                totalCorruptNE += corrupt;
                totalRealNE += real;
            }
        }

        int totalCorrupt = corruptChars + totalCorruptNE;

        // ── Fast path: clean ────────────────────────────
        if (totalCorrupt == 0) {
            return model;
        }

        // ── Determine salvageability ────────────────────
        boolean hasEnoughRealNE = totalRealNE >= MIN_REAL_ATTRS;
        boolean allCharsCorrupt = (totalChars > 0 && corruptChars == totalChars);

        if (hasEnoughRealNE && !allCharsCorrupt) {
            // Partially corrupt – strip and salvage
            log.warn("Subscriber {} model partially corrupt ({} markers) – stripping and salvaging",
                    subscriberId, totalCorrupt);

            Map<String, Object> salvaged = new LinkedHashMap<>(model);

            // Strip corrupt characteristics
            if (characteristics != null && corruptChars > 0) {
                Map<String, Object> cleanChars = stripCorrupt(characteristics);
                salvaged.put("characteristics", cleanChars);
            }

            // Strip corrupt NE attributes
            if (networkElements != null && totalCorruptNE > 0) {
                List<Map<String, Object>> cleanNEs = new ArrayList<>();
                for (Map<String, Object> ne : networkElements) {
                    Map<String, Object> cleanNE = new LinkedHashMap<>(ne);
                    Map<String, Object> attrs = getMap(ne, "attributes");
                    if (attrs != null) {
                        cleanNE.put("attributes", stripCorrupt(attrs));
                    }
                    cleanNEs.add(cleanNE);
                }
                salvaged.put("network_elements", cleanNEs);
            }

            return salvaged;
        }

        // Fully corrupt – delete and force fresh provisioning
        log.warn("Subscriber {} model fully corrupt ({} markers, {} real NE attrs) – deleting",
                subscriberId, totalCorrupt, totalRealNE);
        delete(subscriberId);
        return null;
    }

    /**
     * Persist (or update) a subscriber service model.
     *
     * <p>Bumps the {@code version} field and sets {@code last_updated}
     * to the current ISO-8601 timestamp before serialising to JSON.</p>
     *
     * @param subscriberId subscriber identifier
     * @param model        model map (mutated in-place: version and timestamp updated)
     */
    public void save(String subscriberId, Map<String, Object> model) {
        // Bump version
        Object verObj = model.get("version");
        int version = 1;
        if (verObj instanceof Number n) {
            version = n.intValue() + 1;
        }
        model.put("version", version);
        model.put("last_updated", Instant.now().toString());

        String json;
        try {
            json = MAPPER.writeValueAsString(model);
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to serialise model for subscriber " + subscriberId, e);
        }

        jdbc.update(
                "MERGE INTO subscriber_models (subscriber_id, data) VALUES (?, ?)",
                subscriberId, json);

        log.debug("Saved model for subscriber {} (version {})", subscriberId, version);
    }

    /**
     * Delete a subscriber's stored model.
     *
     * @param subscriberId subscriber identifier
     */
    public void delete(String subscriberId) {
        int rows = jdbc.update(
                "DELETE FROM subscriber_models WHERE subscriber_id = ?",
                subscriberId);
        if (rows > 0) {
            log.debug("Deleted model for subscriber {}", subscriberId);
        }
    }

    /**
     * Compute a diff between a previously-stored model and incoming
     * provisioning data.
     *
     * <h3>Network-element fuzzy matching</h3>
     * NE names are normalised by stripping trailing {@code /HSS}, {@code /PCF},
     * and {@code /MME} suffixes so that e.g. {@code "HLR/HSS"} in the previous
     * model matches {@code "HLR"} in the incoming list.
     *
     * @param previous           the previously-stored model (may be {@code null})
     * @param incomingChars      characteristics from the incoming request
     * @param newNetworkElements network elements from the incoming request
     * @return a diff map with keys:
     *         {@code hasPrevious}, {@code isFirstRun}, {@code hasChanges},
     *         {@code changedAttributes}, {@code networkElementDiffs}
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> computeDiff(
            Map<String, Object> previous,
            Map<String, Object> incomingChars,
            List<Map<String, Object>> newNetworkElements) {

        boolean hasPrevious = previous != null;
        boolean isFirstRun = !hasPrevious;

        Map<String, Object> changedAttributes = new LinkedHashMap<>();
        List<Map<String, Object>> networkElementDiffs = new ArrayList<>();

        if (!hasPrevious) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("hasPrevious", false);
            result.put("isFirstRun", true);
            result.put("hasChanges", true);
            result.put("changedAttributes", changedAttributes);
            result.put("networkElementDiffs", networkElementDiffs);
            return result;
        }

        Map<String, Object> prevChars = getMap(previous, "characteristics");
        List<Map<String, Object>> prevNEs = getListOfMaps(previous, "network_elements");

        // ── Compare characteristics ─────────────────────
        if (incomingChars == null) {
            incomingChars = Collections.emptyMap();
        }
        if (prevChars == null) {
            prevChars = Collections.emptyMap();
        }

        // Changed values (key exists in both, value differs)
        for (var entry : incomingChars.entrySet()) {
            String key = entry.getKey();
            Object newVal = entry.getValue();
            if (prevChars.containsKey(key)) {
                Object oldVal = prevChars.get(key);
                if (!Objects.equals(oldVal, newVal)) {
                    Map<String, Object> change = new LinkedHashMap<>();
                    change.put("key", key);
                    change.put("previous", oldVal);
                    change.put("incoming", newVal);
                    changedAttributes.put(key, change);
                }
            }
        }

        // Removed keys (in previous but not in incoming)
        for (String key : prevChars.keySet()) {
            if (!incomingChars.containsKey(key)) {
                Map<String, Object> removal = new LinkedHashMap<>();
                removal.put("key", key);
                removal.put("previous", prevChars.get(key));
                removal.put("incoming", null);
                removal.put("removed", true);
                changedAttributes.put(key, removal);
            }
        }

        // ── Compare network elements ────────────────────
        // Build a lookup from normalised name → previous NE
        Map<String, Map<String, Object>> prevNEMap = new LinkedHashMap<>();
        if (prevNEs != null) {
            for (Map<String, Object> ne : prevNEs) {
                String name = normalizeNEName(getString(ne, "name"));
                if (name != null) {
                    prevNEMap.put(name, ne);
                }
            }
        }

        if (newNetworkElements != null) {
            // Normalised incoming NE set (for detecting removed NEs)
            Set<String> incomingNENames = new HashSet<>();
            for (Map<String, Object> ne : newNetworkElements) {
                String rawName = getString(ne, "name");
                String normName = normalizeNEName(rawName);
                if (normName != null) {
                    incomingNENames.add(normName);
                }

                Map<String, Object> prevNE = normName != null ? prevNEMap.get(normName) : null;

                if (prevNE == null) {
                    // New NE
                    Map<String, Object> diff = new LinkedHashMap<>();
                    diff.put("name", rawName);
                    diff.put("normalized_name", normName);
                    diff.put("action", "added");
                    diff.put("incoming", ne);
                    networkElementDiffs.add(diff);
                } else {
                    // Compare attributes
                    Map<String, Object> prevAttrs = getMap(prevNE, "attributes");
                    Map<String, Object> newAttrs = getMap(ne, "attributes");

                    Map<String, Object> attrChanges = new LinkedHashMap<>();
                    if (prevAttrs == null) prevAttrs = Collections.emptyMap();
                    if (newAttrs == null) newAttrs = Collections.emptyMap();

                    for (var entry : newAttrs.entrySet()) {
                        String key = entry.getKey();
                        if (prevAttrs.containsKey(key)
                                && !Objects.equals(prevAttrs.get(key), entry.getValue())) {
                            Map<String, Object> change = new LinkedHashMap<>();
                            change.put("previous", prevAttrs.get(key));
                            change.put("incoming", entry.getValue());
                            attrChanges.put(key, change);
                        }
                    }
                    for (String key : prevAttrs.keySet()) {
                        if (!newAttrs.containsKey(key)) {
                            Map<String, Object> removal = new LinkedHashMap<>();
                            removal.put("previous", prevAttrs.get(key));
                            removal.put("incoming", null);
                            removal.put("removed", true);
                            attrChanges.put(key, removal);
                        }
                    }

                    if (!attrChanges.isEmpty()) {
                        Map<String, Object> diff = new LinkedHashMap<>();
                        diff.put("name", rawName);
                        diff.put("normalized_name", normName);
                        diff.put("action", "modified");
                        diff.put("attribute_changes", attrChanges);
                        networkElementDiffs.add(diff);
                    }
                }
            }

            // Detect removed NEs
            for (var entry : prevNEMap.entrySet()) {
                if (!incomingNENames.contains(entry.getKey())) {
                    Map<String, Object> diff = new LinkedHashMap<>();
                    diff.put("name", getString(entry.getValue(), "name"));
                    diff.put("normalized_name", entry.getKey());
                    diff.put("action", "removed");
                    diff.put("previous", entry.getValue());
                    networkElementDiffs.add(diff);
                }
            }
        } else if (prevNEs != null) {
            // No incoming NEs – all previous NEs removed
            for (Map<String, Object> ne : prevNEs) {
                Map<String, Object> diff = new LinkedHashMap<>();
                diff.put("name", getString(ne, "name"));
                diff.put("normalized_name", normalizeNEName(getString(ne, "name")));
                diff.put("action", "removed");
                diff.put("previous", ne);
                networkElementDiffs.add(diff);
            }
        }

        boolean hasChanges = !changedAttributes.isEmpty() || !networkElementDiffs.isEmpty();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("hasPrevious", true);
        result.put("isFirstRun", false);
        result.put("hasChanges", hasChanges);
        result.put("changedAttributes", changedAttributes);
        result.put("networkElementDiffs", networkElementDiffs);

        return result;
    }

    /**
     * Build a subscriber service model map from raw provisioning data.
     *
     * <p>Merges network-element attributes into characteristics, skipping
     * {@code status}, {@code default_*} keys, and {@code <}… placeholder
     * values.</p>
     *
     * @param subscriberId    subscriber identifier
     * @param svc             canonical service type
     * @param allChars        all characteristics from the provisioning request
     * @param networkElements list of network-element maps from the request
     * @param version         initial version number
     * @return a ready-to-persist model map
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> buildModel(
            String subscriberId,
            String svc,
            Map<String, Object> allChars,
            List<Map<String, Object>> networkElements,
            int version) {

        Map<String, Object> characteristics = new LinkedHashMap<>();

        // Start with allChars (skip null/empty)
        if (allChars != null) {
            for (var entry : allChars.entrySet()) {
                characteristics.put(entry.getKey(), entry.getValue());
            }
        }

        // Merge NE attributes into characteristics
        if (networkElements != null) {
            for (Map<String, Object> ne : networkElements) {
                Map<String, Object> attrs = getMap(ne, "attributes");
                if (attrs == null) {
                    continue;
                }
                for (var entry : attrs.entrySet()) {
                    String key = entry.getKey();
                    Object value = entry.getValue();

                    // Skip "status"
                    if ("status".equals(key)) {
                        continue;
                    }
                    // Skip default_* keys
                    if (key.startsWith("default_")) {
                        continue;
                    }
                    // Skip < placeholder values
                    if (value instanceof String s && s.startsWith("<")) {
                        continue;
                    }

                    characteristics.put(key, value);
                }
            }
        }

        Map<String, Object> model = new LinkedHashMap<>();
        model.put("subscriber_id", subscriberId);
        model.put("service_type", svc);
        model.put("characteristics", characteristics);
        model.put("network_elements", networkElements != null
                ? new ArrayList<>(networkElements) : new ArrayList<>());
        model.put("version", version);
        model.put("last_updated", Instant.now().toString());

        return model;
    }

    // ──────────────────────────────────────────────
    //  Corruption helpers
    // ──────────────────────────────────────────────

    /**
     * Count corruption markers in a flat characteristics/attributes map.
     *
     * <p>A key is corrupt if it starts with {@code default_}.
     * A value is corrupt if it is a {@link String} starting with {@code <}.</p>
     */
    static int countCorruptInMap(Map<String, Object> map) {
        if (map == null || map.isEmpty()) {
            return 0;
        }
        int count = 0;
        for (var entry : map.entrySet()) {
            if (entry.getKey().startsWith("default_")) {
                count++;
            }
            if (entry.getValue() instanceof String s && s.startsWith("<")) {
                count++;
            }
        }
        return count;
    }

    /**
     * Count real (non-corrupt) entries in a flat map.
     */
    static int countRealInMap(Map<String, Object> map) {
        if (map == null || map.isEmpty()) {
            return 0;
        }
        int count = 0;
        for (var entry : map.entrySet()) {
            boolean corruptKey = entry.getKey().startsWith("default_");
            boolean corruptVal = entry.getValue() instanceof String s && s.startsWith("<");
            if (!corruptKey && !corruptVal) {
                count++;
            }
        }
        return count;
    }

    /**
     * Return a new map with all corrupt entries (keys starting with
     * {@code default_} and values starting with {@code <}) removed.
     */
    static Map<String, Object> stripCorrupt(Map<String, Object> map) {
        Map<String, Object> clean = new LinkedHashMap<>();
        for (var entry : map.entrySet()) {
            if (entry.getKey().startsWith("default_")) {
                continue;
            }
            if (entry.getValue() instanceof String s && s.startsWith("<")) {
                continue;
            }
            clean.put(entry.getKey(), entry.getValue());
        }
        return clean;
    }

    // ──────────────────────────────────────────────
    //  Safe accessors
    // ──────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private static Map<String, Object> getMap(Map<String, Object> parent, String key) {
        if (parent == null) return null;
        Object val = parent.get(key);
        if (val instanceof Map) return (Map<String, Object>) val;
        return null;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> getListOfMaps(
            Map<String, Object> parent, String key) {
        if (parent == null) return null;
        Object val = parent.get(key);
        if (val instanceof List<?> list) {
            List<Map<String, Object>> result = new ArrayList<>();
            for (Object item : list) {
                if (item instanceof Map) {
                    result.add((Map<String, Object>) item);
                }
            }
            return result;
        }
        return null;
    }

    private static String getString(Map<String, Object> map, String key) {
        if (map == null) return null;
        Object val = map.get(key);
        return val != null ? val.toString() : null;
    }

    // ──────────────────────────────────────────────
    //  NE name normalisation
    // ──────────────────────────────────────────────

    /**
     * Normalise a network-element name for fuzzy matching by stripping
     * trailing {@code /HSS}, {@code /PCF}, and {@code /MME} suffixes.
     */
    static String normalizeNEName(String raw) {
        if (raw == null) return null;
        // Strip trailing suffixes used for variant disambiguation
        String name = raw;
        name = name.replaceAll("/HSS$", "");
        name = name.replaceAll("/PCF$", "");
        name = name.replaceAll("/MME$", "");
        return name;
    }
}
