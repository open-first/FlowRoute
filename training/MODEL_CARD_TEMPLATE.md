---
language:
  - en
license: apache-2.0
library_name: sentence-transformers
pipeline_tag: sentence-similarity
tags:
  - workflow-routing
  - tool-retrieval
  - selective-prediction
---

# FlowRoute checkpoint

> Draft template. Replace every `TBD` before publishing.

## Model details

- Component: `TBD` (`retriever` or `verifier`)
- Base model: `TBD`
- Parameters: `TBD`
- Training code revision: `TBD`
- Dataset revision and hash: `TBD`
- Intended catalog schema version: `TBD`

## Intended use

Candidate ranking or pair verification inside FlowRoute. This model recommends a workflow but
does not authorize or execute it.

## Out-of-scope use

- autonomous execution of financial, destructive, legal, medical, or safety-critical actions;
- use without independent authorization, schema validation, and confirmation controls;
- languages and domains absent from the evaluation table; and
- treating raw scores as calibrated probabilities.

## Evaluation

| Slice | Recall@8 | False-route rate | Coverage | Notes |
|---|---:|---:|---:|---|
| Seen workflow | TBD | TBD | TBD | TBD |
| Unseen workflow | TBD | TBD | TBD | TBD |
| Unseen domain | TBD | TBD | TBD | TBD |
| Near miss | TBD | TBD | TBD | TBD |
| OOD | TBD | TBD | TBD | TBD |

Reference hardware, latency, memory, confidence intervals, and threshold bundle: `TBD`.

## Training data

Sources, licenses, deduplication, workflow-disjoint split procedure, synthetic-data provenance,
human review, and known contamination: `TBD`.

## Limitations and risks

Catalog wording, unseen languages, distribution shift, ambiguous requests, and adversarial text can
all cause misrouting. The deployment must default to abstention when the calibrated operating point
is unavailable or stale.

