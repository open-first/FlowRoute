# FlowRoute

FlowRoute is a small, safety-oriented router that maps a natural-language request to a
deterministic workflow without using a generative LLM for the routing decision.

It returns exactly one of three outcomes:

- `ROUTE`: one eligible workflow clears its risk threshold;
- `CLARIFY`: the capability matches, but required input is missing; or
- `LLM_REQUIRED`: the request is unsupported, ambiguous, reasoning-heavy, or below threshold.

FlowRoute never executes workflows. Authorization, argument validation, confirmation,
idempotency, and side effects remain in the workflow orchestrator.

## Status

Version 0.2 provides a **production-hardened routing runtime and research scaffold**, but it does
not include a released model checkpoint. The default indexed TF-IDF retriever and lexical verifier
are development baselines. Production mode rejects them.

Production startup requires trained backends, a matching and approved artifact manifest, local
checkpoint hashes, a production-safe catalog, calibrated thresholds, and an injected
authorization callback. Model quality still depends on representative data and workflow-disjoint
evaluation; the demo fixtures are not evidence of real-world accuracy.

## Architecture

```mermaid
flowchart TD
    A["Request + trusted context"] --> B["Rules and policy filter"]
    B --> C["Bi-encoder retrieval"]
    C --> D["Pair verifier"]
    D --> E["Risk calibration"]
    E --> F{"Decision"}
    F --> G["ROUTE"]
    F --> H["CLARIFY"]
    F --> I["LLM_REQUIRED"]
```

## Quick start

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

flowroute route \
  --catalog examples/workflows.yaml \
  --text "Where is order 4812?" \
  --debug
```

Expected decision:

```json
{
  "decision": "ROUTE",
  "workflow_id": "orders.get_status",
  "reason_code": "ACCEPTED_LOW_RISK"
}
```

Run the local fixture suite:

```bash
flowroute evaluate \
  --catalog examples/workflows.yaml \
  --calibration configs/calibration.yaml \
  --data examples/requests.jsonl \
  --fail-on-error
```

Run unit tests without installing development tools:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Developer documentation

The complete developer guide is authored as portable Markdown under `docs/` and configured for
MkDocs:

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Build a static site that can be uploaded to any static host:

```bash
mkdocs build --strict
```

Start with [the documentation home](docs/index.md). It covers installation, contracts, Python,
HTTP and CLI integration, routing internals, training, dataset design, evaluation, safety,
production requirements, and troubleshooting.

## Python API

```python
from flowroute import FlowRouter, RouteRequest, WorkflowRegistry

registry = WorkflowRegistry.from_yaml("examples/workflows.yaml")
router = FlowRouter(registry)

result = router.route(
    RouteRequest(
        text="Cancel my design review tomorrow at 3 PM",
        context={"event_id": "evt_123"},
    )
)

print(result.decision)      # ROUTE
print(result.workflow_id)   # calendar.cancel_event
```

An empty `allowed_workflow_ids` list means no workflows are allowed. Omitting the field means all
otherwise eligible workflows may be considered.

## HTTP API

```bash
pip install -e ".[api]"
flowroute serve --catalog examples/workflows.yaml --port 8000
```

```bash
curl -s http://127.0.0.1:8000/v1/route \
  -H 'content-type: application/json' \
  -d '{
    "text": "Cancel my design review tomorrow at 3 PM",
    "context": {"event_id": "evt_123"},
    "catalog_version": "demo-2026-09-04"
  }'
```

The development service also exposes `GET /health`, `GET /health/live`, and
`GET /health/ready`. A stale `catalog_version` returns HTTP 409.

## Production mode

```python
from flowroute import LoggingTelemetrySink, load_production_router
from flowroute.api import ApiSettings, create_app

router = load_production_router(
    catalog_path="/config/workflows.yaml",
    calibration_path="/config/calibration.yaml",
    artifact_manifest_path="/config/artifact-manifest.yaml",
    retriever_model="/models/retriever",
    verifier_model="/models/verifier",
    telemetry=LoggingTelemetrySink(),
)

async def authorize(request, payload):
    principal = request.scope["authenticated_principal"]
    return await permission_service.allowed_workflow_ids(principal)

app = create_app(
    router,
    authorizer=authorize,
    settings=ApiSettings.production_defaults(
        trusted_hosts=["router.example.internal"],
    ),
)
```

Production mode:

- verifies catalog, model, serializer, calibration, policy, prefix, label-order, and top-K lineage;
- hashes local model directories before loading;
- requires catalog version and an authorization-derived workflow allowlist on every request;
- disables caller-supplied exact-event shortcuts unless explicitly approved for a trusted entrypoint;
- disables debug candidate exposure;
- checks artifact compatibility again before every request;
- time-bounds regex extraction and limits request/context sizes;
- fails closed on backend errors;
- batches verifier inference;
- emits privacy-conscious structured telemetry; and
- supports atomic bundle reload and rollback through `RouterRuntime`.

See [Production mode](docs/operations/production-mode.md) and
[Artifact manifests](docs/operations/artifact-manifests.md).

## Workflow contracts

Contracts describe capability boundaries, inputs, effects, and risk—not executable code.

```yaml
- id: calendar.cancel_event
  version: 1.0.0
  name: Cancel a calendar event
  description: Cancel one existing event the current user may modify.
  positive_capabilities:
    - cancel an existing meeting
  exclusions:
    - decline an invitation
    - delete a recurring series without confirmation
  required_inputs:
    - name: event_id
      pattern: '\b(?P<value>evt_[A-Za-z0-9_-]+)\b'
  side_effect: external_write
  risk_tier: medium
  confirmation: required_if_recurring
```

For safety, external or destructive contracts must declare both exclusions and a confirmation
policy. Regex extraction is optional; trusted structured context takes precedence.

## Plug in Hugging Face checkpoints

Install the ML extra:

```bash
pip install -e ".[hf]"
```

```python
from flowroute import FlowRouter, WorkflowRegistry
from flowroute.backends import HuggingFaceCrossEncoderVerifier, HuggingFaceRetriever

registry = WorkflowRegistry.from_yaml("examples/workflows.yaml")
router = FlowRouter(
    registry,
    retriever=HuggingFaceRetriever("your-account/flowroute-retriever"),
    verifier=HuggingFaceCrossEncoderVerifier("your-account/flowroute-verifier"),
)
```

The verifier checkpoint must output logits in this order by default:
`mismatch`, `needs_input`, `executable`. Schema completeness remains deterministic and can override
an unsafe `executable` prediction.

## Train the first retriever

The `training/` directory contains:

- a deterministic demo-data builder;
- a current Sentence Transformers trainer entry point;
- a Transformers three-class verifier entry point; and
- model/dataset card templates with explicit `TBD` fields.

```bash
PYTHONPATH=src python training/build_demo_data.py \
  --catalog examples/workflows.yaml \
  --output-dir artifacts/demo-data

pip install -e ".[training]"
python training/train_retriever.py \
  --data artifacts/demo-data/retriever.jsonl \
  --output-dir models/flowroute-retriever
```

Do not publish the demo-derived checkpoint as a research result. Build workflow-disjoint train,
calibration, and hidden test splits first.

## Repository map

```text
src/flowroute/          routing library, CLI, and optional HTTP API
src/flowroute/backends/ optional Hugging Face adapters
examples/               demo catalog and labeled requests
configs/                baseline threshold bundle
training/               data and model-training scaffolds
tests/                  unit and end-to-end safety tests
docs/                   architecture and research implementation notes
```

## Before publishing a model release

1. Add the final repository URLs to package metadata after the public repository URL exists.
2. Audit dataset and base-model licenses.
3. Freeze workflow-disjoint splits before augmentation.
4. Train and evaluate at least the retriever and verifier baselines.
5. Fit calibration by risk tier on a separate split.
6. Report false-route rate together with route coverage and confidence intervals.
7. Fill every `TBD` in the model and dataset cards; publish checkpoint hashes.

## License

Apache-2.0. Dataset and model artifacts may have separate licenses; document them before release.
