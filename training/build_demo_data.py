"""Build tiny deterministic training fixtures from a workflow catalog.

This is for plumbing validation only. Embedded contract examples must never be
used to report final generalization metrics.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from flowroute.inputs import resolve_required_inputs
from flowroute.registry import WorkflowRegistry
from flowroute.serialization import serialize_contract

LABELS = {"mismatch": 0, "needs_input": 1, "executable": 2}


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build(catalog: Path, output_dir: Path, seed: int) -> tuple[Path, Path]:
    rng = random.Random(seed)
    workflows = WorkflowRegistry.from_yaml(catalog).active_workflows()
    retriever_rows: list[dict[str, object]] = []
    verifier_rows: list[dict[str, object]] = []

    for workflow in workflows:
        positive_contract = serialize_contract(workflow)
        alternatives = [item for item in workflows if item.id != workflow.id]
        same_domain = [
            item
            for item in alternatives
            if item.id.split(".", 1)[0] == workflow.id.split(".", 1)[0]
        ]
        negative_pool = same_domain or alternatives
        for example_index, query in enumerate(workflow.examples):
            negative = rng.choice(negative_pool)
            retriever_rows.append(
                {
                    "id": f"{workflow.id}:example:{example_index}",
                    "anchor": query,
                    "positive": positive_contract,
                    "negative": serialize_contract(negative),
                    "workflow_id": workflow.id,
                    "negative_workflow_id": negative.id,
                    "provenance": "catalog_example",
                }
            )
            missing = resolve_required_inputs(workflow, query, {}).missing
            positive_label = "needs_input" if missing else "executable"
            verifier_rows.append(
                {
                    "id": f"{workflow.id}:positive:{example_index}",
                    "query": query,
                    "contract": positive_contract,
                    "label": LABELS[positive_label],
                    "label_name": positive_label,
                    "workflow_id": workflow.id,
                    "provenance": "catalog_example",
                }
            )
            sampled_negatives = rng.sample(alternatives, k=min(2, len(alternatives)))
            for negative_index, negative_workflow in enumerate(sampled_negatives):
                verifier_rows.append(
                    {
                        "id": f"{workflow.id}:negative:{example_index}:{negative_index}",
                        "query": query,
                        "contract": serialize_contract(negative_workflow),
                        "label": LABELS["mismatch"],
                        "label_name": "mismatch",
                        "workflow_id": negative_workflow.id,
                        "provenance": "sampled_negative",
                    }
                )
        for exclusion_index, exclusion in enumerate(workflow.exclusions):
            verifier_rows.append(
                {
                    "id": f"{workflow.id}:exclusion:{exclusion_index}",
                    "query": exclusion,
                    "contract": positive_contract,
                    "label": LABELS["mismatch"],
                    "label_name": "mismatch",
                    "workflow_id": workflow.id,
                    "provenance": "contract_exclusion",
                }
            )

    retriever_path = output_dir / "retriever.jsonl"
    verifier_path = output_dir / "verifier.jsonl"
    _write_jsonl(retriever_path, retriever_rows)
    _write_jsonl(verifier_path, verifier_rows)
    return retriever_path, verifier_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    retriever_path, verifier_path = build(args.catalog, args.output_dir, args.seed)
    print(json.dumps({"retriever": str(retriever_path), "verifier": str(verifier_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
