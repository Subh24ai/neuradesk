"""Escalation node — routes unresolvable tickets to a human agent group."""

import structlog

from tracing.langsmith import node_span
from agents.state import TicketState

log = structlog.get_logger(__name__)

# Priority → assignee group mapping.
_PRIORITY_GROUP: dict[str, str] = {
    "CRITICAL": "sre-oncall",
    "HIGH": "tier-2-support",
    "MEDIUM": "tier-1-support",
    "LOW": "tier-1-support",
}


def escalation_node(state: TicketState) -> TicketState:
    """Determine escalation reason and assign to the appropriate support group.

    Reads:  status, error, action_result, priority, confidence, category, trace_id
    Writes: escalated, escalation_reason, assignee_group, status
    """
    error = state.get("error")
    confidence = state.get("confidence") or 1.0
    category = state.get("category", "")
    priority = state.get("priority", "MEDIUM")

    with node_span("escalation_node", {"error": error, "priority": priority, "category": category}):
        log.info("escalation_node.start", ticket_id=state.get("ticket_id"), error=error)

        # Determine the most specific reason for escalation.
        if category == "UNKNOWN":
            reason = "Category could not be determined."
        elif confidence < 0.6:
            reason = f"Triage confidence too low ({confidence:.2f} < 0.60)."
        elif error and "confirmation" in error.lower():
            reason = "Destructive action awaiting human confirmation."
        elif error:
            reason = f"Action node error: {error}"
        else:
            reason = "Escalated by policy."

        assignee = _PRIORITY_GROUP.get(priority, "tier-1-support")

        updates: dict = {
            "escalated": True,
            "escalation_reason": reason,
            "assignee_group": assignee,
            "status": "escalated",
        }

        log.info(
            "escalation_node.done",
            reason=reason,
            assignee_group=assignee,
            ticket_id=state.get("ticket_id"),
        )
        return {**state, **updates}  # type: ignore[return-value]
