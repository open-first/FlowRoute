"""Fine-tune a three-way request/contract cross-encoder verifier."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-model", default="cross-encoder/ms-marco-MiniLM-L6-v2")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    try:
        import numpy as np
        from datasets import load_dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            DataCollatorWithPadding,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit('Training requires: pip install -e ".[training]"') from exc

    dataset = load_dataset("json", data_files=str(args.data), split="train")
    split = dataset.train_test_split(test_size=0.15, seed=args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)

    def tokenize(batch):
        return tokenizer(batch["query"], batch["contract"], truncation=True, max_length=512)

    removable = [column for column in dataset.column_names if column != "label"]
    tokenized = split.map(tokenize, batched=True, remove_columns=removable)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=3,
        id2label={0: "mismatch", 1: "needs_input", 2: "executable"},
        label2id={"mismatch": 0, "needs_input": 1, "executable": 2},
        ignore_mismatched_sizes=True,
    )

    def metrics(prediction):
        predicted = np.argmax(prediction.predictions, axis=-1)
        return {"accuracy": float((predicted == prediction.label_ids).mean())}

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        seed=args.seed,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["test"],
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=metrics,
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
