# Configuration reference

## Calibration file

```yaml
version: demo-baseline-2026-09-04
temperature: 1.0
clarify_threshold: 0.55
min_retrieval_score: 0.08
tiers:
  low:
    route: 0.55
    margin: 0.08
  medium:
    route: 0.65
    margin: 0.12
  high:
    route: 0.76
    margin: 0.18
  critical:
    route: 0.90
    margin: 0.25
```

These are demonstrative baseline values, not production recommendations.

| Field | Type | Constraint | Meaning |
| --- | --- | --- | --- |
| `version` | string | Required | Immutable calibration bundle identity |
| `temperature` | float | Greater than 0 | Temperature scaling applied in logit space |
| `clarify_threshold` | float | 0–1 | Minimum confidence for a `CLARIFY` decision |
| `min_retrieval_score` | float | 0–1 | Minimum first-stage candidate score |
| `tiers.*.route` | float | 0–1 | Minimum route confidence for that risk tier |
| `tiers.*.margin` | float | 0–1 | Minimum gap over the second candidate |

All four risk tiers must be present. Route thresholds must not decrease from low through critical.

## Routing policy

```python
from flowroute import RiskTier, RoutingPolicy

policy = RoutingPolicy(
    allowed_risk_tiers={
        RiskTier.LOW,
        RiskTier.MEDIUM,
        RiskTier.HIGH,
        RiskTier.CRITICAL,
    },
    reject_reasoning_requests=True,
    reject_multi_action_requests=True,
)
```

| Field | Default | Meaning |
| --- | --- | --- |
| `allowed_risk_tiers` | All tiers | Global risk eligibility |
| `reject_reasoning_requests` | `True` | Abstain on common analysis, advice, and planning language |
| `reject_multi_action_requests` | `True` | Abstain when multiple actions are detected |

## Router

```python
router = FlowRouter(
    registry,
    retriever=my_retriever,
    verifier=my_verifier,
    calibration=my_calibration,
    policy=my_policy,
    top_k=8,
)
```

`top_k` must be between 1 and 64.

## Runtime modes

```python
from flowroute import RouterRuntimeConfig

runtime = RouterRuntimeConfig.production(
    max_context_bytes=64 * 1024,
    allow_exact_event_routes=False,
)
```

| Field | Production value | Meaning |
| --- | --- | --- |
| `require_catalog_version` | `True` | Reject requests without active catalog lineage |
| `require_workflow_allowlist` | `True` | Require an authorization-derived candidate set |
| `allow_exact_event_routes` | `False` by default | Do not trust caller-supplied event types as routing authority |
| `allow_debug` | `False` | Do not expose candidate-level scores |
| `fail_closed_on_backend_error` | `True` | Convert model errors to a typed abstention |
| `max_context_bytes` | `65536` | Bound the serialized context size |

Set `allow_exact_event_routes=True` only for an authenticated structured-event entrypoint. The
setting is bound into the production artifact manifest.

## HTTP settings

```python
from flowroute.api import ApiSettings

settings = ApiSettings.production_defaults(
    trusted_hosts=["router.example.internal"],
    cors_origins=["https://console.example.com"],
    max_body_bytes=128 * 1024,
)
```

Production settings require an authorization callback, disable interactive API docs, reject
wildcard hosts and origins, and validate host/origin syntax. TLS, authentication, global request
deadlines, and distributed rate limiting remain at the ingress or service-mesh boundary.

## Catalog limits

The typed schema supports:

- up to 50,000 workflows per snapshot;
- up to 30 positive capabilities, exclusions, inputs, preconditions, or event types per workflow;
- up to 50 examples per workflow; and
- contract descriptions up to 2,000 characters.

Schema capacity is not the same as tested performance. The lexical baseline prepares its TF-IDF
index once, but it is still not appropriate for a large production catalog. Precompute learned
embeddings and use indexed retrieval for scale.
