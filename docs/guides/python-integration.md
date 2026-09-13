# Python integration

## Create a router

```python
from flowroute import FlowRouter, WorkflowRegistry

registry = WorkflowRegistry.from_yaml("examples/workflows.yaml")
router = FlowRouter(registry, top_k=8)
```

`FlowRouter` accepts these constructor arguments:

| Argument | Default | Responsibility |
| --- | --- | --- |
| `registry` | Required | Validated, versioned workflow snapshot |
| `retriever` | `TfidfRetriever` | Rank likely workflows |
| `verifier` | `LexicalVerifier` | Score each request–contract pair |
| `calibration` | Built-in baseline | Convert scores and risk to a decision |
| `policy` | `RoutingPolicy` | Eligibility filters and deterministic guards |
| `runtime_config` | Development mode | Enforce development, shadow, or production invariants |
| `artifact_manifest` | `None` | Bind approved production artifact identities |
| `telemetry` | Mode-specific sink | Record privacy-conscious routing outcomes |
| `top_k` | `8` | Number of candidates passed to verification; 1–64 |

## Build a request

```python
from flowroute import RouteRequest

request = RouteRequest(
    request_id="req_checkout_901",
    text="Refund payment pay_90210",
    context={"payment_id": "pay_90210"},
    catalog_version="demo-2026-09-04",
    allowed_workflow_ids=["billing.refund_payment"],
    blocked_workflow_ids=[],
    debug=False,
)

response = router.route(request)
```

### Authorization allowlist

`allowed_workflow_ids` has intentional three-state behavior:

| Value | Meaning |
| --- | --- |
| Field omitted or `None` | All otherwise eligible workflows may be considered |
| Non-empty list | Only listed eligible workflows may be considered |
| Empty list `[]` | No workflow is allowed; returns `NO_ELIGIBLE_WORKFLOW` |

Generate the list in an authorization-aware component. FlowRoute does not authenticate the caller.

## Handle the response

```python
from flowroute import Decision

match response.decision:
    case Decision.ROUTE:
        orchestrator.validate_and_execute(
            workflow_id=response.workflow_id,
            request_id=response.request_id,
            confirmation_required=response.confirmation_required,
        )
    case Decision.CLARIFY:
        ui.ask_for(response.missing_inputs)
    case Decision.LLM_REQUIRED:
        fallback.handle(
            text=request.text,
            reason_code=response.reason_code,
        )
```

The orchestrator must independently recheck:

- the user or service identity;
- permission for the chosen workflow;
- the current catalog and contract version;
- typed arguments;
- live preconditions;
- confirmation policy; and
- idempotency before any write.

## Restrict risk tiers

```python
from flowroute import FlowRouter, RiskTier, RoutingPolicy

policy = RoutingPolicy(
    allowed_risk_tiers={RiskTier.LOW, RiskTier.MEDIUM},
    reject_reasoning_requests=True,
    reject_multi_action_requests=True,
)

router = FlowRouter(registry, policy=policy)
```

## Use a calibration file

```python
from flowroute import CalibrationConfig, FlowRouter

calibration = CalibrationConfig.from_yaml("configs/calibration.yaml")
router = FlowRouter(registry, calibration=calibration)
```

## Debug candidates

Set `debug=True` only in trusted development or diagnostic contexts. The response then includes
the ranked candidates, component scores, verifier labels, missing inputs, and internal reason
codes.

Avoid returning debug data to untrusted clients without reviewing whether catalog details should
be exposed.
