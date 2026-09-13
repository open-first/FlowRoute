# Production checklist

The package enforces the routing-side controls it can own. Complete these deployment- and
model-specific items before routing real side effects.

## Access and execution

- [ ] Generate `allowed_workflow_ids` from an authorization-aware service.
- [ ] Treat client-provided allowlists and context as untrusted unless verified.
- [ ] Recheck authorization immediately before execution.
- [ ] Validate all workflow arguments with the executor's typed schema.
- [ ] Check live preconditions rather than trusting catalog prose.
- [ ] Enforce confirmation for the current action and scope.
- [ ] Require idempotency keys for writes and destructive operations.
- [ ] Keep the router unable to call side-effecting tools directly.

## Artifacts and versioning

- [ ] Store immutable workflow catalog snapshots.
- [ ] Approve a complete artifact manifest for each deployed bundle.
- [ ] Verify local retriever and verifier directory hashes at startup.
- [ ] Bind embeddings to catalog, serializer, and model hashes.
- [ ] Pin model and tokenizer revisions.
- [ ] Version calibration thresholds independently.
- [ ] Reject incompatible artifact combinations.
- [ ] Keep a tested rollback bundle.

## Model readiness

- [ ] Replace TF-IDF and lexical defaults for the intended production claim.
- [ ] Freeze workflow-disjoint train, calibration, and hidden test splits.
- [ ] Define maximum false-route rates by risk tier.
- [ ] Fit thresholds only on the calibration split.
- [ ] Test exclusions, missing inputs, OOD, multi-action, and reasoning cases.
- [ ] Evaluate every deployed language, domain, and risk tier.
- [ ] Confirm quality after quantization or model export.

## Service reliability

- [ ] Precompute and persist workflow embeddings.
- [ ] Use an ANN index when catalog scale requires it.
- [ ] Test concurrent requests and memory pressure.
- [ ] Define timeouts and fail closed to `LLM_REQUIRED`.
- [ ] Add health and readiness checks for model and catalog state.
- [ ] Exercise corrupt catalog, stale version, and unavailable-model failures.

## Observability

Log at least:

- request ID;
- decision and reason code;
- selected workflow ID;
- confidence and top-candidate margin;
- model, calibration, and catalog versions;
- latency;
- risk tier;
- confirmation requirement; and
- downstream validation and execution outcome.

Avoid logging raw request text or context by default when it may contain personal, secret, or
regulated data.

Monitor:

- false-route rate from reviewed outcomes;
- route coverage;
- clarification precision;
- OOD recall from audit samples;
- score and margin distributions;
- reason-code distribution;
- latency and error rate; and
- changes by domain, language, catalog, and risk tier.

## Governance

- [ ] Audit dataset and base-model licenses.
- [ ] Document data retention and deletion.
- [ ] Review training text for personal or confidential data.
- [ ] Assign an owner to every workflow.
- [ ] Define incident response and route-disable procedures.
- [ ] Publish model and dataset cards with limitations.
- [ ] Record checkpoint hashes and reproducibility metadata.

## Rollout

Use staged deployment:

1. offline evaluation;
2. shadow mode with no workflow execution;
3. human-reviewed low-risk suggestions;
4. low-risk automatic routing with downstream validation;
5. measured expansion by workflow and risk tier.

Do not expand based on route volume alone. Require stable reviewed error rates and a working
rollback path.
