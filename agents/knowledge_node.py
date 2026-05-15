"""Knowledge node — hybrid RAG retrieval + LLM resolution generation."""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import RetrievedChunk, TicketState
from core.llm import get_llm
from rag.retriever import get_retriever
from tracing.langsmith import node_span

log = structlog.get_logger(__name__)

_RESOLUTION_SYSTEM_PROMPT: str = (
    "You are an IT/HR support assistant. "
    "Given the following knowledge base excerpt, write a "
    "single clear resolution step for the employee. "
    "Use {username} as a placeholder where the person's "
    "name is needed. Be concise — one sentence maximum."
)


def knowledge_node(state: TicketState) -> TicketState:
    """Retrieve relevant KB chunks and generate a resolution via LLM.

    Builds a hybrid FAISS + BM25 query from the ticket category and text,
    retrieves the top-3 chunks, then invokes the LLM to produce a one-sentence
    resolution from the highest-scoring chunk.

    If retrieval returns no results, confidence is set to 0.3 so the graph
    router escalates the ticket after the action node runs.

    Reads:  category, extracted_text, raw_text, trace_id
    Writes: retrieved_chunks, resolution_template, resolution, status
    """
    category: str = state.get("category") or "unknown"
    ticket_text: str = (
        state.get("extracted_text") or state.get("raw_text") or ""
    )[:300]
    query: str = f"{category} {ticket_text}"

    with node_span("knowledge_node", {"query_preview": query[:80], "category": category}):
        log.info("knowledge_node.start", ticket_id=state.get("ticket_id"), category=category)

        retriever = get_retriever()
        chunks: list[RetrievedChunk] = retriever.search(query, top_k=3)

        # No results → low confidence so the graph router escalates.
        if not chunks:
            log.warning("knowledge_node.empty_retrieval", query_preview=query[:80])
            return {
                **state,
                "retrieved_chunks": [],
                "confidence": 0.3,
                "status": "acting",
            }  # type: ignore[return-value]

        # Generate a one-sentence resolution from the top-ranked chunk.
        top_chunk = chunks[0]
        try:
            llm = get_llm()
            response = llm.invoke([
                SystemMessage(content=_RESOLUTION_SYSTEM_PROMPT),
                HumanMessage(content=top_chunk["content"]),
            ])
            resolution: str = str(response.content).strip()
        except Exception as exc:
            log.exception("knowledge_node.llm_error", error=str(exc))
            resolution = top_chunk["content"][:200]

        # Guarantee {username} in resolution_template so the action node can
        # always substitute the authenticated user's identity into the message.
        resolution_template: str = (
            resolution
            if "{username}" in resolution
            else f"{resolution} — Ticket raised by {{username}}."
        )

        updates: dict = {
            "retrieved_chunks": chunks,
            "resolution_template": resolution_template,
            "resolution": resolution,
            "status": "acting",
        }

        log.info(
            "knowledge_node.done",
            chunks_retrieved=len(chunks),
            ticket_id=state.get("ticket_id"),
        )
        return {**state, **updates}  # type: ignore[return-value]
