package com.telecom.orchestrator.notification;

import com.telecom.orchestrator.pipeline.TraceStepEmitter;
import com.telecom.orchestrator.store.KnowledgeBase;
import com.telecom.orchestrator.store.KnowledgeBase.ServiceResourceDef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.*;

public class LifecycleNotifier {
    private static final Logger log = LoggerFactory.getLogger(LifecycleNotifier.class);

    public static final String ORDER_IN_PROGRESS = "inProgress";
    public static final String ORDER_COMPLETED = "completed";

    private final List<Map<String, Object>> notifications = new ArrayList<>();

    public List<String> parseLifecycle(String svc) {
        ServiceResourceDef sr = KnowledgeBase.get(svc);
        String lc = sr.lifecycle();
        return Arrays.stream(lc.split("→"))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .toList();
    }

    private Map<String, Object> baseEvent(String eventType, String orderId, String correlationId) {
        String now = Instant.now().toString();
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventId", "evt-" + orderId + "-" + eventType.replace("Event", ""));
        event.put("eventTime", now);
        event.put("eventType", eventType);
        event.put("correlationId", correlationId);
        event.put("domain", "ServiceFulfillment");
        event.put("priority", "normal");
        event.put("timeOcurred", now);
        return event;
    }

    public Map<String, Object> emitMilestone(String state, String svc, String orderId,
                                              String correlationId, String description) {
        String now = Instant.now().toString();
        Map<String, Object> event = baseEvent("ServiceOrderMilestoneEvent", orderId, correlationId);
        event.put("title", "Milestone: " + state);
        event.put("description", description != null ? description : "Service order reached milestone: " + state);

        Map<String, Object> so = new LinkedHashMap<>();
        so.put("id", orderId);
        so.put("href", "/api/tmf641/serviceOrder/" + orderId);
        so.put("state", ORDER_IN_PROGRESS);
        so.put("externalId", orderId);
        so.put("category", svc);

        Map<String, Object> milestone = new LinkedHashMap<>();
        milestone.put("id", "ms-" + orderId + "-" + state);
        milestone.put("name", state);
        milestone.put("description", description != null ? description : "State transition: " + state);
        milestone.put("message", "Orchestrator reached lifecycle state: " + state);
        milestone.put("milestoneDate", now);
        milestone.put("status", "achieved");
        so.put("milestone", List.of(milestone));

        Map<String, Object> eventBody = new LinkedHashMap<>();
        eventBody.put("serviceOrder", so);
        event.put("event", eventBody);

        notifications.add(event);
        return event;
    }

    public Map<String, Object> emitStateChange(String toState, String svc, String orderId,
                                                String correlationId, String description) {
        String now = Instant.now().toString();
        Map<String, Object> event = baseEvent("ServiceOrderStateChangeEvent", orderId, correlationId);
        event.put("title", "Order " + toState);
        event.put("description", description != null ? description : "Service order state changed to: " + toState);

        Map<String, Object> so = new LinkedHashMap<>();
        so.put("id", orderId);
        so.put("href", "/api/tmf641/serviceOrder/" + orderId);
        so.put("state", toState);
        so.put("externalId", orderId);
        so.put("category", svc);
        if (ORDER_COMPLETED.equals(toState)) {
            so.put("completionDate", now);
        }

        Map<String, Object> eventBody = new LinkedHashMap<>();
        eventBody.put("serviceOrder", so);
        event.put("event", eventBody);

        notifications.add(event);
        return event;
    }

    public List<Map<String, Object>> flush() {
        List<Map<String, Object>> result = new ArrayList<>(notifications);
        notifications.clear();
        return result;
    }

    /**
     * Build TMF notification events and emit individual trace steps for
     * each lifecycle state.  Accepts a {@link TraceStepEmitter} callback so
     * the pipeline can record each notification as a separate trace step
     * (matching the Python PoC's 6 separate NOTIFY steps).
     *
     * @param orderId      the order identifier
     * @param svc          service type (mobile, l3vpn, sdwan, broadband)
     * @param subscriberId subscriber identifier
     * @param step         callback to emit a trace step
     * @param elapsedMs    base elapsed ms for the step timestamp
     * @return number of notification events emitted
     */
    public int buildNotificationTrace(String orderId, String svc, String subscriberId,
                                       TraceStepEmitter step, int elapsedMs) {
        List<String> states = parseLifecycle(svc);
        String correlationId = "corr-" + orderId;
        int count = 0;

        for (int i = 0; i < states.size(); i++) {
            String state = states.get(i);
            boolean isFinal = (i == states.size() - 1);

            if (isFinal) {
                emitStateChange(ORDER_COMPLETED, svc, orderId, correlationId,
                        "Service provisioning complete. Final state: " + state);

                // Emit individual trace step for the final state change
                step.emit("NOTIFY", "done",
                    "TMF Notification — StateChange → completed",
                    "Goal: Notify TMF641 listener of order completion.\n"
                        + "Input: Final lifecycle state = " + state + "\n"
                        + "Expected: ServiceOrderStateChangeEvent with state=completed.\n"
                        + "Actual: StateChange event emitted; completionDate set.\n"
                        + "Output: TMF641 event delivered to notification channel.",
                    "cyan", "📬");
            } else {
                emitMilestone(state, svc, orderId, correlationId,
                        "Orchestrator provisioning: " + state);

                // Emit individual trace step for each milestone
                step.emit("NOTIFY", "done",
                    "TMF Notification — Milestone: " + state,
                    "Goal: Emit TMF641 milestone event for lifecycle state.\n"
                        + "Input: Lifecycle state = " + state + "\n"
                        + "Expected: ServiceOrderMilestoneEvent with status=achieved.\n"
                        + "Actual: Milestone event emitted for \"" + state + "\".\n"
                        + "Output: TMF641 milestone delivered to notification channel.",
                    "cyan", "📬");
            }
            count++;
        }
        return count;
    }
}
