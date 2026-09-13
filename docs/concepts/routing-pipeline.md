# Routing pipeline

The online path is intentionally layered so deterministic checks can reject unsafe candidates
before or after model scoring.

## End-to-end sequence

| Step | Code | What happens |
| --- | --- | --- |
| 1. Validate | `models.py`, `registry.py` | Validate the request and reject a stale catalog version |
| 2. Filter | `policy.py` | Remove disabled, blocked, unauthorized, or disallowed-risk workflows |
| 3. Exact event | `router.py` | Optionally route one authenticated event match, subject to input completeness |
| 4. Precheck | `policy.py` | Reject open-ended reasoning and unsupported multi-action requests |
| 5. Retrieve | `retrieval.py` | Rank the top (K) workflows from positive capability text |
| 6. Verify | `verification.py` | Score the full request–contract pair |
| 7. Resolve inputs | `inputs.py` | Prefer trusted context, then optional regex extraction |
| 8. Calibrate | `calibration.py` | Apply temperature scaling and risk-tier thresholds |
| 9. Decide | `router.py` | Return `ROUTE`, `CLARIFY`, or `LLM_REQUIRED` with lineage |

## 1. Validation and lineage

`RouteRequest` uses a strict Pydantic model: unknown fields are rejected and text is limited to
8,000 characters. If a request supplies `catalog_version`, `WorkflowRegistry.require_version`
compares it with the active snapshot.

A mismatch fails rather than silently routing against a different contract set.

## 2. Eligibility filtering

`RoutingPolicy.filter_candidates` keeps only workflows that are:

- `active`;
- in an allowed risk tier;
- present in `allowed_workflow_ids`, when that field is not `None`; and
- absent from `blocked_workflow_ids`.

If nothing remains, the result is:

```text
LLM_REQUIRED / NO_ELIGIBLE_WORKFLOW
```

## 3. Trusted event routing

When `event_type` is present and exact-event routing is enabled, FlowRoute looks for eligible
workflows that declare it.

- One match with complete inputs → `ROUTE / EXACT_EVENT_RULE`.
- One match with missing inputs → `CLARIFY / EXACT_EVENT_MISSING_INPUT`.
- More than one match → `LLM_REQUIRED / AMBIGUOUS_EVENT_RULE`.
- No match → continue to normal semantic routing.

The event must come from a trusted structured source. Exact-event routing is disabled by default
in shadow and production modes because a generic HTTP request does not establish that trust.
Free-form user input must not manufacture an authoritative event type.

## 4. Deterministic guards

The v0.2 policy recognizes common requests for explanation, recommendation, analysis, or planning
and returns `OPEN_ENDED_REASONING`. It also detects multiple action verbs connected by phrases
such as “and then” and returns `MULTI_ACTION_UNSUPPORTED`.

These regex guards are transparent baseline policy, not a complete natural-language safety
system.

## 5. Candidate retrieval

The baseline `TfidfRetriever` serializes:

- workflow name;
- description;
- positive capabilities; and
- positive examples.

It combines word n-gram and character n-gram cosine similarity:

`score = (0.65 × word score) + (0.35 × character score)`

It returns up to `top_k` hits. A request whose best score is below
`min_retrieval_score` becomes `NO_WORKFLOW`.

### Why exclusions are not retrieved

Indexing a phrase such as “delete a recurring series” can make that excluded behavior look closer
to the cancellation workflow. Negative fields stay out of stage-one serialization. The verifier
receives the complete contract.

## 6. Pair verification

The lexical baseline uses:

- the retrieval score as positive evidence;
- similarity to each exclusion as a penalty; and
- deterministic required-input resolution.

It produces three component scores and one label:

- `executable`;
- `needs_input`; or
- `mismatch`.

The production research path replaces this logic with a trained three-way cross-encoder.

## 7. Input completeness

If required inputs are absent, an otherwise compatible pair cannot be labeled executable. It may
become `CLARIFY` when the needs-input score clears the clarification threshold.

## 8. Risk calibration

The router calibrates the winning semantic score, compares it with the second-best candidate, and
loads thresholds for the candidate's risk tier.

The route is accepted only when both are true:

- `top confidence >= route threshold for the risk tier`; and
- `top confidence - second confidence >= margin threshold for the risk tier`.

Higher-risk tiers should normally have stricter route and margin thresholds.

## 9. Typed response

Every response includes:

- request ID;
- decision and reason code;
- optional workflow ID;
- confidence;
- missing input names;
- confirmation requirement;
- model version;
- calibration version;
- catalog version; and
- routing latency.

Debug mode additionally returns candidate-level details.
