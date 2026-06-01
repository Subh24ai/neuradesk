"""Tests for agents.action_node — enterprise HTTP calls are mocked via patch."""

from __future__ import annotations

from datetime import datetime, timezone
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
        "created_at": datetime.now(timezone.utc),
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
        """{username} in resolution_template is replaced with the extracted entity."""
        state = _base_state(
            intent="password_reset",
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
