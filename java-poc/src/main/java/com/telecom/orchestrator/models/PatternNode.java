package com.telecom.orchestrator.models;

import java.util.*;

public class PatternNode {
    public String id;
    public String serviceType;
    public String label;
    public Map<String, Object> characteristics = new LinkedHashMap<>();
    public List<List<String>> triples = new ArrayList<>();
    public List<Map<String, Object>> resources = new ArrayList<>();
    public double confidence = 0.3;
    public int useCount = 0;
    public String createdAt;
    public String lastUsed;
    public String source = "auto";

    public Map<String, Object> toDict() {
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("id", id);
        d.put("service_type", serviceType);
        d.put("label", label);
        d.put("characteristics", characteristics);
        d.put("triples", triples);
        d.put("resources", resources);
        d.put("confidence", Math.round(confidence * 100.0) / 100.0);
        d.put("use_count", useCount);
        d.put("created_at", createdAt);
        d.put("last_used", lastUsed);
        d.put("source", source);
        return d;
    }
}
