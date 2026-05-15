"""Knowledge node — retrieves relevant KB chunks via RAG (stub for week 1)."""

import structlog

from tracing.langsmith import node_span
from agents.state import RetrievedChunk, TicketState

log = structlog.get_logger(__name__)


def knowledge_node(state: TicketState) -> TicketState:
    """Retrieve knowledge chunks and select a resolution template.

    Reads:  category, intent, entities, trace_id
    Writes: retrieved_chunks, resolution_template, status
    """
    with node_span("knowledge_node", {"intent": state.get("intent"), "category": state.get("category")}):
        log.info("knowledge_node.start", ticket_id=state.get("ticket_id"), intent=state.get("intent"))

        # Stub — FAISS + BM25 hybrid retrieval wired in week 2.
        stub_chunks: list[RetrievedChunk] = [
            {
                "source": "kb/password-reset.md",
                "content": "To reset a password: navigate to IT Portal > Self-Service > Reset Password.",
                "score": 0.91,
            }
        ]

        updates: dict = {
            "retrieved_chunks": stub_chunks,
            "resolution_template": "Password reset initiated for {username} via IT Portal.",
            "status": "acting",
        }

        log.info("knowledge_node.done", chunks_retrieved=len(stub_chunks), ticket_id=state.get("ticket_id"))
        return {**state, **updates}  # type: ignore[return-value]
