"""Second-stage request/contract verification backends."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .inputs import resolve_required_inputs
from .models import CandidateScore, RetrievalHit, VerificationLabel, WorkflowContract


class Verifier(Protocol):
    model_version: str
    production_capable: bool

    def verify(
        self,
        query: str,
        context: dict[str, object],
        contract: WorkflowContract,
        retrieval: RetrievalHit,
    ) -> CandidateScore: ...

    def verify_many(
        self,
        query: str,
        context: dict[str, object],
        pairs: Sequence[tuple[WorkflowContract, RetrievalHit]],
    ) -> list[CandidateScore]: ...


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _pair_similarity(left: str, right: str) -> float:
    if not left.strip() or not right.strip():
        return 0.0
    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        analyzer="char_wb",
        ngram_range=(3, 5),
    )
    vectors = vectorizer.fit_transform([left, right])
    return float(cosine_similarity(vectors[0], vectors[1])[0, 0])


class LexicalVerifier:
    """Transparent verifier for wiring and baseline evaluation.

    It intentionally does not pretend to be a semantic model. Replace it with
    a trained three-way cross-encoder for research or production evaluation.
    """

    model_version = "lexical-verifier-0.1.0"
    production_capable = False

    def verify(
        self,
        query: str,
        context: dict[str, object],
        contract: WorkflowContract,
        retrieval: RetrievalHit,
    ) -> CandidateScore:
        exclusion_score = max(
            (_pair_similarity(query, item) for item in contract.exclusions), default=0.0
        )
        positive_logit = 10.0 * (retrieval.score - 0.22)
        exclusion_penalty = 8.0 * max(0.0, exclusion_score - 0.12)
        semantic_fit = _sigmoid(positive_logit - exclusion_penalty)
        resolution = resolve_required_inputs(contract, query, context)

        reason_codes: list[str] = []
        reason_codes.extend(
            f"EXTRACTION_TIMEOUT:{name}" for name in resolution.extraction_timeouts
        )
        if exclusion_score >= 0.36:
            reason_codes.append("EXCLUSION_SIMILARITY")
        if retrieval.score < 0.08:
            reason_codes.append("WEAK_RETRIEVAL")

        if resolution.missing:
            executable = 0.0
            needs_input = semantic_fit
            mismatch = 1.0 - needs_input
            reason_codes.extend(f"MISSING:{name}" for name in resolution.missing)
        else:
            executable = semantic_fit
            needs_input = 0.0
            mismatch = 1.0 - executable

        probabilities = {
            VerificationLabel.EXECUTABLE: executable,
            VerificationLabel.NEEDS_INPUT: needs_input,
            VerificationLabel.MISMATCH: mismatch,
        }
        label = max(probabilities, key=lambda item: probabilities[item])
        if not reason_codes:
            reason_codes.append("PAIR_SCORED")
        return CandidateScore(
            workflow_id=contract.id,
            risk_tier=contract.risk_tier,
            retrieval_score=retrieval.score,
            executable_score=executable,
            needs_input_score=needs_input,
            mismatch_score=mismatch,
            label=label,
            missing_inputs=resolution.missing,
            reason_codes=reason_codes,
        )

    def verify_many(
        self,
        query: str,
        context: dict[str, object],
        pairs: Sequence[tuple[WorkflowContract, RetrievalHit]],
    ) -> list[CandidateScore]:
        return [
            self.verify(query, context, contract, retrieval)
            for contract, retrieval in pairs
        ]
