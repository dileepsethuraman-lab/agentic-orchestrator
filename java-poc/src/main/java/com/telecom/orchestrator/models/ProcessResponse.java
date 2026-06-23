package com.telecom.orchestrator.models;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProcessResponse {
    public String orderId;
    public String format;
    public String status;
    public List<TraceStep> trace = new ArrayList<>();
    public int totalMs;
    public Map<String, Object> finalState;
    public String startedAt;
}
