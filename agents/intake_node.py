"""Intake node — classifies the ticket, extracts intent, priority, and entities."""

import uuid
from datetime import datetime, timezone

import structlog

from tracing.langsmith import node_span
from agents.state import TicketState

log = structlog.get_logger(__name__)


def intake_node(state: TicketState) -> TicketState:
    """Triage the incoming ticket: set category, intent, priority, confidence, entities.

    Reads:  raw_text, raw_image_b64, channel, ticket_id, trace_id
    Writes: category, intent, priority, confidence, entities,
            extracted_text, status, ticket_id (if not yet set), created_at
    """
    with node_span("intake_node", {"raw_text": state.get("raw_text", ""), "ticket_id": state.get("ticket_id")}):
        log.info("intake_node.start", ticket_id=state.get("ticket_id"))

        updates: dict = {
            "ticket_id": state.get("ticket_id") or str(uuid.uuid4()),
            "created_at": state.get("created_at") or datetime.now(timezone.utc),
            # Stub values — replaced by LLM classifier in week 2.
            "category": "password_reset",
            "intent": "password_reset",
            "priority": "MEDIUM",
            "confidence": 0.92,
            "entities": {"username": "unknown"},
            "extracted_text": None,
            "status": "retrieving",
        }

        log.info("intake_node.done", **{k: v for k, v in updates.items() if k != "created_at"})
        return {**state, **updates}  # type: ignore[return-value]
