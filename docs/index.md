# FlowRoute

**Route predictable natural-language requests to deterministic workflows without using a
generative LLM for the routing decision.**

FlowRoute is a selector between user language and a versioned workflow catalog. It returns one
of three typed outcomes and never executes the selected workflow.

<div class="flowroute-outcomes">
  <div>
    <strong>ROUTE</strong>
    One eligible workflow clears its risk-specific confidence and margin thresholds.
  </div>
  <div>
    <strong>CLARIFY</strong>
    The capability matches, but one or more required inputs are missing.
  </div>
  <div>
    <strong>LLM_REQUIRED</strong>
    The request is unsupported, ambiguous, reasoning-heavy, or below threshold.
  </div>
</div>

!!! warning "Routing is not execution"

    A `ROUTE` response recommends entry into a workflow-specific validation path. Your
    orchestrator must still check authorization, typed inputs, live preconditions,
    confirmation, and idempotency before performing side effects.

## Start here

1. [Install FlowRoute](getting-started/installation.md).
2. [Route the first request](getting-started/quickstart.md).
3. Define your [workflow contracts](guides/workflow-contracts.md).
4. Choose [Python](guides/python-integration.md), [HTTP](guides/http-api.md), or
   [CLI](guides/cli.md) integration.
5. Read the [production checklist](operations/production.md) before real traffic.

## Current status

Version 0.2.0 provides a production-hardened runtime and research scaffold. The default indexed
TF-IDF retriever and lexical verifier make the full path testable on CPU without downloading a
model. Production mode rejects those baselines, and the demo fixtures are not evidence of
real-world model quality.

Production deployment requires trained checkpoints, workflow-disjoint evaluation, calibrated
thresholds, an approved artifact manifest, local artifact hash verification, and an
application-owned authorization callback.

The intended research configuration replaces those defaults with:

- a fine-tuned bi-encoder for top-K retrieval;
- a three-way cross-encoder for `mismatch`, `needs_input`, and `executable`; and
- thresholds fitted on a separate, workflow-disjoint calibration split.

## When FlowRoute fits

Use FlowRoute when:

- workflows are narrow, named, and deterministic;
- users express the same intent in varied language;
- a safe fallback is available for ambiguous requests;
- inference cost or latency matters; and
- false routing is more expensive than abstention.

Use an LLM or planner when the task requires explanation, advice, strategy, open-ended
generation, or several dependent actions.

## Requirements at a glance

| Requirement | Value |
| --- | --- |
| Python | 3.10 or newer |
| Core runtime | NumPy, Pydantic, PyYAML, regex, scikit-learn |
| GPU | Not required for the baseline |
| API extra | FastAPI and Uvicorn |
| Inference extra | Torch, Transformers, Sentence Transformers |
| Training extra | Datasets, Accelerate, plus inference dependencies |
| License | Apache-2.0 |

Continue with [Installation](getting-started/installation.md).
