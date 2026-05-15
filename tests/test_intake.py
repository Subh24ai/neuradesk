"""Tests for agents.intake_node — all LLM and vision calls are mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.intake_node import intake_node
from agents.state import TicketState


# ── Helpers ───────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> TicketState:
    """Return a minimal but complete TicketState for intake_node tests."""
    base: dict = {
        "ticket_id": "test-intake-001",
        "user_id": "test-user@corp.com",
        "created_at": None,
        "trace_id": "test-trace-001",
        "channel": "text",
        "raw_text": "I forgot my password and cannot log in",
        "raw_image_b64": None,
        "extracted_text": None,
        "category": None,
        "intent": None,
        "priority": None,
        "confidence": None,
        "entities": None,
        "retrieved_chunks": None,
        "resolution_template": None,
        "action_taken": None,
        "action_result": None,
        "action_confirmed": None,
        "resolution": None,
        "escalated": None,
        "escalation_reason": None,
        "assignee_group": None,
        "status": "triaging",
        "error": None,
        "trace_url": None,
    }
    return {**base, **overrides}  # type: ignore[return-value]


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestIntakeNode:
    """Unit tests for the real intake_node implementation."""

    def test_text_ticket_classified_correctly(self) -> None:
        """Text ticket: classify() result propagates into state category/intent/status."""
        state = _base_state(raw_text="I forgot my password and cannot log in")

        with patch("agents.intake_node.classify", return_value=("password_reset", 0.92)):
            result = intake_node(state)

        assert result["category"] == "password_reset"
        assert result["intent"] == "password_reset"
        assert result["status"] == "retrieving"
        assert result["confidence"] == pytest.approx(0.92)
        assert result["priority"] is not None
        # Text channel — no vision extraction, so extracted_text stays None.
        assert result["extracted_text"] is None

    def test_image_ticket_extracts_text_via_groq(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Image ticket: extracted_text is set from the Groq vision call."""
        monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
        state = _base_state(
            channel="image",
            raw_image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
            raw_text="Screenshot showing login error",
        )
        extracted = "User sees 'Invalid credentials' on the corporate SSO login page."

        with (
            patch(
                "agents.intake_node._extract_text_from_image", return_value=extracted
            ),
            patch("agents.intake_node.classify", return_value=("password_reset", 0.88)),
        ):
            result = intake_node(state)

        assert result["extracted_text"] == extracted
        assert result["category"] == "password_reset"
        assert result["status"] == "retrieving"

    def test_image_fallback_when_no_groq_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When GROQ_API_KEY is absent, extracted_text falls back to raw_text (no crash)."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        state = _base_state(
            channel="image",
            raw_image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ",
            raw_text="Screenshot showing login error",
        )

        with patch("agents.intake_node.classify", return_value=("password_reset", 0.75)):
            result = intake_node(state)

        assert result["extracted_text"] == state["raw_text"]
        assert result["status"] == "retrieving"
        # _extract_text_from_image must NOT have been called (no key → short-circuit).
        # Verified implicitly: no Groq API call raised despite no real key.

    def test_confidence_propagated_to_state(self) -> None:
        """classify() confidence is written into state['confidence'] unchanged."""
        state = _base_state(raw_text="I need access to the production database")

        with patch("agents.intake_node.classify", return_value=("access_request", 0.96)):
            result = intake_node(state)

        assert result["confidence"] == pytest.approx(0.96)
        assert result["category"] == "access_request"

    # ── Bonus: entity extraction and priority rules ────────────────────────────

    def test_email_extracted_as_username_entity(self) -> None:
        """An email address in the ticket text is captured as entities['username']."""
        state = _base_state(raw_text="Please reset the password for jdoe@corp.com")

        with patch("agents.intake_node.classify", return_value=("password_reset", 0.93)):
            result = intake_node(state)

        assert result["entities"] is not None
        assert result["entities"].get("username") == "jdoe@corp.com"

    def test_critical_keyword_overrides_priority(self) -> None:
        """'outage' in the ticket text forces priority to CRITICAL regardless of category."""
        state = _base_state(
            raw_text="Complete network outage on floor 3, everyone is affected"
        )

        with patch("agents.intake_node.classify", return_value=("incident_report", 0.99)):
            result = intake_node(state)

        assert result["priority"] == "CRITICAL"

    def test_leave_approval_gets_low_priority(self) -> None:
        """leave_approval category without critical keywords maps to LOW priority."""
        state = _base_state(raw_text="I would like to take annual leave next week")

        with patch("agents.intake_node.classify", return_value=("leave_approval", 0.97)):
            result = intake_node(state)

        assert result["priority"] == "LOW"
