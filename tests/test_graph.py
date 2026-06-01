"""Tests for LangGraph node logic and conditional routing."""

import pytest
from datetime import datetime, timezone

from agents.action_node import action_node
from agents.graph import _should_escalate, run_ticket


def _base_state(**overrides) -> dict:
    """Return a complete TicketState dict with sensible defaults.

    All Optional fields are pre-filled so individual tests only need to
    override the keys they care about.
    """
    base: dict = {
        "ticket_id": "test-ticket-001",
        "user_id": "test-user@corp.com",
        "created_at": datetime.now(timezone.utc),
        "trace_id": "test-trace-001",
        "channel": "text",
        "raw_text": "I forgot my password",
        "raw_image_b64": None,
        "extracted_text": None,
        "category": "password_reset",
        "intent": "password_reset",
        "priority": "MEDIUM",
        "confidence": 0.92,
        "entities": {"username": "test-user@corp.com"},
        "retrieved_chunks": None,
        "resolution_template": "Password reset initiated for {username}.",
        "action_taken": None,
        "action_result": None,
        "action_confirmed": None,
        "resolution": None,
        "escalated": None,
        "escalation_reason": None,
        "assignee_group": None,
        "status": "acting",
        "error": None,
        "trace_url": None,
    }
    return {**base, **overrides}


class TestRouting:
    """Unit tests for the _should_escalate conditional edge function."""

    def test_intake_routes_correctly_high_confidence(self) -> None:
        """confidence=0.92 with a valid category routes to __end__."""
        state = _base_state(confidence=0.92, category="password_reset", status="resolved")
        assert _should_escalate(state) == "__end__"

    def test_escalation_triggers_on_low_confidence(self) -> None:
        """confidence=0.4 (below 0.6 threshold) routes to escalation_node."""
        state = _base_state(confidence=0.4, status="acting")
        assert _should_escalate(state) == "escalation_node"

    def test_escalation_triggers_on_unknown_category(self) -> None:
        """category='unknown' routes to escalation_node regardless of confidence."""
        state = _base_state(category="unknown", confidence=0.9, status="acting")
        assert _should_escalate(state) == "escalation_node"

    def test_escalation_triggers_on_escalated_status(self) -> None:
        """status='escalated' (set by action_node on error) routes to escalation_node."""
        state = _base_state(status="escalated", confidence=0.9)
        assert _should_escalate(state) == "escalation_node"

    def test_confidence_exactly_at_threshold_does_not_escalate(self) -> None:
        """confidence=0.6 is not below threshold — should not escalate."""
        state = _base_state(confidence=0.6, status="resolved")
        assert _should_escalate(state) == "__end__"

    def test_awaiting_confirmation_routes_to_end(self) -> None:
        """status='awaiting_confirmation' exits the graph without calling escalation_node."""
        state = _base_state(status="awaiting_confirmation", confidence=0.9)
        assert _should_escalate(state) == "__end__"


class TestActionNode:
    """Tests for action_node destructive-action guard and resolution rendering."""

    @pytest.mark.asyncio
    async def test_destructive_action_requires_confirmation(self) -> None:
        """Destructive intent without confirmation → status=awaiting_confirmation."""
        state = _base_state(intent="access_revoke", action_confirmed=None)
        result = await action_node(state)

        assert result["status"] == "awaiting_confirmation"
        assert result["action_confirmed"] is False
        assert result["error"] is not None
        assert "confirm" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_destructive_action_with_explicit_confirmation_proceeds(self) -> None:
        """Destructive intent WITH action_confirmed=True bypasses the guard."""
        state = _base_state(intent="access_revoke", action_confirmed=True)
        result = await action_node(state)

        assert result["status"] == "resolved"
        assert result["action_taken"] == "access_revoke_executed"
        assert result["action_confirmed"] is True

    @pytest.mark.asyncio
    async def test_user_id_used_as_username_fallback(self) -> None:
        """Stub 'unknown' in entities → state['user_id'] appears in resolution."""
        state = _base_state(
            user_id="jdoe@corp.com",
            entities={"username": "unknown"},
        )
        result = await action_node(state)
        assert "jdoe@corp.com" in result["resolution"]

    @pytest.mark.asyncio
    async def test_extracted_entity_overrides_user_id_fallback(self) -> None:
        """Real NLP-extracted username overrides the user_id fallback."""
        state = _base_state(
            user_id="jdoe@corp.com",
            entities={"username": "john.doe"},
        )
        result = await action_node(state)
        assert "john.doe" in result["resolution"]
        assert "jdoe@corp.com" not in result["resolution"]

    @pytest.mark.asyncio
    async def test_non_destructive_intent_resolves_without_confirmation(self) -> None:
        """Non-destructive intent resolves even with action_confirmed=None."""
        state = _base_state(intent="password_reset", action_confirmed=None)
        result = await action_node(state)
        assert result["status"] == "resolved"


class TestFullGraph:
    """End-to-end smoke tests through run_ticket()."""

    @pytest.mark.asyncio
    async def test_full_graph_smoke(self) -> None:
        """run_ticket returns a valid final status."""
        result = await run_ticket("I forgot my password", "test-user-001", "text")
        assert result["status"] in ("resolved", "escalated", "awaiting_confirmation")

    @pytest.mark.asyncio
    async def test_full_graph_populates_all_key_fields(self) -> None:
        """All expected output fields are non-None after the graph runs."""
        result = await run_ticket("I forgot my password", "test-user-002", "text")
        assert result["ticket_id"] is not None
        assert result["category"] is not None
        assert result["created_at"] is not None
        assert result["intent"] is not None
        assert result["confidence"] is not None
        assert result["retrieved_chunks"] is not None
        assert len(result["retrieved_chunks"]) > 0

    @pytest.mark.asyncio
    async def test_full_graph_user_id_in_resolution(self) -> None:
        """The authenticated user's ID appears in the resolved ticket."""
        result = await run_ticket("I forgot my password", "alice@corp.com", "text")
        if result["status"] == "resolved":
            assert "alice@corp.com" in result["resolution"]
