"""Escalation node — routes unresolvable tickets to a human agent group."""

import structlog

from agents.state import TicketState
from api.email import send_escalation_alert, send_ticket_notification
from tracing.langsmith import traceable

log = structlog.get_logger(__name__)

# Priority → assignee group mapping.
_PRIORITY_GROUP: dict[str, str] = {
    "CRITICAL": "sre-oncall",
    "HIGH": "tier-2-support",
    "MEDIUM": "tier-1-support",
    "LOW": "tier-1-support",
}


@traceable(name="escalation_node", run_type="chain", metadata={"agent": "escalation", "version": "1.0"})
def escalation_node(state: TicketState) -> TicketState:
    """Determine escalation reason and assign to the appropriate support group.

    Reads:  status, error, action_result, priority, confidence, category, trace_id
    Writes: escalated, escalation_reason, assignee_group, status
    """
    error = state.get("error")
    confidence = state.get("confidence") or 1.0
    category = state.get("category", "")
    priority = state.get("priority", "MEDIUM")

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

    _send_escalation_notifications(state, reason, assignee, priority)

    return {**state, **updates}  # type: ignore[return-value]


def _send_escalation_notifications(
    state: TicketState,
    reason: str,
    assignee: str,
    priority: str,
) -> None:
    """Fire support-team and user emails; log warnings on failure, never raise."""
    ticket_id: str = state.get("ticket_id") or ""
    support_email: str = state.get("support_email") or ""
    user_email: str = state.get("user_email") or ""
    org_name: str = state.get("org_name") or state.get("org_id") or "Unknown org"

    try:
        if support_email:
            send_escalation_alert(
                ticket_id=ticket_id,
                reason=reason,
                assignee_group=assignee,
                priority=priority,
                org_name=org_name,
                support_email=support_email,
            )
        else:
            log.warning(
                "escalation_node.no_support_email",
                ticket_id=ticket_id,
                hint="Set SUPPORT_EMAIL env var or configure org SMTP to receive escalation alerts",
            )
    except Exception as exc:
        log.warning("escalation_node.support_email_failed", ticket_id=ticket_id, error=str(exc))

    try:
        if user_email:
            send_ticket_notification(
                email=user_email,
                ticket_id=ticket_id,
                status="escalated",
                resolution=None,
                escalation_reason=reason,
                priority=priority,
                assignee_group=assignee,
            )
        else:
            log.warning(
                "escalation_node.no_user_email",
                ticket_id=ticket_id,
                hint="user_email not in state — user will not receive an escalation notification",
            )
    except Exception as exc:
        log.warning("escalation_node.user_email_failed", ticket_id=ticket_id, error=str(exc))
