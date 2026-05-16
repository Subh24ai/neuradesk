"""Tests for agents.escalation_node — reason determination and assignee routing."""

from __future__ import annotations

from datetime import datetime, timezone

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
