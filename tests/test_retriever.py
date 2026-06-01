"""Tests for rag.loader and rag.retriever."""

from __future__ import annotations

import pytest

from rag.loader import load_documents
from rag.retriever import HybridRetriever


@pytest.fixture(scope="module")
def retriever() -> HybridRetriever:
    """Build a real HybridRetriever from rag/data/ documents (module-scoped, built once)."""
    from pathlib import Path
    _index = Path("faiss_index.bin")
    _docs_json = Path("faiss_index.docs.json")
    # Remove stale persisted files so __init__ always builds from the corpus, not disk.
    _index.unlink(missing_ok=True)
    _docs_json.unlink(missing_ok=True)
    docs = load_documents()
    try:
        yield HybridRetriever(docs)
    finally:
        # Remove files written by TestAddDocuments so they do not corrupt future runs.
        _index.unlink(missing_ok=True)
        _docs_json.unlink(missing_ok=True)


# ── Loader tests ──────────────────────────────────────────────────────────────


class TestLoader:
    """Unit tests for rag.loader.load_documents."""

    def test_loads_at_least_ten_chunks(self) -> None:
        """10 markdown files should produce well over 10 paragraph chunks."""
        docs = load_documents()
        assert len(docs) >= 10

    def test_every_chunk_has_source_and_content(self) -> None:
        """Every chunk must carry a .md source name and non-empty content."""
        docs = load_documents()
        for doc in docs:
            assert "source" in doc and "content" in doc
            assert doc["source"].endswith(".md")
            assert len(doc["content"]) >= 60

    def test_all_ten_source_files_present(self) -> None:
        """All 10 knowledge-base files must contribute at least one chunk."""
        expected_sources = {
            "password-reset-runbook.md",
            "vpn-setup-runbook.md",
            "software-install-runbook.md",
            "access-provisioning-runbook.md",
            "incident-response-runbook.md",
            "leave-policy.md",
            "onboarding-policy.md",
            "remote-work-policy.md",
            "equipment-policy.md",
            "offboarding-policy.md",
        }
        sources = {d["source"] for d in load_documents()}
        assert expected_sources == sources


# ── Retriever tests ───────────────────────────────────────────────────────────


class TestRetriever:
    """Integration tests for HybridRetriever.retrieve."""

    def test_retrieve_returns_exactly_top_k(self, retriever: HybridRetriever) -> None:
        """search(top_k=3) returns exactly 3 chunks."""
        results = retriever.search("reset my password", top_k=3)
        assert len(results) == 3

    def test_top_k_one_returns_single_chunk(self, retriever: HybridRetriever) -> None:
        """search(top_k=1) returns exactly 1 chunk."""
        results = retriever.search("software installation request", top_k=1)
        assert len(results) == 1

    def test_chunks_have_required_fields(self, retriever: HybridRetriever) -> None:
        """Every returned chunk must have source (str), content (str), score (float)."""
        results = retriever.search("VPN connection problem", top_k=3)
        for chunk in results:
            assert isinstance(chunk["source"], str)
            assert isinstance(chunk["content"], str)
            assert isinstance(chunk["score"], float)
            assert chunk["source"].endswith(".md")
            assert len(chunk["content"]) > 0

    def test_scores_are_sorted_descending(self, retriever: HybridRetriever) -> None:
        """Results must be ordered by cross-encoder score, highest first."""
        results = retriever.search("approve employee leave request", top_k=3)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not in descending order: {scores}"
        )

    def test_password_reset_query_hits_relevant_doc(self, retriever: HybridRetriever) -> None:
        """A password-reset query must surface password-reset-runbook.md in top-3."""
        results = retriever.search("I forgot my password and need to reset it", top_k=3)
        sources = [r["source"] for r in results]
        assert any("password" in s for s in sources), (
            f"password-reset-runbook not in top-3 results: {sources}"
        )

    def test_access_request_query_hits_relevant_doc(self, retriever: HybridRetriever) -> None:
        """An access-provisioning query must surface access-provisioning-runbook.md in top-3."""
        results = retriever.search("I need access to the production database", top_k=3)
        sources = [r["source"] for r in results]
        assert any("access" in s for s in sources), (
            f"access-provisioning-runbook not in top-3 results: {sources}"
        )

    def test_leave_query_hits_relevant_doc(self, retriever: HybridRetriever) -> None:
        """A leave-request query must surface leave-policy.md in top-3."""
        results = retriever.search("I want to apply for annual leave next week", top_k=3)
        sources = [r["source"] for r in results]
        assert any("leave" in s for s in sources), (
            f"leave-policy not in top-3 results: {sources}"
        )

    def test_retrieved_chunk_content_is_non_trivial(self, retriever: HybridRetriever) -> None:
        """Returned chunk content must be a meaningful paragraph (>= 60 chars)."""
        results = retriever.search("incident severity classification", top_k=3)
        for chunk in results:
            assert len(chunk["content"]) >= 60


# ── add_documents + get() classmethod tests ───────────────────────────────────


class TestAddDocuments:
    """Tests for HybridRetriever.add_documents() and the get() classmethod."""

    def test_get_classmethod_returns_retriever(self) -> None:
        """HybridRetriever.get() returns the module-level singleton."""
        from rag.retriever import HybridRetriever
        r = HybridRetriever.get()
        assert isinstance(r, HybridRetriever)
        assert r is HybridRetriever.get()  # same object on repeated calls

    def test_add_documents_increases_corpus(self) -> None:
        """add_documents() grows _documents, _texts, and the FAISS index by the added count."""
        docs = load_documents()
        r = HybridRetriever(docs[:5])
        initial_doc_count = len(r._documents)
        initial_faiss_count = r._faiss_index.ntotal

        r.add_documents([{"source": "test-extra.md", "content": "Unique content for testing add_documents incremental indexing."}])

        assert len(r._documents) == initial_doc_count + 1
        assert len(r._texts) == initial_doc_count + 1
        assert r._faiss_index.ntotal == initial_faiss_count + 1

    def test_add_documents_noop_on_empty_list(self) -> None:
        """add_documents([]) leaves the corpus unchanged and does not raise."""
        docs = load_documents()
        r = HybridRetriever(docs[:3])
        initial_count = len(r._documents)
        r.add_documents([])
        assert len(r._documents) == initial_count

    def test_add_documents_new_content_searchable(self) -> None:
        """A document added via add_documents() is returned by a subsequent search."""
        docs = load_documents()
        r = HybridRetriever(docs[:5])
        unique_source = "injected-custom-kb.md"
        r.add_documents([{
            "source": unique_source,
            "content": (
                "Maternity leave policy grants twelve weeks of paid leave. "
                "Employees must submit a maternity leave request form to HR "
                "at least eight weeks before the expected due date."
            ),
        }])
        results = r.search("maternity leave request HR form", top_k=3)
        sources = [c["source"] for c in results]
        assert unique_source in sources, f"Injected doc not found in top-3: {sources}"
