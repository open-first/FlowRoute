"""Lazy Hugging Face model adapters.

These classes keep heavyweight ML dependencies optional. Install the ``hf``
extra before constructing either adapter.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Sequence

import numpy as np

from ..inputs import resolve_required_inputs
from ..models import CandidateScore, RetrievalHit, VerificationLabel, WorkflowContract
from ..serialization import serialize_capability, serialize_contract


class HuggingFaceBackendUnavailable(RuntimeError):
    pass


def _require_sentence_transformers():
    try:
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError as exc:
        raise HuggingFaceBackendUnavailable(
            'Hugging Face backends require: pip install -e ".[hf]"'
        ) from exc
    return SentenceTransformer, CrossEncoder


class HuggingFaceRetriever:
    production_capable = True

    def __init__(
        self,
        model_name_or_path: str,
        *,
        model_version: str | None = None,
        query_prefix: str = "",
        document_prefix: str = "",
    ):
        SentenceTransformer, _ = _require_sentence_transformers()
        self.model = SentenceTransformer(model_name_or_path)
        self.model_version = model_version or model_name_or_path
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self._cache: dict[str, np.ndarray] = {}
        self._lock = threading.RLock()

    def prepare(self, workflows: Sequence[WorkflowContract]) -> None:
        pending: list[tuple[str, str]] = []
        with self._lock:
            for contract in workflows:
                text = self.document_prefix + serialize_capability(contract)
                key = hashlib.sha256(f"{self.model_version}\0{text}".encode()).hexdigest()
                if key not in self._cache:
                    pending.append((key, text))
            if not pending:
                return
            encoded = self.model.encode(
                [text for _, text in pending],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            for (key, _), vector in zip(pending, encoded, strict=True):
                self._cache[key] = np.asarray(vector)

    def _embedding(self, contract: WorkflowContract) -> np.ndarray:
        text = self.document_prefix + serialize_capability(contract)
        key = hashlib.sha256(f"{self.model_version}\0{text}".encode()).hexdigest()
        with self._lock:
            if key not in self._cache:
                self._cache[key] = self.model.encode(
                    text, normalize_embeddings=True, convert_to_numpy=True
                )
            return self._cache[key]

    def rank(
        self, query: str, workflows: Sequence[WorkflowContract], *, top_k: int
    ) -> list[RetrievalHit]:
        if not workflows:
            return []
        with self._lock:
            query_vector = self.model.encode(
                self.query_prefix + query, normalize_embeddings=True, convert_to_numpy=True
            )
            matrix = np.vstack([self._embedding(item) for item in workflows])
        # Normalized vectors make dot product cosine similarity. Convert from
        # [-1, 1] to a stable [0, 1] interface score.
        raw = matrix @ query_vector
        scores = np.clip((raw + 1.0) / 2.0, 0.0, 1.0)
        ranked = np.argsort(-scores, kind="stable")[: max(1, min(top_k, len(workflows)))]
        return [
            RetrievalHit(workflow_id=workflows[index].id, score=float(scores[index]), rank=rank + 1)
            for rank, index in enumerate(ranked)
        ]


class HuggingFaceCrossEncoderVerifier:
    """Adapter for a three-class checkpoint: mismatch, needs_input, executable."""

    production_capable = True

    def __init__(
        self,
        model_name_or_path: str,
        *,
        model_version: str | None = None,
        label_order: tuple[str, str, str] = ("mismatch", "needs_input", "executable"),
    ) -> None:
        _, CrossEncoder = _require_sentence_transformers()
        self.model = CrossEncoder(model_name_or_path, num_labels=3)
        self.model_version = model_version or model_name_or_path
        self.label_order = tuple(VerificationLabel(item) for item in label_order)
        if set(self.label_order) != set(VerificationLabel):
            raise ValueError(
                "label_order must contain mismatch, needs_input, and executable exactly once"
            )
        self._lock = threading.RLock()

    @staticmethod
    def _softmax(values: np.ndarray) -> np.ndarray:
        shifted: np.ndarray = values - np.max(values)
        exp = np.exp(shifted)
        return exp / exp.sum()

    def verify(
        self,
        query: str,
        context: dict[str, object],
        contract: WorkflowContract,
        retrieval: RetrievalHit,
    ) -> CandidateScore:
        return self.verify_many(query, context, [(contract, retrieval)])[0]

    def verify_many(
        self,
        query: str,
        context: dict[str, object],
        pairs: Sequence[tuple[WorkflowContract, RetrievalHit]],
    ) -> list[CandidateScore]:
        if not pairs:
            return []
        with self._lock:
            raw = np.asarray(
                self.model.predict(
                    [(query, serialize_contract(contract)) for contract, _ in pairs]
                )
            )
        if raw.ndim == 1 and len(pairs) == 1:
            raw = raw.reshape(1, -1)
        if raw.shape != (len(pairs), 3):
            raise ValueError("verifier checkpoint must return three logits")
        candidates: list[CandidateScore] = []
        for logits, (contract, retrieval) in zip(raw, pairs, strict=True):
            probabilities = self._softmax(logits)
            scores = {
                label: float(probabilities[index])
                for index, label in enumerate(self.label_order)
            }
            resolution = resolve_required_inputs(contract, query, context)
            reason_codes = ["CROSS_ENCODER_SCORED"]
            reason_codes.extend(
                f"EXTRACTION_TIMEOUT:{name}"
                for name in resolution.extraction_timeouts
            )
            if resolution.missing:
                # Typed schema completeness is authoritative. A semantic model
                # may not declare an incomplete call executable.
                moved = scores[VerificationLabel.EXECUTABLE]
                scores[VerificationLabel.EXECUTABLE] = 0.0
                scores[VerificationLabel.NEEDS_INPUT] = min(
                    1.0, scores[VerificationLabel.NEEDS_INPUT] + moved
                )
                reason_codes.extend(f"MISSING:{name}" for name in resolution.missing)
            label = max(scores, key=lambda item: scores[item])
            candidates.append(
                CandidateScore(
                    workflow_id=contract.id,
                    risk_tier=contract.risk_tier,
                    retrieval_score=retrieval.score,
                    executable_score=scores[VerificationLabel.EXECUTABLE],
                    needs_input_score=scores[VerificationLabel.NEEDS_INPUT],
                    mismatch_score=scores[VerificationLabel.MISMATCH],
                    label=label,
                    missing_inputs=resolution.missing,
                    reason_codes=reason_codes,
                )
            )
        return candidates
