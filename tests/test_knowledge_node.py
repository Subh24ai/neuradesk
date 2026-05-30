"""Tests for agents.knowledge_node — retriever and LLM calls are mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from agents.knowledge_node import knowledge_node
from agents.state import RetrievedChunk, TicketState


# ── Helpers ───────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> TicketState:
    """Return a complete TicketState ready for knowledge_node."""
    base: dict = {
        "ticket_id": "test-knowledge-001",
        "user_id": "test-user@corp.com",
        "created_at": None,
        "trace_id": "test-trace-001",
        "channel": "text",
        "raw_text": "I forgot my password and cannot log in",
        "raw_image_b64": None,
        "extracted_text": None,
        "category": "password_reset",
        "intent": "password_reset",
        "priority": "MEDIUM",
        "confidence": 0.92,
        "entities": {"username": "test-user@corp.com"},
        "retrieved_chunks": None,
        "resolution_template": None,
        "action_taken": None,
        "action_result": None,
        "action_confirmed": None,
        "resolution": None,
        "escalated": None,
        "escalation_reason": None,
        "assignee_group": None,
        "status": "retrieving",
        "error": None,
        "trace_url": None,
    }
    return {**base, **overrides}  # type: ignore[return-value]


def _make_chunks(n: int = 3) -> list[RetrievedChunk]:
    """Return n fake RetrievedChunk dicts."""
    return [
        {
            "source": f"password-reset-runbook.md",
            "content": f"To reset your password, navigate to the IT Self-Service Portal (chunk {i}).",
            "score": 0.9 - i * 0.1,
        }
        for i in range(n)
    ]


def _mock_retriever(chunks: list[RetrievedChunk]) -> MagicMock:
    """Return a mock retriever whose .search() returns chunks."""
    r = MagicMock()
    r.search.return_value = chunks
    return r


def _mock_llm(content: str) -> MagicMock:
    """Return a mock LangChain LLM whose .invoke() returns content."""
    response = MagicMock()
    response.content = content
    lm = MagicMock()
    lm.invoke.return_value = response
    return lm


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestKnowledgeNode:
    """Unit tests for knowledge_node."""

    def test_knowledge_node_populates_chunks(self) -> None:
        """retrieved_chunks in state matches what the retriever returned."""
        chunks = _make_chunks(3)
        state = _base_state()

        with (
            patch("agents.knowledge_node.get_retriever", return_value=_mock_retriever(chunks)),
            patch("agents.knowledge_node.get_llm", return_value=_mock_llm("Reset via IT Portal for {username}.")),
        ):
            result = knowledge_node(state)

        assert result["retrieved_chunks"] == chunks
        assert len(result["retrieved_chunks"]) == 3
        assert result["status"] == "acting"

    def test_knowledge_node_generates_resolution(self) -> None:
        """state['resolution'] contains the LLM response content."""
        chunks = _make_chunks(1)
        llm_text = "Please reset your password at the IT Self-Service Portal for {username}."
        state = _base_state()

        with (
            patch("agents.knowledge_node.get_retriever", return_value=_mock_retriever(chunks)),
            patch("agents.knowledge_node.get_llm", return_value=_mock_llm(llm_text)),
        ):
            result = knowledge_node(state)

        assert result["resolution"] == llm_text
        assert result["resolution_template"] is not None

    def test_empty_retrieval_triggers_escalation(self) -> None:
        """Empty retrieval sets confidence to 0.3 (graph router escalates on < 0.6)."""
        state = _base_state()

        with patch("agents.knowledge_node.get_retriever", return_value=_mock_retriever([])):
            result = knowledge_node(state)

        assert result["confidence"] == pytest.approx(0.3)
        assert result["retrieved_chunks"] == []
        assert result["status"] == "acting"

    def test_query_built_from_category_and_text(self) -> None:
        """The query passed to retriever.search() starts with category then ticket text."""
        chunks = _make_chunks(1)
        mock_ret = _mock_retriever(chunks)
        state = _base_state(
            category="password_reset",
            raw_text="I forgot my password and cannot log in",
            extracted_text=None,
        )

        with (
            patch("agents.knowledge_node.get_retriever", return_value=mock_ret),
            patch("agents.knowledge_node.get_llm", return_value=_mock_llm("Reset for {username}.")),
        ):
            knowledge_node(state)

        query_used: str = mock_ret.search.call_args[0][0]
        assert query_used.startswith("password_reset")
        assert "forgot my password" in query_used

    def test_resolution_template_contains_username_placeholder(self) -> None:
        """resolution_template always contains {username} even if LLM omits it."""
        chunks = _make_chunks(1)
        # LLM deliberately omits {username}
        llm_text = "Reset your password via the IT Self-Service Portal."
        state = _base_state()

        with (
            patch("agents.knowledge_node.get_retriever", return_value=_mock_retriever(chunks)),
            patch("agents.knowledge_node.get_llm", return_value=_mock_llm(llm_text)),
        ):
            result = knowledge_node(state)

        assert "{username}" in result["resolution_template"]

    def test_llm_error_falls_back_to_chunk_content(self) -> None:
        """LLM exception causes graceful fallback to the raw top-chunk content."""
        chunks = _make_chunks(1)
        mock_lm = MagicMock()
        mock_lm.invoke.side_effect = RuntimeError("network error")
        state = _base_state()

        with (
            patch("agents.knowledge_node.get_retriever", return_value=_mock_retriever(chunks)),
            patch("agents.knowledge_node.get_llm", return_value=mock_lm),
        ):
            result = knowledge_node(state)

        # Falls back to chunk content — node must not raise.
        assert result["retrieved_chunks"] is not None
        assert result["status"] == "acting"

    def test_low_rag_score_triggers_escalation(self) -> None:
        """A top-chunk cross-encoder score below 0.35 sets confidence to 0.3.

        Covers the case where a ticket is completely outside the KB — e.g.
        'book me a flight to Dubai'.  The retriever may return chunks but the
        reranker assigns sub-threshold scores, so the node should downgrade
        confidence so the graph router escalates instead of hallucinating a
        resolution.
        """
        off_topic_chunks: list[RetrievedChunk] = [
            {"source": "password-reset-runbook.md", "content": "Reset via IT portal.", "score": 0.10},
            {"source": "leave-policy.md", "content": "Leave requests go via HR.", "score": 0.05},
        ]
        state = _base_state(
            raw_text="Please book me a flight to Dubai next Friday",
            category="unknown",
        )

        with patch("agents.knowledge_node.get_retriever", return_value=_mock_retriever(off_topic_chunks)):
            result = knowledge_node(state)

        assert result["confidence"] == pytest.approx(0.3), (
            "Off-topic ticket with sub-threshold score must have confidence 0.3 so the graph escalates"
        )
        assert result["status"] == "acting"
        assert result["retrieved_chunks"] == off_topic_chunks

    def test_extracted_text_preferred_over_raw_text_for_query(self) -> None:
        """When extracted_text is set (image ticket), it is used in the query."""
        chunks = _make_chunks(1)
        mock_ret = _mock_retriever(chunks)
        state = _base_state(
            raw_text="Screenshot of error",
            extracted_text="User sees 'Invalid credentials' on the SSO login page.",
        )

        with (
            patch("agents.knowledge_node.get_retriever", return_value=mock_ret),
            patch("agents.knowledge_node.get_llm", return_value=_mock_llm("Reset for {username}.")),
        ):
            knowledge_node(state)

        query_used: str = mock_ret.search.call_args[0][0]
        assert "Invalid credentials" in query_used
        assert "Screenshot" not in query_used
