# Quickstart

This walkthrough needs a catalog. The published package does not ship one, so fetch the demo
catalog from the tagged source:

```bash
curl -O https://raw.githubusercontent.com/open-first/FlowRoute/v0.2.0/examples/workflows.yaml
```

Working from a clone instead? Use `examples/workflows.yaml` in place of `workflows.yaml` below.

## Route from the CLI

```bash
flowroute route \
  --catalog workflows.yaml \
  --text "Where is order 4812?" \
  --debug
```

The important response fields look like this:

```json
{
  "decision": "ROUTE",
  "workflow_id": "orders.get_status",
  "reason_code": "ACCEPTED_LOW_RISK",
  "confirmation_required": false,
  "catalog_version": "demo-2026-09-04"
}
```

Scores and latency vary with the catalog, backend, hardware, and calibration bundle.

## Route from Python

```python
from flowroute import FlowRouter, RouteRequest, WorkflowRegistry

registry = WorkflowRegistry.from_yaml("workflows.yaml")
router = FlowRouter(registry)

result = router.route(
    RouteRequest(
        text="Cancel my design review tomorrow at 3 PM",
        context={"event_id": "evt_123"},
    )
)

print(result.decision)     # ROUTE
print(result.workflow_id)  # calendar.cancel_event
```

## Handle every outcome

```python
if result.decision == "ROUTE":
    # FlowRoute has selected a workflow, not authorized its side effect.
    begin_workflow_validation(result.workflow_id)
elif result.decision == "CLARIFY":
    ask_user_for(result.missing_inputs)
else:
    send_to_llm_or_human()
```

## Run the fixture evaluation

The fixture suite reads several files that ship only in the repository, so run it from a clone:

```bash
git clone https://github.com/open-first/FlowRoute.git
cd FlowRoute

flowroute evaluate \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --data examples/requests.jsonl \
  --fail-on-error
```

The included examples exercise routing, clarification, exact event rules, out-of-scope input,
reasoning fallback, multi-action fallback, near misses, and an empty authorization allowlist.
They are integration fixtures—not a research benchmark.

Next: define [workflow contracts](../guides/workflow-contracts.md).
