package com.telecom.orchestrator.models;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProcessRequest {
    @NotBlank(message = "prompt must not be empty")
    public String prompt;
}
