# Workflow contracts

A workflow contract describes a capability boundary. It is configuration for selection and
safety—not executable code.

## Catalog shape

```yaml
catalog_version: commerce-2026-09-04
metadata:
  language: en
workflows:
  - id: orders.get_status
    version: 1.0.0
    name: Get order status
    description: Look up the current status of one customer order.
    positive_capabilities:
      - check where an order is
      - track an existing order
    exclusions:
      - cancel an order
      - refund a payment
    required_inputs:
      - name: order_id
        description: Unique order number.
        aliases: [order_number]
        pattern: '\border\s*[:#-]?\s*(?P<value>[A-Z0-9_-]+)\b'
    side_effect: read_only
    risk_tier: low
    confirmation: never
    examples:
      - Where is order 4812?
    owner: commerce-platform
```

## Contract fields

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Stable lowercase namespaced ID, 3–128 characters |
| `version` | Yes | Semantic version such as `1.0.0` |
| `name` | Yes | Human-readable capability name |
| `description` | Yes | Precise definition of one capability |
| `positive_capabilities` | No | Phrases used by first-stage retrieval |
| `exclusions` | Conditional | Confusing behaviors the workflow must not handle |
| `required_inputs` | No | Values required before a route can be executable |
| `optional_inputs` | No | Useful values that are not routing blockers |
| `preconditions` | No | Conditions the downstream orchestrator must check |
| `side_effect` | No | `read_only`, `internal_write`, `external_write`, or `destructive` |
| `risk_tier` | No | `low`, `medium`, `high`, or `critical` |
| `confirmation` | No | Downstream confirmation policy |
| `examples` | No | Representative positive requests |
| `event_types` | No | Trusted event types for exact routing |
| `owner` | No | Team responsible for the workflow |
| `status` | No | `active`, `disabled`, or `deprecated` |
| `metadata` | No | Additional application-owned metadata |

## Safety validation

Pydantic rejects:

- malformed workflow IDs and versions;
- duplicate input names;
- duplicate active workflow IDs;
- invalid extraction regexes; and
- an `external_write` or `destructive` workflow with no exclusions or with
  `confirmation: never`.

## Input resolution

For each required input, FlowRoute checks:

1. an exact key in trusted `context`;
2. a dotted path in trusted `context`;
3. each declared alias in trusted `context`; then
4. the optional text-extraction regex.

Context wins over text extraction. A regex with a named `value` group returns that group;
otherwise the entire match is returned.

```python
request = RouteRequest(
    text="Cancel tomorrow's review",
    context={"event_id": "evt_review_3pm"},
)
```

!!! tip "Prefer structured context"

    If your UI, API, or event bus already knows an order, payment, event, or user ID, pass that
    value in `context`. Do not ask a semantic model to reconstruct an authoritative identifier.

## Write strong contracts

### Keep capabilities atomic

Avoid `calendar.manage`. Use separate contracts such as:

- `calendar.create_event`;
- `calendar.cancel_event`; and
- `calendar.reschedule_event`.

### Include hard boundaries

For a cancellation contract, good exclusions include:

- decline an invitation without cancelling the event;
- delete an entire recurring series; and
- create or reschedule a meeting.

These are more useful than unrelated negatives because they define where mistakes are likely.

### Version semantic changes

Increment the workflow version when inputs, exclusions, side-effect class, risk tier, or capability
meaning changes. Increment `catalog_version` whenever the deployed snapshot changes.

### Use exact event rules carefully

`event_types` are appropriate only when the event is authenticated and maps to one active eligible
workflow. Exact-event routing is disabled by default in production. If two candidates declare the
same event, FlowRoute returns
`LLM_REQUIRED / AMBIGUOUS_EVENT_RULE`.

Even an exact event match must pass required-input resolution.
