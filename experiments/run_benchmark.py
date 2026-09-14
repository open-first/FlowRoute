#!/usr/bin/env python3
"""Reproduce the FlowRoute benchmark reported in the paper.

The experiment treats each intent label as a runtime workflow. It compares a
lexical index, description-only dense routing, and example-aware dense routing.
No generative model is called and no benchmark test example is used to choose
hyperparameters or decision thresholds.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import sklearn
import torch
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer


MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
SEEDS = (11, 23, 37, 53, 71)
EXAMPLE_COUNTS = (0, 1, 3, 5, 10)
ALPHAS = tuple(value / 10 for value in range(11))
TARGET_SELECTIVE_ERROR = 0.05
TARGET_OOD_FPR = 0.05

DATASETS = {
    "clinc150_full.json": {
        "url": "https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json",
        "sha256": "36923c3705a59e08fe9c3883d8bc2dd966ef93e22cb78ac41171782a698d56e0",
    },
    "banking77_train.csv": {
        "url": "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv",
        "sha256": "b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b",
    },
    "banking77_test.csv": {
        "url": "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv",
        "sha256": "d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d",
    },
}


@dataclass(frozen=True)
class DatasetSplit:
    name: str
    train_by_label: dict[str, list[str]]
    validation: list[tuple[str, str]]
    test: list[tuple[str, str]]
    ood_validation: list[str]
    ood_test: list[str]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename, metadata in DATASETS.items():
        target = data_dir / filename
        if not target.exists():
            print(f"Downloading {filename}", file=sys.stderr)
            urllib.request.urlretrieve(metadata["url"], target)
        actual = sha256(target)
        if actual != metadata["sha256"]:
            raise RuntimeError(
                f"Checksum mismatch for {target}: expected {metadata['sha256']}, got {actual}"
            )


def load_clinc(data_dir: Path) -> DatasetSplit:
    raw = json.loads((data_dir / "clinc150_full.json").read_text(encoding="utf-8"))
    train_by_label: dict[str, list[str]] = defaultdict(list)
    for text, label in raw["train"]:
        train_by_label[label].append(text)
    return DatasetSplit(
        name="CLINC150",
        train_by_label=dict(train_by_label),
        validation=[tuple(item) for item in raw["val"]],
        test=[tuple(item) for item in raw["test"]],
        ood_validation=[text for text, _ in [*raw["oos_train"], *raw["oos_val"]]],
        ood_test=[text for text, _ in raw["oos_test"]],
    )


def load_banking(data_dir: Path) -> DatasetSplit:
    train_by_label: dict[str, list[str]] = defaultdict(list)
    with (data_dir / "banking77_train.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            train_by_label[row["category"]].append(row["text"])
    with (data_dir / "banking77_test.csv").open(encoding="utf-8", newline="") as handle:
        test = [(row["text"], row["category"]) for row in csv.DictReader(handle)]

    validation: list[tuple[str, str]] = []
    exemplar_pool: dict[str, list[str]] = {}
    for label, examples in sorted(train_by_label.items()):
        label_seed = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16)
        shuffled = list(examples)
        random.Random(20260912 + label_seed).shuffle(shuffled)
        validation.extend((text, label) for text in shuffled[:20])
        exemplar_pool[label] = shuffled[20:]

    return DatasetSplit(
        name="BANKING77",
        train_by_label=exemplar_pool,
        validation=validation,
        test=test,
        ood_validation=[],
        ood_test=[],
    )


def workflow_description(label: str) -> str:
    return f"Workflow for {label.replace('_', ' ')}."


def select_examples(
    train_by_label: dict[str, list[str]], labels: list[str], count: int, seed: int
) -> dict[str, list[str]]:
    selected: dict[str, list[str]] = {}
    for label in labels:
        label_seed = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16)
        values = list(train_by_label[label])
        random.Random(seed + label_seed).shuffle(values)
        selected[label] = values[:count]
    return selected


def dense_components(
    model: SentenceTransformer,
    query_embeddings: np.ndarray,
    labels: list[str],
    examples: dict[str, list[str]],
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray | None]:
    descriptions = [workflow_description(label) for label in labels]
    description_embeddings = model.encode(
        descriptions,
        batch_size=128,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    description_scores = query_embeddings @ description_embeddings.T
    count = len(examples[labels[0]]) if labels else 0
    if count == 0:
        return description_scores, None, description_embeddings, None

    flat_examples = [text for label in labels for text in examples[label]]
    example_embeddings = model.encode(
        flat_examples,
        batch_size=128,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).reshape(len(labels), count, -1)
    example_scores = np.einsum("qd,lnd->qln", query_embeddings, example_embeddings).max(
        axis=2
    )
    return (
        description_scores,
        example_scores,
        description_embeddings,
        example_embeddings,
    )


def combine_scores(
    description_scores: np.ndarray, example_scores: np.ndarray | None, alpha: float
) -> np.ndarray:
    if example_scores is None:
        return description_scores
    return (alpha * description_scores) + ((1.0 - alpha) * example_scores)


def label_indices(
    rows: list[tuple[str, str]], label_to_index: dict[str, int]
) -> np.ndarray:
    return np.asarray([label_to_index[label] for _, label in rows], dtype=np.int64)


def ranking_metrics(scores: np.ndarray, gold: np.ndarray) -> dict[str, float]:
    order = np.argsort(-scores, axis=1, kind="stable")
    top1 = float(np.mean(order[:, 0] == gold))
    top5 = float(
        np.mean(np.any(order[:, : min(5, scores.shape[1])] == gold[:, None], axis=1))
    )
    return {"top1": top1, "recall_at_5": top5}


def common_confusions(
    scores: np.ndarray, gold: np.ndarray, labels: list[str], limit: int = 8
) -> list[dict[str, Any]]:
    predictions = np.argmax(scores, axis=1)
    pairs = Counter(
        (labels[int(expected)], labels[int(predicted)])
        for expected, predicted in zip(gold, predictions, strict=True)
        if expected != predicted
    )
    return [
        {"gold": gold_label, "predicted": predicted_label, "count": count}
        for (gold_label, predicted_label), count in pairs.most_common(limit)
    ]


def tune_alpha(
    description_scores: np.ndarray,
    example_scores: np.ndarray | None,
    gold: np.ndarray,
) -> float:
    if example_scores is None:
        return 1.0
    candidates: list[tuple[float, float]] = []
    for alpha in ALPHAS:
        metrics = ranking_metrics(
            combine_scores(description_scores, example_scores, alpha), gold
        )
        candidates.append((metrics["top1"], alpha))
    # Prefer more description weight when validation accuracy ties.
    return max(candidates, key=lambda item: (item[0], item[1]))[1]


def lexical_scores(
    queries: list[str], labels: list[str], examples: dict[str, list[str]]
) -> np.ndarray:
    documents = [
        " ".join([workflow_description(label), *examples[label]]) for label in labels
    ]
    word = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    char = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        analyzer="char_wb",
        ngram_range=(3, 5),
        sublinear_tf=True,
        min_df=1,
    )
    word_documents = word.fit_transform(documents)
    char_documents = char.fit_transform(documents)
    word_scores = (word.transform(queries) @ word_documents.T).toarray()
    char_scores = (char.transform(queries) @ char_documents.T).toarray()
    return np.clip((0.65 * word_scores) + (0.35 * char_scores), 0.0, 1.0)


def top_score_and_margin(
    scores: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.argsort(-scores, axis=1, kind="stable")
    best_index = order[:, 0]
    row_ids = np.arange(scores.shape[0])
    best_score = scores[row_ids, best_index]
    second_score = (
        scores[row_ids, order[:, 1]]
        if scores.shape[1] > 1
        else np.zeros_like(best_score)
    )
    return best_index, best_score, best_score - second_score


def decision_metrics(
    id_scores: np.ndarray,
    id_gold: np.ndarray,
    ood_scores: np.ndarray,
    score_threshold: float,
    margin_threshold: float,
) -> dict[str, float | int]:
    prediction, best_score, margin = top_score_and_margin(id_scores)
    accepted = (best_score >= score_threshold) & (margin >= margin_threshold)
    accepted_count = int(accepted.sum())
    wrong_count = int((accepted & (prediction != id_gold)).sum())
    id_coverage = accepted_count / len(id_gold)
    selective_error = wrong_count / accepted_count if accepted_count else 0.0

    if len(ood_scores):
        _, ood_best_score, ood_margin = top_score_and_margin(ood_scores)
        ood_accepted = (ood_best_score >= score_threshold) & (
            ood_margin >= margin_threshold
        )
        ood_false_positive_count = int(ood_accepted.sum())
        ood_fpr = ood_false_positive_count / len(ood_scores)
    else:
        ood_false_positive_count = 0
        ood_fpr = math.nan

    return {
        "id_coverage": id_coverage,
        "selective_error": selective_error,
        "accepted_id": accepted_count,
        "wrong_accepted_id": wrong_count,
        "ood_fpr": ood_fpr,
        "accepted_ood": ood_false_positive_count,
    }


def tune_decision_thresholds(
    id_scores: np.ndarray,
    id_gold: np.ndarray,
    ood_scores: np.ndarray,
) -> tuple[float, float, dict[str, float | int]]:
    id_prediction, id_best_score, id_margin = top_score_and_margin(id_scores)
    id_wrong = id_prediction != id_gold
    _, ood_best_score, ood_margin = top_score_and_margin(ood_scores)
    best: tuple[float, float, float, float, float, dict[str, float | int]] | None = None
    for score_threshold in np.linspace(0.0, 1.0, 201):
        for margin_threshold in np.linspace(0.0, 0.5, 101):
            id_accepted = (id_best_score >= score_threshold) & (
                id_margin >= margin_threshold
            )
            accepted_id = int(id_accepted.sum())
            wrong_accepted_id = int((id_accepted & id_wrong).sum())
            ood_accepted = (ood_best_score >= score_threshold) & (
                ood_margin >= margin_threshold
            )
            accepted_ood = int(ood_accepted.sum())
            metrics: dict[str, float | int] = {
                "id_coverage": accepted_id / len(id_gold),
                "selective_error": wrong_accepted_id / accepted_id
                if accepted_id
                else 0.0,
                "accepted_id": accepted_id,
                "wrong_accepted_id": wrong_accepted_id,
                "ood_fpr": accepted_ood / len(ood_scores),
                "accepted_ood": accepted_ood,
                "selective_error_wilson_upper_95": wilson_interval(
                    wrong_accepted_id, accepted_id
                )[1],
                "ood_fpr_wilson_upper_95": wilson_interval(
                    accepted_ood, len(ood_scores)
                )[1],
            }
            if metrics["accepted_id"] < 100:
                continue
            if metrics["selective_error_wilson_upper_95"] > TARGET_SELECTIVE_ERROR:
                continue
            if metrics["ood_fpr_wilson_upper_95"] > TARGET_OOD_FPR:
                continue
            candidate = (
                float(metrics["id_coverage"]),
                -float(metrics["selective_error"]),
                -float(metrics["ood_fpr"]),
                -float(score_threshold),
                -float(margin_threshold),
                metrics,
            )
            if best is None or candidate[:5] > best[:5]:
                best = candidate
    if best is None:
        raise RuntimeError("No threshold pair satisfied the validation constraints")
    return -best[3], -best[4], best[5]


def mean_sd(values: list[float]) -> dict[str, float]:
    return {
        "mean": float(statistics.fmean(values)),
        "sd": float(statistics.stdev(values)) if len(values) > 1 else 0.0,
    }


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> list[float]:
    if total == 0:
        return [math.nan, math.nan]
    proportion = successes / total
    denominator = 1 + (z * z / total)
    centre = (proportion + (z * z / (2 * total))) / denominator
    radius = (
        z
        * math.sqrt(
            (proportion * (1 - proportion) / total) + (z * z / (4 * total * total))
        )
        / denominator
    )
    return [centre - radius, centre + radius]


def evaluate_dataset(
    model: SentenceTransformer,
    split: DatasetSplit,
    all_query_embeddings: dict[str, np.ndarray],
) -> dict[str, Any]:
    labels = sorted(split.train_by_label)
    label_to_index = {label: index for index, label in enumerate(labels)}
    test_texts = [text for text, _ in split.test]
    validation_gold = label_indices(split.validation, label_to_index)
    test_gold = label_indices(split.test, label_to_index)
    validation_embeddings = all_query_embeddings[f"{split.name}:validation"]
    test_embeddings = all_query_embeddings[f"{split.name}:test"]

    seed_results: list[dict[str, Any]] = []
    ablations: dict[int, list[dict[str, float]]] = {
        count: [] for count in EXAMPLE_COUNTS
    }
    reference_confusions: list[dict[str, Any]] = []

    for seed in SEEDS:
        seed_record: dict[str, Any] = {"seed": seed, "examples": {}}
        for count in EXAMPLE_COUNTS:
            examples = select_examples(split.train_by_label, labels, count, seed)
            val_desc, val_ex, desc_embeddings, example_embeddings = dense_components(
                model, validation_embeddings, labels, examples
            )
            alpha = tune_alpha(val_desc, val_ex, validation_gold)
            test_desc = test_embeddings @ desc_embeddings.T
            test_ex = (
                np.einsum("qd,lnd->qln", test_embeddings, example_embeddings).max(
                    axis=2
                )
                if example_embeddings is not None
                else None
            )
            test_scores = combine_scores(test_desc, test_ex, alpha)
            metrics = ranking_metrics(test_scores, test_gold)
            metrics["alpha"] = alpha
            seed_record["examples"][str(count)] = metrics
            ablations[count].append(metrics)
            if seed == 37 and count == 10:
                reference_confusions = common_confusions(test_scores, test_gold, labels)
        seed_results.append(seed_record)

    aggregate_ablations: dict[str, Any] = {}
    for count, records in ablations.items():
        aggregate_ablations[str(count)] = {
            "top1": mean_sd([record["top1"] for record in records]),
            "recall_at_5": mean_sd([record["recall_at_5"] for record in records]),
            "alpha": mean_sd([record["alpha"] for record in records]),
        }

    lexical_seed_metrics: list[dict[str, float]] = []
    for seed in SEEDS:
        examples = select_examples(split.train_by_label, labels, 10, seed)
        scores = lexical_scores(test_texts, labels, examples)
        lexical_seed_metrics.append(ranking_metrics(scores, test_gold))

    result: dict[str, Any] = {
        "dataset": split.name,
        "labels": len(labels),
        "validation_examples": len(split.validation),
        "test_examples": len(split.test),
        "ood_validation_examples": len(split.ood_validation),
        "ood_test_examples": len(split.ood_test),
        "seeds": list(SEEDS),
        "seed_results": seed_results,
        "ablation": aggregate_ablations,
        "lexical_10_examples": {
            "top1": mean_sd([item["top1"] for item in lexical_seed_metrics]),
            "recall_at_5": mean_sd(
                [item["recall_at_5"] for item in lexical_seed_metrics]
            ),
        },
        "reference_confusions": {
            "seed": 37,
            "examples_per_workflow": 10,
            "pairs": reference_confusions,
        },
    }

    if split.ood_validation and split.ood_test:
        ood_validation_embeddings = all_query_embeddings[f"{split.name}:ood_validation"]
        ood_test_embeddings = all_query_embeddings[f"{split.name}:ood_test"]
        selective_results: list[dict[str, Any]] = []
        for seed in SEEDS:
            examples = select_examples(split.train_by_label, labels, 10, seed)
            val_desc, val_ex, desc_embeddings, example_embeddings = dense_components(
                model, validation_embeddings, labels, examples
            )
            alpha = tune_alpha(val_desc, val_ex, validation_gold)
            validation_scores = combine_scores(val_desc, val_ex, alpha)
            ood_val_desc = ood_validation_embeddings @ desc_embeddings.T
            ood_val_ex = np.einsum(
                "qd,lnd->qln", ood_validation_embeddings, example_embeddings
            ).max(axis=2)
            ood_validation_scores = combine_scores(ood_val_desc, ood_val_ex, alpha)
            score_threshold, margin_threshold, validation_metrics = (
                tune_decision_thresholds(
                    validation_scores, validation_gold, ood_validation_scores
                )
            )

            test_desc = test_embeddings @ desc_embeddings.T
            test_ex = np.einsum("qd,lnd->qln", test_embeddings, example_embeddings).max(
                axis=2
            )
            test_scores = combine_scores(test_desc, test_ex, alpha)
            ood_test_desc = ood_test_embeddings @ desc_embeddings.T
            ood_test_ex = np.einsum(
                "qd,lnd->qln", ood_test_embeddings, example_embeddings
            ).max(axis=2)
            ood_test_scores = combine_scores(ood_test_desc, ood_test_ex, alpha)
            test_metrics = decision_metrics(
                test_scores,
                test_gold,
                ood_test_scores,
                score_threshold,
                margin_threshold,
            )
            selective_results.append(
                {
                    "seed": seed,
                    "alpha": alpha,
                    "score_threshold": score_threshold,
                    "margin_threshold": margin_threshold,
                    "validation": validation_metrics,
                    "test": test_metrics,
                }
            )

        result["selective_routing"] = {
            "target_validation_selective_error": TARGET_SELECTIVE_ERROR,
            "target_validation_ood_fpr": TARGET_OOD_FPR,
            "seed_results": selective_results,
            "test": {
                "id_coverage": mean_sd(
                    [float(item["test"]["id_coverage"]) for item in selective_results]
                ),
                "selective_error": mean_sd(
                    [
                        float(item["test"]["selective_error"])
                        for item in selective_results
                    ]
                ),
                "ood_fpr": mean_sd(
                    [float(item["test"]["ood_fpr"]) for item in selective_results]
                ),
            },
        }
    return result


def benchmark_latency(
    model: SentenceTransformer,
    split: DatasetSplit,
    seed: int,
    count: int = 10,
    iterations: int = 500,
) -> dict[str, Any]:
    torch.set_num_threads(1)
    labels = sorted(split.train_by_label)
    examples = select_examples(split.train_by_label, labels, count, seed)
    descriptions = model.encode(
        [workflow_description(label) for label in labels],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    example_embeddings = model.encode(
        [text for label in labels for text in examples[label]],
        batch_size=128,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).reshape(len(labels), count, -1)
    queries = [text for text, _ in split.test]
    alpha = 0.4

    def route_once(query: str) -> None:
        query_embedding = model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        description_scores = descriptions @ query_embedding
        example_scores = np.einsum(
            "lnd,d->ln", example_embeddings, query_embedding
        ).max(axis=1)
        scores = (alpha * description_scores) + ((1.0 - alpha) * example_scores)
        int(np.argmax(scores))

    for query in queries[:50]:
        route_once(query)
    samples: list[float] = []
    for index in range(iterations):
        start = time.perf_counter_ns()
        route_once(queries[index % len(queries)])
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return {
        "threads": torch.get_num_threads(),
        "iterations": iterations,
        "batch_size": 1,
        "catalog_workflows": len(labels),
        "examples_per_workflow": count,
        "median_ms": float(np.median(samples)),
        "p95_ms": float(np.percentile(samples, 95)),
        "p99_ms": float(np.percentile(samples, 99)),
        "mean_ms": float(np.mean(samples)),
    }


def cpu_model_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def write_summary_csv(results: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for dataset in results["datasets"]:
        rows.append(
            {
                "dataset": dataset["dataset"],
                "system": "word-char TF-IDF (10 examples)",
                "top1_mean": dataset["lexical_10_examples"]["top1"]["mean"],
                "top1_sd": dataset["lexical_10_examples"]["top1"]["sd"],
                "recall_at_5_mean": dataset["lexical_10_examples"]["recall_at_5"][
                    "mean"
                ],
                "recall_at_5_sd": dataset["lexical_10_examples"]["recall_at_5"]["sd"],
            }
        )
        for count in EXAMPLE_COUNTS:
            record = dataset["ablation"][str(count)]
            rows.append(
                {
                    "dataset": dataset["dataset"],
                    "system": f"dense example-aware ({count} examples)",
                    "top1_mean": record["top1"]["mean"],
                    "top1_sd": record["top1"]["sd"],
                    "recall_at_5_mean": record["recall_at_5"]["mean"],
                    "recall_at_5_sd": record["recall_at_5"]["sd"],
                }
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).parent / "results"
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=Path(__file__).parent / "cache"
    )
    args = parser.parse_args()

    ensure_data(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(args.cache_dir.resolve()))

    torch.manual_seed(20260912)
    np.random.seed(20260912)
    model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION)
    model.eval()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())

    datasets = [load_clinc(args.data_dir), load_banking(args.data_dir)]
    query_embeddings: dict[str, np.ndarray] = {}
    for split in datasets:
        groups = {
            "validation": [text for text, _ in split.validation],
            "test": [text for text, _ in split.test],
            "ood_validation": split.ood_validation,
            "ood_test": split.ood_test,
        }
        for group_name, texts in groups.items():
            if texts:
                query_embeddings[f"{split.name}:{group_name}"] = model.encode(
                    texts,
                    batch_size=128,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )

    started = time.time()
    dataset_results = [
        evaluate_dataset(model, split, query_embeddings) for split in datasets
    ]
    latency = benchmark_latency(model, datasets[0], seed=SEEDS[0])
    elapsed = time.time() - started

    results: dict[str, Any] = {
        "experiment": "FlowRoute public-data benchmark",
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "parameters": parameter_count,
        },
        "method": {
            "seeds": list(SEEDS),
            "example_counts": list(EXAMPLE_COUNTS),
            "alpha_grid": list(ALPHAS),
            "selection": (
                "alpha and route thresholds selected on validation data only; both validation "
                "risk constraints use upper endpoints of two-sided 95% Wilson intervals"
            ),
        },
        "datasets": dataset_results,
        "latency": latency,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu": cpu_model_name(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "sentence_transformers": __import__("sentence_transformers").__version__,
        },
        "data": {
            filename: {
                "url": metadata["url"],
                "sha256": sha256(args.data_dir / filename),
            }
            for filename, metadata in DATASETS.items()
        },
        "evaluation_seconds_excluding_initial_query_encoding": elapsed,
    }
    result_path = args.output_dir / "benchmark_results.json"
    result_path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_summary_csv(results, args.output_dir / "ranking_summary.csv")
    print(f"Wrote {result_path}")
    for dataset in dataset_results:
        dense = dataset["ablation"]["10"]
        print(
            f"{dataset['dataset']}: "
            f"top-1={dense['top1']['mean']:.4f} +/- {dense['top1']['sd']:.4f}, "
            f"R@5={dense['recall_at_5']['mean']:.4f} +/- "
            f"{dense['recall_at_5']['sd']:.4f}"
        )
    print(
        f"CPU latency: median={latency['median_ms']:.2f} ms, "
        f"p95={latency['p95_ms']:.2f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
