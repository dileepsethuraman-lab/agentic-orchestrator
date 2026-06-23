package com.telecom.orchestrator.pipeline;

/**
 * Functional interface for emitting trace steps into a job's trace list.
 * Analogous to the Python PoC's {@code step_fn} closure.
 */
@FunctionalInterface
public interface TraceStepEmitter {
    void emit(String stage, String status, String title, String detail, String color, String icon);
}
