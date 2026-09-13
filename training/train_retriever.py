"""Fine-tune the bi-encoder on (anchor, positive, negative) triples."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-model", default="intfloat/e5-small-v2")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    try:
        from datasets import load_dataset
        from sentence_transformers import (
            SentenceTransformer,
            SentenceTransformerTrainer,
            SentenceTransformerTrainingArguments,
        )
        from sentence_transformers.losses import TripletLoss
    except ImportError as exc:
        raise SystemExit('Training requires: pip install -e ".[training]"') from exc

    dataset = load_dataset("json", data_files=str(args.data), split="train")
    dataset = dataset.select_columns(["anchor", "positive", "negative"])
    model = SentenceTransformer(args.base_model)
    loss = TripletLoss(model=model)
    training_args = SentenceTransformerTrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=0.1,
        save_strategy="epoch",
        logging_steps=10,
        seed=args.seed,
        report_to="none",
    )
    trainer = SentenceTransformerTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        loss=loss,
    )
    trainer.train()
    model.save_pretrained(str(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
