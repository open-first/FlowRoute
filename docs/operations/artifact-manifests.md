# Artifact manifests

The manifest binds every artifact and configuration value that changes routing behavior. A
production process fails during startup when the bundle is incomplete, unapproved, or mismatched.

## Inspect catalog identities

```bash
flowroute inspect-bundle \
  --catalog config/workflows.yaml \
  --calibration config/calibration.yaml \
  --top-k 8 \
  --require-production-catalog
```

This prints:

- catalog version and content hash;
- serializer version;
- calibration version and content hash;
- deterministic policy hash;
- top-K;
- retriever prefixes;
- verifier label order;
- exact-event routing policy; and
- production catalog issues.

## Hash local model artifacts

```bash
flowroute hash-artifact --path models/retriever
flowroute hash-artifact --path models/verifier
```

Directory hashes include sorted relative filenames and file contents. Renaming, adding, removing,
or changing a file changes the digest.

## Manifest example

```yaml
schema_version: "1"
bundle_version: routing-2026-09-04.1
created_at: 2026-09-04T18:30:00Z

catalog_version: commerce-2026-09-04
catalog_content_hash: "<64-character SHA-256>"
serializer_version: flowroute-contract-v1

retriever_model_version: flowroute-retriever@immutable-revision
verifier_model_version: flowroute-verifier@immutable-revision
retriever_query_prefix: ""
retriever_document_prefix: ""
verifier_label_order: [mismatch, needs_input, executable]
allow_exact_event_routes: false

calibration_version: commerce-calibration-2026-09-04
calibration_content_hash: "<64-character SHA-256>"
policy_content_hash: "<64-character SHA-256>"
top_k: 8

artifact_hashes:
  retriever: "<64-character SHA-256>"
  verifier: "<64-character SHA-256>"

approved_for_production: true
approval_reference: evaluation-report-2026-09-04
```

`configs/artifact-manifest.example.yaml` is deliberately unapproved and contains placeholder
model hashes. It cannot start production accidentally.

## Approval process

Set `approved_for_production: true` only after:

1. the dataset and checkpoint licenses are approved;
2. hidden-test results meet the defined false-route target for every risk tier;
3. calibration is frozen;
4. exported or quantized artifacts are reevaluated;
5. hashes are calculated from the exact deployment files; and
6. the evaluation report or change record is stable and reviewable.

The manifest records approval; it does not replace review.

## Bundle layout

```text
release/
├── config/
│   ├── workflows.yaml
│   ├── calibration.yaml
│   └── artifact-manifest.yaml
└── models/
    ├── retriever/
    └── verifier/
```

Keep the complete release immutable. Roll forward or back by selecting a different bundle, not by
editing files inside an active release.

FlowRoute repeats the compatibility check before every production request. If a routing-relevant
setting is mutated after startup, the request becomes
`LLM_REQUIRED / RUNTIME_INTEGRITY_FAILURE`.
