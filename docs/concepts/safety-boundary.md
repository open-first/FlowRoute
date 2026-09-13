# Safety boundary

FlowRoute is a selector, not an executor. A model output may recommend a workflow-specific
validation path; it cannot authorize a side effect.

## Trust matrix

| Component | Trusted for | Not trusted for |
| --- | --- | --- |
| Catalog registry | Candidate identity, version, declared policy | User authorization or live state |
| Retriever | Shortlisting plausible contracts | Final routing |
| Verifier | Semantic compatibility score | Permission, typed values, or execution |
| Calibration bundle | Versioned operating threshold | Guarantees under unmeasured distribution shift |
| FlowRoute service | Typed routing recommendation | Side effects |
| Workflow orchestrator | Final validation and execution policy | Reinterpreting the user's intent |

## Before FlowRoute

An authorization-aware system should determine which workflow IDs the caller may use:

```python
request = RouteRequest(
    text=user_text,
    context=trusted_context,
    allowed_workflow_ids=permission_service.eligible_workflows(user),
)
```

The demo API exposes `allowed_workflow_ids` to make this boundary explicit; it does not implement
identity or access control.

## After FlowRoute

For a `ROUTE` response, the orchestrator must:

1. load the exact current workflow contract;
2. verify the caller is still authorized;
3. validate typed input values;
4. check live preconditions;
5. enforce confirmation policy;
6. acquire or verify an idempotency key;
7. execute through the workflow's normal controls; and
8. record the outcome against the route request ID.

## Confirmation

`confirmation_required` is derived from the contract's declared confirmation policy. It tells the
caller that confirmation is needed; it does not prove confirmation occurred.

For example, a refund can return:

```json
{
  "decision": "ROUTE",
  "workflow_id": "billing.refund_payment",
  "confirmation_required": true
}
```

The billing workflow must still present or verify confirmation before issuing the refund.

## Artifact lineage

Every response includes model, calibration, and catalog versions. Production bundles should also
bind:

- serializer version;
- model content hash;
- catalog content hash;
- policy revision; and
- index-building configuration.

A mismatch should cause fallback or a controlled reload, not silent reuse.

## Threats to consider

- Prompt injection that tries to override the workflow catalog or policy.
- Unauthorized IDs inserted into client-supplied allowlists.
- PII copied into debug logs or training data.
- Stale embeddings paired with a newer contract catalog.
- Adversarial phrasing around destructive or high-risk workflows.
- Threshold drift after model, catalog, language, or traffic changes.
- Replay of write requests without idempotency controls.

FlowRoute reduces one decision surface. It does not replace application security.
