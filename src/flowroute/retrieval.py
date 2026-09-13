"""First-stage candidate retrieval backends."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Sequence
from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import RetrievalHit, WorkflowContract
from .serialization import normalize_text, serialize_capability


class Retriever(Protocol):
    model_version: str
    production_capable: bool

    def prepare(self, workflows: Sequence[WorkflowContract]) -> None: ...

    def rank(
        self, query: str, workflows: Sequence[WorkflowContract], *, top_k: int
    ) -> list[RetrievalHit]: ...


class TfidfRetriever:
    """Prepared lexical baseline for development and regression testing.

    The catalog index is fitted once and reused across requests. This fixes the
    request-time fitting behavior of v0.1, but the backend remains a lexical
    baseline and is intentionally rejected by production mode.
    """

    model_version = "tfidf-indexed-word-char-0.2.0"
    production_capable = False

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._word: TfidfVectorizer | None = None
        self._char: TfidfVectorizer | None = None
        self._word_docs = None
        self._char_docs = None
        self._workflow_ids: tuple[str, ...] = ()
        self._document_hashes: dict[str, str] = {}
        self._index_fingerprint: str | None = None
        self._index_build_count = 0

    @staticmethod
    def _vectorizers() -> tuple[TfidfVectorizer, TfidfVectorizer]:
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
        return word, char

    @staticmethod
    def _document_hash(document: str) -> str:
        return hashlib.sha256(document.encode("utf-8")).hexdigest()

    @property
    def index_fingerprint(self) -> str | None:
        return self._index_fingerprint

    @property
    def index_build_count(self) -> int:
        return self._index_build_count

    def prepare(self, workflows: Sequence[WorkflowContract]) -> None:
        if not workflows:
            raise ValueError("cannot prepare an empty workflow index")
        documents = [serialize_capability(item) for item in workflows]
        workflow_ids = tuple(item.id for item in workflows)
        document_hashes = {
            workflow_id: self._document_hash(document)
            for workflow_id, document in zip(workflow_ids, documents, strict=True)
        }
        fingerprint_input = "\n".join(
            f"{workflow_id}:{document_hashes[workflow_id]}" for workflow_id in workflow_ids
        )
        fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
        with self._lock:
            if fingerprint == self._index_fingerprint:
                return
            word, char = self._vectorizers()
            word_docs = word.fit_transform(documents)
            char_docs = char.fit_transform(documents)
            self._word = word
            self._char = char
            self._word_docs = word_docs
            self._char_docs = char_docs
            self._workflow_ids = workflow_ids
            self._document_hashes = document_hashes
            self._index_fingerprint = fingerprint
            self._index_build_count += 1

    def _is_prepared_for(self, workflows: Sequence[WorkflowContract]) -> bool:
        if self._index_fingerprint is None:
            return False
        return all(
            item.id in self._document_hashes
            and self._document_hashes[item.id]
            == self._document_hash(serialize_capability(item))
            for item in workflows
        )

    def rank(
        self, query: str, workflows: Sequence[WorkflowContract], *, top_k: int
    ) -> list[RetrievalHit]:
        if not workflows:
            return []
        if not self._is_prepared_for(workflows):
            self.prepare(workflows)
        clean_query = normalize_text(query)
        with self._lock:
            if (
                self._word is None
                or self._char is None
                or self._word_docs is None
                or self._char_docs is None
            ):
                raise RuntimeError("retriever index is not prepared")
            index_by_id = {
                workflow_id: index for index, workflow_id in enumerate(self._workflow_ids)
            }
            selected = [index_by_id[item.id] for item in workflows]
            word_query = self._word.transform([clean_query])
            char_query = self._char.transform([clean_query])
            word_scores = cosine_similarity(word_query, self._word_docs[selected])[0]
            char_scores = cosine_similarity(char_query, self._char_docs[selected])[0]
        scores = np.clip((0.65 * word_scores) + (0.35 * char_scores), 0.0, 1.0)
        limit = max(1, min(top_k, len(workflows)))
        ranked = np.argsort(-scores, kind="stable")[:limit]
        return [
            RetrievalHit(workflow_id=workflows[index].id, score=float(scores[index]), rank=rank + 1)
            for rank, index in enumerate(ranked)
        ]
