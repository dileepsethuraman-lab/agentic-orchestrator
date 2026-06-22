# TMF Notification Event Schemas — Reference

> Source: TM Forum Open API specifications (TMF641 v4.1.0, TMF640 R18.5.0)
> Repository: https://github.com/tmforum-apis/TMF641_ServiceOrder

## 1. ServiceOrderStateChangeEvent

The canonical notification emitted when a TMF641 ServiceOrder transitions state.

### Schema (from TMF641 v4.1.0 swagger)

```json
{
  "eventId": "string (required) — unique identifier of this notification instance",
  "eventTime": "date-time (required) — ISO 8601 timestamp of event occurrence",
  "eventType": "string (required) — 'ServiceOrderStateChangeEvent'",
  "correlationId": "string — correlates related events across systems",
  "domain": "string — business domain (e.g., 'Telecom', 'ServiceFulfillment')",
  "title": "string — human-readable title",
  "description": "string — explanatory text",
  "priority": "string — event priority",
  "timeOcurred": "date-time — time the underlying event occurred",
  "event": {
    "serviceOrder": {
      "id": "string (required) — service order identifier",
      "href": "string — hyperlink to the order resource",
      "state": "ServiceOrderStateType — current order state",
      "externalId": "string — CRM/consumer-facing order reference",
      "category": "string — Broadband, TVOption, VPN, Mobile, etc.",
      "description": "string — free-text description",
      "orderDate": "date-time",
      "completionDate": "date-time",
      "expectedCompletionDate": "date-time",
      "priority": "string",
      "relatedParty": [{ "role": "string", "name": "string", "id": "string" }],
      "serviceOrderItem": [
        {
          "id": "string",
          "action": "add | modify | delete | noChange",
          "state": "ServiceOrderItemStateType",
          "service": { "id": "string", "href": "string", "state": "ServiceStateType" }
        }
      ],
      "milestone": [
        {
          "id": "string",
          "name": "string — milestone name",
          "description": "string",
          "message": "string",
          "milestoneDate": "date-time",
          "status": "string"
        }
      ]
    }
  }
}
```

### State Enumerations

**ServiceOrderStateType** (TMF641):
```
acknowledged | rejected | pending | held | inProgress |
cancelled | completed | failed | partial |
assessingCancellation | pendingCancellation
```

**ServiceOrderItemStateType** (TMF641):
```
acknowledged | rejected | pending | held | inProgress |
cancelled | completed | failed | partial |
assessingCancellation | pendingCancellation
```

**ServiceStateType** (TMF638):
```
feasibilityChecked | designed | reserved | inactive | active | terminated
```

## 2. ServiceOrderMilestone

Marks a significant stage in service order processing.

```json
{
  "id": "string — milestone identifier",
  "name": "string — e.g. 'HLR_PROVISIONED', 'IMS_REGISTERED'",
  "description": "string — free-text description",
  "message": "string — operational message",
  "milestoneDate": "date-time — when the milestone was reached",
  "status": "string — 'achieved' | 'pending' | 'failed'",
  "serviceOrderItem": [ { "id": "string", "href": "string" } ]
}
```

## 3. Notification Event Types Available (TMF641)

| Event Type | Trigger |
|------------|---------|
| `ServiceOrderCreateEvent` | New service order created |
| `ServiceOrderStateChangeEvent` | Order state transitioned |
| `ServiceOrderAttributeValueChangeEvent` | Order attribute changed |
| `ServiceOrderDeleteEvent` | Order deleted |
| `ServiceOrderInformationRequiredEvent` | More info needed from consumer |
| `ServiceOrderJeopardyEvent` | Order at risk of missing SLA |
| `ServiceOrderMilestoneEvent` | Milestone reached in processing |

## 4. Mapping: Orchestrator Lifecycle → TMF Events

The orchestrator's KB-defined lifecycle states map to TMF events as follows:

| KB Lifecycle State | TMF Event | ServiceOrder State |
|--------------------|-----------|-------------------|
| DESIGNED | ServiceOrderMilestoneEvent | inProgress, milestone=DESIGNED |
| FEASIBILITY_CHECKED | ServiceOrderMilestoneEvent | inProgress, milestone=FEASIBILITY_CHECKED |
| {NE}_PROVISIONED / REGISTERED / CONFIGURED | ServiceOrderMilestoneEvent | inProgress, milestone={state} |
| ACTIVE | ServiceOrderStateChangeEvent | completed |

### Pattern for milestone emissions during processing:
- Order state remains `inProgress` throughout provisioning
- Each lifecycle stage emits a milestone (not a full state change)
- Final ACTIVE stage emits ServiceOrderStateChangeEvent with state=completed
- All events share the same correlationId for traceability
