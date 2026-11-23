"""Tests for agents.action_node — enterprise HTTP calls are mocked via patch."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from agents.action_node import action_node
from agents.state import TicketState

# ── Helpers ───────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> TicketState:
    """Return a complete TicketState ready for action_node."""
    base: dict = {
        "ticket_id": "test-action-001",
        "user_id": "test-user@corp.com",
        "created_at": datetime.now(UTC),
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
        "resolution_template": "Password reset for {username}.",
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
    return {**base, **overrides}  # type: ignore[return-value]


def _api_success(action: str = "test-action") -> dict:
    """Return a minimal enterprise API success envelope."""
    return {
        "success": True,
        "action": action,
        "destructive": False,
        "result": {
            "temp_password": "TestTmp-abc123!",
            "ticket_ref": "TEST-000001",
        },
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestActionNode:
    """Unit tests for action_node — each test controls the _post_enterprise mock."""

    @pytest.mark.asyncio
    async def test_password_reset_calls_correct_endpoint(self) -> None:
        """password_reset intent POSTs to /itsm/reset-password."""
        state = _base_state(intent="password_reset")

        with patch(
            "agents.action_node._post_enterprise",
            return_value=_api_success("reset-password"),
        ) as mock_post:
            result = await action_node(state)

        mock_post.assert_called_once()
        endpoint: str = mock_post.call_args[0][0]
        assert endpoint == "/itsm/reset-password"
        assert result["status"] == "resolved"
        assert result["action_taken"] == "password_reset_executed"

    @pytest.mark.asyncio
    async def test_access_request_calls_correct_endpoint(self) -> None:
        """access_request intent POSTs to /itsm/provision-access."""
        state = _base_state(
            intent="access_request",
            category="access_request",
        )

        with patch(
            "agents.action_node._post_enterprise",
            return_value=_api_success("provision-access"),
        ) as mock_post:
            result = await action_node(state)

        endpoint: str = mock_post.call_args[0][0]
        assert endpoint == "/itsm/provision-access"
        assert result["status"] == "resolved"
        assert result["action_taken"] == "access_request_executed"

    @pytest.mark.asyncio
    async def test_leave_approval_resolves_without_confirmation(self) -> None:
        """leave_approval is non-destructive — resolves with action_confirmed=None."""
        state = _base_state(
            intent="leave_approval",
            category="leave_approval",
            action_confirmed=None,
        )

        with patch(
            "agents.action_node._post_enterprise",
            return_value=_api_success("approve-leave"),
        ) as mock_post:
            result = await action_node(state)

        endpoint: str = mock_post.call_args[0][0]
        assert endpoint == "/hr/approve-leave"
        assert result["status"] == "resolved"
        assert result["action_confirmed"] is True

    @pytest.mark.asyncio
    async def test_unknown_category_escalates_without_api_call(self) -> None:
        """unknown intent escalates immediately — _post_enterprise must NOT be called."""
        state = _base_state(intent="unknown", category="unknown")

        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)

        mock_post.assert_not_called()
        assert result["status"] == "escalated"
        assert result["escalation_reason"] == "category_unknown"
        assert result["escalated"] is True

    @pytest.mark.asyncio
    async def test_destructive_action_blocked_without_confirmation(self) -> None:
        """Destructive intent without confirmation halts for user confirmation — no API call made."""
        state = _base_state(intent="access_revoke", action_confirmed=None)

        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)

        mock_post.assert_not_called()
        assert result["status"] == "awaiting_confirmation"
        assert result["action_confirmed"] is False
        assert result["error"] is not None
        assert "confirm" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_awaiting_confirmation_status_returned_for_destructive(self) -> None:
        """Destructive intent sets status='awaiting_confirmation' and populates escalation_reason."""
        state = _base_state(intent="account_lock", action_confirmed=None)

        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)

        mock_post.assert_not_called()
        assert result["status"] == "awaiting_confirmation"
        assert result["escalation_reason"] is not None
        assert "account_lock" in result["escalation_reason"]

    @pytest.mark.asyncio
    async def test_api_error_sets_escalated(self) -> None:
        """A network error from the enterprise API sets status=escalated."""
        state = _base_state(intent="incident_report", category="incident_report")

        with patch(
            "agents.action_node._post_enterprise",
            side_effect=RuntimeError("connection refused"),
        ):
            result = await action_node(state)

        assert result["status"] == "escalated"
        assert "connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_username_substituted_in_resolution(self) -> None:
        """{username} in resolution_template is replaced with the AUTHENTICATED user."""
        # Authenticated submitter is jdoe@corp.com; no other user is named.
        state = _base_state(
            intent="password_reset",
            user_id="jdoe@corp.com",
            entities={"username": "jdoe@corp.com"},
            resolution_template="Reset complete for {username}.",
        )

        with patch(
            "agents.action_node._post_enterprise",
            return_value=_api_success(),
        ):
            result = await action_node(state)

        assert "jdoe@corp.com" in result["resolution"]
        assert "{username}" not in result["resolution"]

    @pytest.mark.asyncio
    async def test_action_targets_authenticated_user_not_free_text(self) -> None:
        """The enterprise payload user_id is the JWT identity, never a text-named self-match."""
        # Submitter names their OWN email in the text — payload must use user_id.
        state = _base_state(
            intent="password_reset",
            user_id="alice@corp.com",
            entities={"username": "alice@corp.com"},
        )

        with patch(
            "agents.action_node._post_enterprise",
            return_value=_api_success("reset-password"),
        ) as mock_post:
            result = await action_node(state)

        payload = mock_post.call_args[0][1]
        assert payload["user_id"] == "alice@corp.com"
        assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_third_party_target_escalates_without_api_call(self) -> None:
        """A ticket naming a DIFFERENT user escalates and makes no API call (authz gate)."""
        state = _base_state(
            intent="password_reset",
            user_id="alice@corp.com",
            entities={"username": "victim@corp.com"},  # someone else
        )

        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)

        mock_post.assert_not_called()
        assert result["status"] == "escalated"
        assert "another user" in result["escalation_reason"].lower()

    @pytest.mark.asyncio
    async def test_low_confidence_escalates_before_api_call(self) -> None:
        """Low confidence escalates before any enterprise call (injection/empty-KB safety)."""
        state = _base_state(intent="password_reset", confidence=0.3)

        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)

        mock_post.assert_not_called()
        assert result["status"] == "escalated"


class TestKnowledgeGroundingDecoupled:
    """KB coverage shapes the reply; only triage confidence gates the action."""

    @pytest.mark.asyncio
    async def test_action_runs_without_kb_article(self) -> None:
        """Regression: an org with no password article must still get its reset executed."""
        state = _base_state(intent="password_reset", kb_grounded=False, resolution_template=None)

        with patch(
            "agents.action_node._post_enterprise", return_value=_api_success("reset-password")
        ) as mock_post:
            result = await action_node(state)

        mock_post.assert_called_once()
        assert result["status"] == "resolved"
        assert "temporary password" in result["resolution"]
        assert "test-user@corp.com" in result["resolution"]

    @pytest.mark.asyncio
    async def test_grounded_reply_uses_kb_answer(self) -> None:
        """When the KB answered, the reply is the grounded KB text."""
        state = _base_state(
            intent="password_reset", kb_grounded=True,
            resolution_template="Use the Acme portal at go/reset, {username}.",
        )
        with patch("agents.action_node._post_enterprise", return_value=_api_success()):
            result = await action_node(state)
        assert result["resolution"] == "Use the Acme portal at go/reset, test-user@corp.com."

    @pytest.mark.asyncio
    async def test_stray_braces_in_kb_text_do_not_crash(self) -> None:
        """LLM text containing other {braces} is rendered safely (str.format would raise)."""
        state = _base_state(
            intent="password_reset", kb_grounded=True,
            resolution_template="Run `reset {--all}` then sign in, {username}. Use {curly} freely.",
        )
        with patch("agents.action_node._post_enterprise", return_value=_api_success()):
            result = await action_node(state)
        assert result["status"] == "resolved"
        assert "{--all}" in result["resolution"] and "test-user@corp.com" in result["resolution"]

    @pytest.mark.asyncio
    async def test_policy_question_answered_from_kb_without_api_call(self) -> None:
        """An 'unknown' ticket the org KB answers is resolved as information — no API call."""
        state = _base_state(
            intent="unknown", category="unknown", confidence=0.9, kb_grounded=True,
            resolution_template="You get 30 days of annual leave; request it in BambooHR, {username}.",
        )
        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)
        mock_post.assert_not_called()
        assert result["status"] == "resolved"
        assert result["action_taken"] == "knowledge_answer"
        assert "30 days" in result["resolution"]

    @pytest.mark.asyncio
    async def test_unknown_without_kb_answer_escalates(self) -> None:
        """No KB answer → an unknown ticket still escalates to a human."""
        state = _base_state(intent="unknown", category="unknown", confidence=0.9, kb_grounded=False)
        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)
        mock_post.assert_not_called()
        assert result["status"] == "escalated"

    @pytest.mark.asyncio
    async def test_suspicious_unknown_is_not_answered_even_if_kb_matches(self) -> None:
        """Injection-capped confidence (0.3) blocks the informational answer path too."""
        state = _base_state(
            intent="unknown", category="unknown", confidence=0.3, kb_grounded=True,
            resolution_template="Some policy answer, {username}.",
        )
        with patch("agents.action_node._post_enterprise") as mock_post:
            result = await action_node(state)
        mock_post.assert_not_called()
        assert result["status"] == "escalated"
