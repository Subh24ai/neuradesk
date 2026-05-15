"""Action node — calls mock enterprise APIs to fulfil the ticket (stub for week 1)."""

import structlog

from tracing.langsmith import node_span
from agents.state import TicketState

log = structlog.get_logger(__name__)

# Intents that are considered destructive and require explicit confirmation.
_DESTRUCTIVE_INTENTS = frozenset({"access_revoke", "account_lock", "account_delete"})


def action_node(state: TicketState) -> TicketState:
    """Execute the appropriate enterprise API call for the resolved intent.

    Reads:  intent, entities, resolution_template, action_confirmed, trace_id
    Writes: action_taken, action_result, action_confirmed, resolution, status, error
    """
    intent = state.get("intent", "")
    entities = state.get("entities") or {}

    with node_span("action_node", {"intent": intent, "entities": entities}):
        log.info("action_node.start", ticket_id=state.get("ticket_id"), intent=intent)

        # Guard: destructive actions require explicit confirmation.
        if intent in _DESTRUCTIVE_INTENTS and not state.get("action_confirmed"):
            log.warning("action_node.awaiting_confirmation", intent=intent)
            return {
                **state,
                "action_confirmed": False,
                "status": "escalated",
                "error": f"Destructive intent '{intent}' requires explicit confirmation.",
            }  # type: ignore[return-value]

        try:
            # Stub — real HTTP call to enterprise-api added in file 5.
            action_result: dict = {
                "status": "ok",
                "data": {"temp_password": "Stub-P@ssw0rd!", "ticket_ref": "INC0000001"},
            }
            # Seed format context with state user_id so resolution strings show a real
            # identity even before week-2 NLP extracts named entities from the ticket text.
            # Extracted entities override the fallback — except when they still carry the
            # stub sentinel "unknown", in which case the real user_id is kept instead.
            user_fallback = state.get("user_id", "unknown")
            format_context: dict[str, str] = {"user_id": user_fallback, "username": user_fallback}
            for k, v in entities.items():
                if k == "username" and v in (None, "unknown", ""):
                    continue  # stub placeholder — keep the real user_id fallback
                format_context[k] = str(v) if v is not None else "unknown"
            resolution = (state.get("resolution_template") or "Action completed.").format(**format_context)

            updates: dict = {
                "action_taken": f"{intent}_executed",
                "action_result": action_result,
                "action_confirmed": True,
                "resolution": resolution,
                "status": "resolved",
                "error": None,
            }

            log.info("action_node.done", action_taken=updates["action_taken"], ticket_id=state.get("ticket_id"))
            return {**state, **updates}  # type: ignore[return-value]

        except Exception as exc:
            log.exception("action_node.error", ticket_id=state.get("ticket_id"))
            return {
                **state,
                "status": "escalated",
                "error": str(exc),
            }  # type: ignore[return-value]
