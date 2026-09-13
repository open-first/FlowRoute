# Architecture and safety boundary

FlowRoute is a **selector**, not an agent executor. The central invariant is that a model output can
recommend entry into a workflow-specific validation path but cannot authorize a side effect.

## Online path

1. Validate the request and, in production, require the caller's catalog version and authorized
   workflow set.
2. Remove disabled, blocked, unauthorized, or disallowed-risk workflows.
3. Use an exact event mapping only when trusted-event routing was explicitly enabled.
4. Reject open-ended or multi-action requests that v1 does not support.
5. Retrieve the top `K` candidates using a positive capability representation.
6. Verify each request against its complete contract.
7. Check deterministic required-input completeness.
8. Apply calibrated route and margin thresholds for the candidate's risk tier.
9. Return `ROUTE`, `CLARIFY`, or `LLM_REQUIRED` with artifact lineage.
10. Let a separate orchestrator recheck authorization, inputs, current state, confirmation, and
    idempotency before execution.

## Trust boundaries

| Component | Trusted for | Not trusted for |
|---|---|---|
| Catalog registry | Candidate identity, version, declared policy | User authorization or live state |
| Retriever | Shortlisting plausible contracts | Final routing |
| Verifier | Semantic pair score | Permission, typed values, or execution |
| Calibration bundle | Versioned operating threshold | Guarantees under unmeasured distribution shift |
| FlowRoute service | A typed routing recommendation | Side effects |
| Workflow orchestrator | Final validation and execution policy | Reinterpreting the user's intent |

The production candidate filter must receive eligible workflow IDs from an authorization-aware
system. The demo API accepts `allowed_workflow_ids` to make this boundary visible; it does not
implement identity or access control itself.

## Decision rules

| Condition | Result |
|---|---|
| Unique trusted event mapping, required inputs present | `ROUTE` |
| Unique compatible workflow, required inputs missing | `CLARIFY` |
| No eligible candidates | `LLM_REQUIRED / NO_ELIGIBLE_WORKFLOW` |
| Retrieval below minimum | `LLM_REQUIRED / NO_WORKFLOW` |
| Top candidates too close | `LLM_REQUIRED / AMBIGUOUS_CANDIDATES` |
| Semantic score below tier threshold | `LLM_REQUIRED / BELOW_RISK_THRESHOLD` |
| Reasoning or multi-action request | `LLM_REQUIRED` with the policy reason |

## Why retrieval excludes negative fields

The first-stage retriever uses the name, description, positive capabilities, and examples. Putting
exclusions into that representation can make an excluded behavior look more similar to the
workflow. The verifier receives the full contract and is responsible for the finer boundary.

## Version lineage

Every response contains:

- model version (retriever plus verifier);
- calibration version;
- immutable catalog version; and
- request ID.

Production artifact manifests additionally bind the serializer version, model hashes, catalog
content hash, policy revision, prefixes, label order, top-K, and exact-event policy. Compatibility
is checked at startup and again before each production request. A mismatch causes a fail-closed
response, never silent reuse.

## Deployment responsibility

The package provides hardened runtime controls, artifact lineage, telemetry interfaces, and an
authorization integration point. A deployment still needs application authentication, executor
validation, rate limiting, TLS, immutable release storage, operational monitoring, and a trained
and calibrated model that passed the target-domain acceptance criteria. ANN indexing, persisted
embedding caches, and optimized exports are scale-dependent choices rather than correctness
requirements.
