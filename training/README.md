# Training scaffold

This directory wires FlowRoute to current Hugging Face training APIs. It does not include a
publishable dataset or checkpoint.

## Data contracts

Retriever rows contain:

```json
{"anchor":"user request","positive":"matching contract","negative":"near-miss contract"}
```

Verifier rows contain:

```json
{"query":"user request","contract":"serialized contract","label":2,"label_name":"executable"}
```

Verifier labels are fixed:

| ID | Label | Meaning |
|---:|---|---|
| 0 | `mismatch` | Contract cannot satisfy the request. |
| 1 | `needs_input` | Capability matches, but required information is unavailable. |
| 2 | `executable` | Capability and routing-time information both match. |

## Demo pipeline

```bash
PYTHONPATH=src python training/build_demo_data.py \
  --catalog examples/workflows.yaml \
  --output-dir artifacts/demo-data

pip install -e ".[training]"

python training/train_retriever.py \
  --data artifacts/demo-data/retriever.jsonl \
  --output-dir models/retriever

python training/train_verifier.py \
  --data artifacts/demo-data/verifier.jsonl \
  --output-dir models/verifier
```

The catalog examples are deliberately tiny and leak into the generated rows. Use this only to
confirm that loading, batching, training, saving, and inference work.

## Real experiment rules

- Split by workflow identity before generating paraphrases or mining negatives.
- Keep calibration data separate from model-selection validation data.
- Include same-domain near misses, explicit exclusions, missing-input pairs, ambiguous requests,
  open-ended reasoning, and requests for which no workflow exists.
- Preserve source, license, generator, reviewer, workflow family, and split provenance per row.
- Never tune thresholds on the hidden test set.
- Report false-route risk and coverage together, including bootstrap confidence intervals.
