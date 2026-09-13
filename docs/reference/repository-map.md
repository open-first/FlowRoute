# Repository map

```text
flowroute/
├── .github/workflows/
│   └── ci.yml
├── configs/
│   ├── artifact-manifest.example.yaml
│   └── calibration.yaml
├── docs/
│   ├── concepts/
│   ├── getting-started/
│   ├── guides/
│   ├── models/
│   ├── operations/
│   ├── reference/
│   └── stylesheets/
├── examples/
│   ├── requests.jsonl
│   ├── run_demo.py
│   └── workflows.yaml
├── src/flowroute/
│   ├── backends/
│   ├── api.py
│   ├── calibration.py
│   ├── cli.py
│   ├── evaluation.py
│   ├── factory.py
│   ├── inputs.py
│   ├── models.py
│   ├── policy.py
│   ├── registry.py
│   ├── retrieval.py
│   ├── router.py
│   ├── runtime.py
│   ├── serialization.py
│   ├── telemetry.py
│   └── verification.py
├── tests/
├── training/
├── Dockerfile
├── SECURITY.md
├── mkdocs.yml
├── pyproject.toml
├── requirements-audit.txt
└── requirements-docs.txt
```

## Runtime package

| Path | Responsibility |
| --- | --- |
| `router.py` | Orchestrates filtering, retrieval, verification, calibration, and decisions |
| `models.py` | Strict public request, response, catalog, and score types |
| `registry.py` | Catalog loading, validation, lookup, versioning, and content hash |
| `policy.py` | Candidate eligibility and deterministic request guards |
| `retrieval.py` | Retriever protocol and prepared TF-IDF development baseline |
| `verification.py` | Verifier protocol and lexical baseline |
| `inputs.py` | Trusted-context and regex input resolution |
| `calibration.py` | Temperature and risk-tier thresholds |
| `evaluation.py` | JSONL fixture evaluator and metrics |
| `factory.py` | Compatibility-checked production bundle loader |
| `api.py` | Optional FastAPI application factory |
| `cli.py` | Route, evaluate, and serve commands |
| `runtime.py` | Production settings, artifact manifests, hashing, reload, and rollback |
| `serialization.py` | Stable capability and contract text representations |
| `telemetry.py` | Privacy-conscious telemetry sink interfaces |
| `backends/huggingface.py` | Optional learned retriever and verifier adapters |

## Research scaffolding

| Path | Responsibility |
| --- | --- |
| `training/build_demo_data.py` | Build deterministic wiring data from the demo catalog |
| `training/train_retriever.py` | Sentence Transformers retriever entry point |
| `training/train_verifier.py` | Transformers three-class verifier entry point |
| `training/MODEL_CARD_TEMPLATE.md` | Publication checklist for checkpoints |
| `training/DATASET_CARD_TEMPLATE.md` | Publication checklist for datasets |

## Documentation

`mkdocs.yml` defines site navigation and rendering. All authored documentation remains Markdown
under `docs/`, so another documentation system can ingest it even if you do not use MkDocs.
