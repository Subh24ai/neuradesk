"""Hybrid FAISS + BM25 retriever with cross-encoder reranking."""

from __future__ import annotations

import hashlib
import threading
from typing import Optional

import numpy as np
import structlog
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

import faiss  # type: ignore[import-untyped]

from agents.state import RetrievedChunk
from rag.loader import Document, load_documents

log = structlog.get_logger(__name__)

_EMBED_MODEL: str = "all-MiniLM-L6-v2"
_CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# Candidates drawn from each retrieval stage before reranking.
_STAGE_CANDIDATES: int = 10


class HybridRetriever:
    """FAISS dense + BM25 sparse retriever with cross-encoder reranking.

    Retrieval is a three-stage pipeline:
      1. Dense recall  — FAISS inner-product search on L2-normalised embeddings.
      2. Sparse recall — BM25 keyword scoring.
      3. Reranking     — cross-encoder scores the union of candidates; top-k returned.
    """

    def __init__(self, documents: list[Document]) -> None:
        """Build all three indices from the provided document list.

        Args:
            documents: Flat list of Document dicts (source + content).

        Raises:
            ValueError: If documents is empty.
        """
        if not documents:
            raise ValueError("Cannot build a retriever from an empty document list.")

        self._documents: list[Document] = documents
        self._texts: list[str] = [d["content"] for d in documents]
        self._lock: threading.Lock = threading.Lock()

        log.info("retriever.build_start", num_docs=len(documents))

        # ── Dense index (FAISS) ──────────────────────────────────────────────
        self._embedder: SentenceTransformer = SentenceTransformer(_EMBED_MODEL)
        embeddings: np.ndarray = self._embedder.encode(
            self._texts, show_progress_bar=False, convert_to_numpy=True
        ).astype(np.float32)
        faiss.normalize_L2(embeddings)  # cosine similarity via inner product
        self._faiss_index: faiss.IndexFlatIP = faiss.IndexFlatIP(embeddings.shape[1])
        self._faiss_index.add(embeddings)

        # ── Sparse index (BM25) ──────────────────────────────────────────────
        tokenized: list[list[str]] = [t.lower().split() for t in self._texts]
        self._bm25: BM25Okapi = BM25Okapi(tokenized)

        # ── Cross-encoder reranker ───────────────────────────────────────────
        self._cross_encoder: CrossEncoder = CrossEncoder(_CROSS_ENCODER_MODEL)

        log.info("retriever.build_done", num_docs=len(documents))

    def search(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Run hybrid retrieval and return the top_k best chunks.

        Args:
            query: Free-text search query from the ticket or agent.
            top_k: Maximum number of chunks to return after reranking.

        Returns:
            List of RetrievedChunk dicts sorted by cross-encoder score descending.
        """
        n_docs = len(self._documents)
        stage_k = min(_STAGE_CANDIDATES, n_docs)

        # ── 1. Dense candidates ──────────────────────────────────────────────
        q_vec: np.ndarray = self._embedder.encode(
            [query], show_progress_bar=False, convert_to_numpy=True
        ).astype(np.float32)
        faiss.normalize_L2(q_vec)
        _scores, dense_idxs = self._faiss_index.search(q_vec, stage_k)
        dense_set: set[int] = set(int(i) for i in dense_idxs[0])

        # ── 2. Sparse candidates ─────────────────────────────────────────────
        bm25_scores: np.ndarray = self._bm25.get_scores(query.lower().split())
        sparse_set: set[int] = set(
            int(i) for i in np.argsort(bm25_scores)[::-1][:stage_k]
        )

        # ── 3. Deduplicate union by content hash ─────────────────────────────
        candidate_idxs: list[int] = []
        seen: set[str] = set()
        for idx in dense_set | sparse_set:
            h = hashlib.md5(self._texts[idx].encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                candidate_idxs.append(idx)

        # ── 4. Cross-encoder reranking ───────────────────────────────────────
        pairs: list[tuple[str, str]] = [(query, self._texts[i]) for i in candidate_idxs]
        ce_scores: list[float] = self._cross_encoder.predict(pairs).tolist()

        ranked = sorted(zip(candidate_idxs, ce_scores), key=lambda x: x[1], reverse=True)

        results: list[RetrievedChunk] = [
            {
                "source": self._documents[idx]["source"],
                "content": self._texts[idx],
                "score": float(score),
            }
            for idx, score in ranked[:top_k]
        ]

        log.info(
            "retriever.retrieve_done",
            query_preview=query[:80],
            num_candidates=len(candidate_idxs),
            top_k=top_k,
        )
        return results

    def add_documents(self, documents: list[Document]) -> None:
        """Incrementally add documents to the live FAISS and BM25 indices.

        FAISS IndexFlatIP supports incremental add; BM25 is rebuilt from the
        full corpus because IDF scores depend on global document frequency.
        Thread-safe via an instance-level lock.

        Args:
            documents: New documents to index. Empty list is a no-op.
        """
        if not documents:
            return
        with self._lock:
            new_texts = [d["content"] for d in documents]

            # Embed and add to FAISS incrementally.
            new_embeddings: np.ndarray = self._embedder.encode(
                new_texts, show_progress_bar=False, convert_to_numpy=True
            ).astype(np.float32)
            faiss.normalize_L2(new_embeddings)
            self._faiss_index.add(new_embeddings)

            # Extend in-memory corpus lists.
            self._documents.extend(documents)
            self._texts.extend(new_texts)

            # BM25 IDF depends on corpus size — rebuild from the full corpus.
            self._bm25 = BM25Okapi([t.lower().split() for t in self._texts])

        log.info(
            "retriever.add_documents",
            num_added=len(documents),
            total=len(self._documents),
        )

    @classmethod
    def get(cls) -> "HybridRetriever":
        """Return the module-level singleton, initialising it on first call."""
        return get_retriever()


# ── Module-level singleton ────────────────────────────────────────────────────

_retriever: Optional[HybridRetriever] = None
_init_lock: threading.Lock = threading.Lock()


def get_retriever() -> HybridRetriever:
    """Return the module-level HybridRetriever singleton, building it on first call.

    The index is built once per process from rag/data/*.md documents.
    Subsequent calls return the cached instance. Thread-safe via double-checked locking.
    """
    global _retriever
    if _retriever is None:
        with _init_lock:
            if _retriever is None:
                docs = load_documents()
                _retriever = HybridRetriever(docs)
    return _retriever
