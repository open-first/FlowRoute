import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from flowroute import RetrievalHit, VerificationLabel, WorkflowRegistry
from flowroute.backends.huggingface import (
    HuggingFaceCrossEncoderVerifier,
    HuggingFaceRetriever,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeSentenceTransformer:
    def __init__(self, model_name_or_path):
        self.model_name_or_path = model_name_or_path
        self.calls = []

    def encode(self, values, **_kwargs):
        self.calls.append(values)

        def vector(value):
            return np.array([1.0, 0.0]) if "order" in value.lower() else np.array([0.0, 1.0])

        if isinstance(values, str):
            return vector(values)
        return np.vstack([vector(value) for value in values])


class FakeCrossEncoder:
    def __init__(self, model_name_or_path, *, num_labels):
        self.model_name_or_path = model_name_or_path
        self.num_labels = num_labels
        self.calls = []

    def predict(self, pairs):
        self.calls.append(pairs)
        return np.array([[0.0, 0.0, 8.0] for _ in pairs])


class LearnedBackendTests(unittest.TestCase):
    def setUp(self):
        self.registry = WorkflowRegistry.from_yaml(ROOT / "examples" / "workflows.yaml")

    @patch(
        "flowroute.backends.huggingface._require_sentence_transformers",
        return_value=(FakeSentenceTransformer, FakeCrossEncoder),
    )
    def test_retriever_prepares_catalog_once_and_reuses_embeddings(self, _dependency_loader):
        workflows = self.registry.active_workflows()[:3]
        retriever = HuggingFaceRetriever(
            "local-retriever",
            model_version="retriever-release-1",
            query_prefix="query::",
            document_prefix="document::",
        )

        retriever.prepare(workflows)
        retriever.prepare(workflows)
        hits = retriever.rank("Where is my order?", workflows, top_k=2)

        self.assertEqual(hits[0].workflow_id, "orders.get_status")
        self.assertEqual(len(retriever.model.calls), 2)
        self.assertTrue(
            all(value.startswith("document::") for value in retriever.model.calls[0])
        )
        self.assertTrue(retriever.model.calls[1].startswith("query::"))

    @patch(
        "flowroute.backends.huggingface._require_sentence_transformers",
        return_value=(FakeSentenceTransformer, FakeCrossEncoder),
    )
    def test_verifier_batches_pairs_and_schema_overrides_executable_logit(
        self, _dependency_loader
    ):
        contract = self.registry.get("orders.get_status")
        assert contract is not None
        verifier = HuggingFaceCrossEncoderVerifier(
            "local-verifier",
            model_version="verifier-release-1",
        )

        missing = verifier.verify_many(
            "Check the order",
            {},
            [(contract, RetrievalHit(workflow_id=contract.id, score=0.9, rank=1))],
        )
        complete = verifier.verify_many(
            "Check the order",
            {"order_id": "4812"},
            [(contract, RetrievalHit(workflow_id=contract.id, score=0.9, rank=1))],
        )

        self.assertEqual(missing[0].label, VerificationLabel.NEEDS_INPUT)
        self.assertEqual(missing[0].executable_score, 0.0)
        self.assertEqual(missing[0].missing_inputs, ["order_id"])
        self.assertEqual(complete[0].label, VerificationLabel.EXECUTABLE)
        self.assertEqual(len(verifier.model.calls), 2)

    @patch(
        "flowroute.backends.huggingface._require_sentence_transformers",
        return_value=(FakeSentenceTransformer, FakeCrossEncoder),
    )
    def test_verifier_rejects_duplicate_label_mapping(self, _dependency_loader):
        with self.assertRaises(ValueError):
            HuggingFaceCrossEncoderVerifier(
                "local-verifier",
                label_order=("mismatch", "mismatch", "executable"),
            )


if __name__ == "__main__":
    unittest.main()
