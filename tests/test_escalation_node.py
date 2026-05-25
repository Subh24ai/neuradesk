"""Tests for agents.escalation_node — reason determination and assignee routing."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from agents.escalation_node import escalation_node
from agents.state import TicketState


# ── Helpers ───────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> TicketState:
    """Return a minimal TicketState ready for escalation_node."""
    base: dict = {
        "ticket_id": "test-escalation-001",
        "user_id": "test-user@corp.com",
        "created_at": datetime.now(timezone.utc),
        "trace_id": "test-trace-001",
        "channel": "text",
        "raw_text": "I cannot log in",
        "raw_image_b64": None,
        "extracted_text": None,
        "category": "password_reset",
        "intent": "password_reset",
        "priority": "MEDIUM",
        "confidence": 0.9,
        "entities": {},
        "retrieved_chunks": [],
        "resolution_template": None,
        "action_taken": None,
        "action_result": None,
        "action_confirmed": None,
        "resolution": None,
        "escalated": None,
        "escalation_reason": None,
        "assignee_group": None,
        "org_id": "test-org-001",
        "org_name": "Test Corp",
        "org_kb_docs": [],
        "org_api_url": None,
        "org_api_secret": None,
        "support_email": "",
        "user_email": "",
        "slack_webhook_url": None,
        "status": "escalated",
        "error": None,
        "trace_url": None,
    }
    return {**base, **overrides}  # type: ignore[return-value]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestEscalationNode:
    """Unit tests for escalation_node."""

    def test_output_marks_escalated_true(self) -> None:
        """escalation_node always sets escalated=True in the returned state."""
        result = escalation_node(_base_state())
        assert result["escalated"] is True

    def test_output_status_is_escalated(self) -> None:
        """escalation_node sets status='escalated'."""
        result = escalation_node(_base_state())
        assert result["status"] == "escalated"

    def test_low_confidence_reason(self) -> None:
        """confidence < 0.6 produces a reason mentioning the threshold."""
        result = escalation_node(_base_state(confidence=0.45))
        assert "0.45" in result["escalation_reason"]
        assert "0.60" in result["escalation_reason"]

    def test_api_error_reason(self) -> None:
        """A non-confirmation error in state['error'] is echoed in the reason."""
        result = escalation_node(_base_state(error="httpx.ConnectTimeout: upstream"))
        assert "httpx.ConnectTimeout" in result["escalation_reason"]

    def test_confirmation_error_reason(self) -> None:
        """Error containing 'confirmation' gets the destructive-action reason."""
        result = escalation_node(
            _base_state(error="Destructive intent 'access_revoke' requires explicit confirmation.")
        )
        assert "confirmation" in result["escalation_reason"].lower()

    def test_policy_escalation_reason(self) -> None:
        """No error and no confidence issue → generic 'Escalated by policy' reason."""
        result = escalation_node(_base_state(confidence=0.9, error=None))
        assert result["escalation_reason"] == "Escalated by policy."

    # ── Assignee group routing ─────────────────────────────────────────────────

    def test_critical_priority_routes_to_sre_oncall(self) -> None:
        """CRITICAL priority tickets go to 'sre-oncall'."""
        result = escalation_node(_base_state(priority="CRITICAL"))
        assert result["assignee_group"] == "sre-oncall"

    def test_high_priority_routes_to_tier2(self) -> None:
        """HIGH priority tickets go to 'tier-2-support'."""
        result = escalation_node(_base_state(priority="HIGH"))
        assert result["assignee_group"] == "tier-2-support"

    def test_medium_priority_routes_to_tier1(self) -> None:
        """MEDIUM priority tickets go to 'tier-1-support'."""
        result = escalation_node(_base_state(priority="MEDIUM"))
        assert result["assignee_group"] == "tier-1-support"

    def test_low_priority_routes_to_tier1(self) -> None:
        """LOW priority tickets also go to 'tier-1-support'."""
        result = escalation_node(_base_state(priority="LOW"))
        assert result["assignee_group"] == "tier-1-support"

    def test_unknown_priority_defaults_to_tier1(self) -> None:
        """Unrecognised priority string falls back to 'tier-1-support'."""
        result = escalation_node(_base_state(priority="UNKNOWN"))
        assert result["assignee_group"] == "tier-1-support"

    def test_state_fields_preserved(self) -> None:
        """escalation_node does not drop unrelated state fields."""
        state = _base_state(raw_text="cannot log in", entities={"username": "jdoe"})
        result = escalation_node(state)
        assert result["raw_text"] == "cannot log in"
        assert result["entities"] == {"username": "jdoe"}


# ── Notification tests ────────────────────────────────────────────────────────


class TestEscalationNotifications:
    """Tests for the email notification side-effects of escalation_node."""

    def test_escalation_sends_alert(self) -> None:
        """When support_email and user_email are set, both email functions are called."""
        state = _base_state(
            priority="HIGH",
            support_email="support@corp.com",
            user_email="alice@corp.com",
            org_name="Corp Inc",
        )
        with (
            patch("agents.escalation_node.send_escalation_alert") as mock_alert,
            patch("agents.escalation_node.send_ticket_notification") as mock_notify,
        ):
            result = escalation_node(state)

        # Node still returns correct escalation fields
        assert result["escalated"] is True
        assert result["assignee_group"] == "tier-2-support"

        # Support team alert fired with correct args
        mock_alert.assert_called_once()
        alert_kwargs = mock_alert.call_args.kwargs
        assert alert_kwargs["support_email"] == "support@corp.com"
        assert alert_kwargs["ticket_id"] == "test-escalation-001"
        assert alert_kwargs["assignee_group"] == "tier-2-support"
        assert alert_kwargs["priority"] == "HIGH"
        assert alert_kwargs["org_name"] == "Corp Inc"

        # User notification fired with escalated status and response-time args
        mock_notify.assert_called_once()
        notify_kwargs = mock_notify.call_args.kwargs
        assert notify_kwargs["email"] == "alice@corp.com"
        assert notify_kwargs["status"] == "escalated"
        assert notify_kwargs["priority"] == "HIGH"
        assert notify_kwargs["assignee_group"] == "tier-2-support"

    def test_escalation_skips_gracefully_when_no_smtp(self) -> None:
        """When support_email and user_email are empty, no email calls are made and node succeeds."""
        state = _base_state(support_email="", user_email="")
        with (
            patch("agents.escalation_node.send_escalation_alert") as mock_alert,
            patch("agents.escalation_node.send_ticket_notification") as mock_notify,
        ):
            result = escalation_node(state)

        # Node completed without raising
        assert result["status"] == "escalated"
        assert result["escalated"] is True

        # Neither email function was called
        mock_alert.assert_not_called()
        mock_notify.assert_not_called()


# ── Slack notification tests ──────────────────────────────────────────────────


class TestSlackNotifications:
    """Tests for the Slack webhook side-effect of escalation_node."""

    def test_slack_sent_on_escalation(self) -> None:
        """When slack_webhook_url is set, send_slack_escalation is called with correct args."""
        state = _base_state(
            priority="HIGH",
            slack_webhook_url="https://hooks.slack.com/services/T00/B00/XXXX",
            org_name="Corp Inc",
        )
        with (
            patch("agents.escalation_node.send_escalation_alert"),
            patch("agents.escalation_node.send_ticket_notification"),
            patch("agents.escalation_node.send_slack_escalation") as mock_slack,
        ):
            result = escalation_node(state)

        assert result["escalated"] is True
        mock_slack.assert_called_once()
        kwargs = mock_slack.call_args.kwargs
        assert kwargs["webhook_url"] == "https://hooks.slack.com/services/T00/B00/XXXX"
        assert kwargs["ticket_id"] == "test-escalation-001"
        assert kwargs["assignee_group"] == "tier-2-support"
        assert kwargs["priority"] == "HIGH"
        assert kwargs["org_name"] == "Corp Inc"

    def test_slack_skipped_when_no_url(self) -> None:
        """When slack_webhook_url is None, send_slack_escalation is not called."""
        state = _base_state(slack_webhook_url=None)
        with (
            patch("agents.escalation_node.send_escalation_alert"),
            patch("agents.escalation_node.send_ticket_notification"),
            patch("agents.escalation_node.send_slack_escalation") as mock_slack,
        ):
            result = escalation_node(state)

        assert result["escalated"] is True
        mock_slack.assert_not_called()
