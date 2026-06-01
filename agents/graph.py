"""LangGraph ticket-resolution workflow.

Topology:
    intake_node → knowledge_node → action_node → [escalation_node] → END

The conditional edge after action_node routes to escalation_node when:
  - status == "escalated"           (destructive action, unhandled exception)
  - confidence < 0.6                (low-confidence triage)
  - category == "UNKNOWN"
"""

import uuid
from typing import Literal

import structlog
from langgraph.graph import END, StateGraph

from agents.action_node import action_node
from agents.escalation_node import escalation_node
from agents.intake_node import intake_node
from agents.knowledge_node import knowledge_node
from agents.state import TicketState
from tracing.langsmith import get_trace_url, print_trace_url

log = structlog.get_logger(__name__)


def _should_escalate(state: TicketState) -> Literal["escalation_node", "__end__"]:
    """Routing function executed after action_node."""
    if state.get("status") == "awaiting_confirmation":
        return "__end__"  # halt graph; user must confirm via POST /tickets/{id}/confirm-action
    if state.get("status") == "escalated":
        return "escalation_node"
    if (state.get("confidence") or 1.0) < 0.6:
        return "escalation_node"
    if state.get("category") == "unknown":
        return "escalation_node"
    return "__end__"


def build_graph() -> StateGraph:
    """Construct and compile the NeuraDesk LangGraph workflow."""
    builder: StateGraph = StateGraph(TicketState)

    builder.add_node("intake_node", intake_node)
    builder.add_node("knowledge_node", knowledge_node)
    builder.add_node("action_node", action_node)
    builder.add_node("escalation_node", escalation_node)

    builder.set_entry_point("intake_node")
    builder.add_edge("intake_node", "knowledge_node")
    builder.add_edge("knowledge_node", "action_node")
    builder.add_conditional_edges(
        "action_node",
        _should_escalate,
        {
            "escalation_node": "escalation_node",
            "__end__": END,
        },
    )
    builder.add_edge("escalation_node", END)

    return builder.compile()


# Module-level compiled graph — import this in FastAPI and tests.
graph = build_graph()


def build_initial_state(
    raw_text: str,
    user_id: str = "anonymous",
    channel: str = "text",
    org_id: str | None = None,
    org_name: str | None = None,
    org_kb_docs: list[dict] | None = None,
    org_api_url: str | None = None,
    raw_image_b64: str | None = None,
    support_email: str | None = None,
    user_email: str | None = None,
    slack_webhook_url: str | None = None,
) -> TicketState:
    """Construct a blank TicketState ready to be fed into the graph."""
    return {  # type: ignore[return-value]
        "ticket_id": str(uuid.uuid4()),
        "user_id": user_id,
        "created_at": None,
        "trace_id": str(uuid.uuid4()),
        "channel": channel,  # type: ignore[arg-type]
        "raw_text": raw_text,
        "raw_image_b64": raw_image_b64,
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
        "org_id": org_id,
        "org_name": org_name,
        "org_kb_docs": org_kb_docs or [],
        "org_api_url": org_api_url,
        "support_email": support_email,
        "user_email": user_email,
        "slack_webhook_url": slack_webhook_url,
        "status": "triaging",
        "error": None,
        "trace_url": None,
    }


def run_ticket(raw_text: str, user_id: str = "anonymous", channel: str = "text") -> TicketState:
    """Submit a ticket through the full graph and return the final state.

    Used by smoke tests and any non-streaming callers.
    """
    initial = build_initial_state(raw_text, user_id, channel)

    log.info("graph.run_ticket.start", ticket_id=initial["ticket_id"], user_id=user_id)
    result: TicketState = graph.invoke(initial)

    # Surface the LangSmith trace URL in the returned state and on stdout.
    trace_url = get_trace_url()
    if trace_url:
        result = {**result, "trace_url": trace_url}  # type: ignore[assignment]
    print_trace_url()

    log.info("graph.run_ticket.done", ticket_id=result["ticket_id"], status=result["status"])
    return result
