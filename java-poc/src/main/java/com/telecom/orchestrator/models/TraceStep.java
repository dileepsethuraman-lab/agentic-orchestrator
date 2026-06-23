package com.telecom.orchestrator.models;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class TraceStep {
    public String stage;
    public String status;
    public String title;
    public String detail;
    public String color;
    public String icon;
    public int elapsedMs;

    public TraceStep() {}

    public TraceStep(String stage, String status, String title, String detail,
                     String color, String icon, int elapsedMs) {
        this.stage = stage;
        this.status = status;
        this.title = title;
        this.detail = detail;
        this.color = color;
        this.icon = icon;
        this.elapsedMs = elapsedMs;
    }
}
