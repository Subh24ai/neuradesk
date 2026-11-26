"""Knowledge node — hybrid RAG retrieval + LLM resolution generation."""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import RetrievedChunk, TicketState
from core.config import get_settings
from core.llm import get_llm
from rag.retriever import get_retriever
from tracing.langsmith import traceable

_cfg = get_settings()

log = structlog.get_logger(__name__)

# Cross-encoder scores below this threshold indicate the KB has no useful answer.
# ms-marco-MiniLM-L-6-v2 returns raw logits (not 0–1 probabilities): on-topic
# passages typically score > 1, off-topic ones are strongly negative.
_RAG_SCORE_THRESHOLD: float = _cfg.rag_score_threshold

# Number of top-ranked chunks fed to the LLM when generating the resolution.
_GROUNDING_CHUNKS: int = 3

_RESOLUTION_SYSTEM_PROMPT: str = (
    "You are an IT/HR support assistant replying directly to the employee who "
    "asked. Answer their question using ONLY the knowledge base excerpts provided. "
    "Answer every part of the question (e.g. both 'how many' and 'how do I'), "
    "include concrete steps, names of tools and deadlines from the excerpts, and "
    "leave out information they did not ask about. Use at most three short "
    "sentences, address them as 'you', and never mention their name or email. "
    "If the excerpts don't answer the question, say so in one sentence. "
    "Never add anything the excerpts don't state — no invented timelines, emails, "
    "contacts, statuses or generic advice."
)

# Sentinel the model returns when the excerpts hold no follow-up guidance for an
# action NeuraDesk is already performing; the reply then uses the standard text.
_NO_GUIDANCE: str = "NONE"


@traceable(name="knowledge_node", run_type="chain", metadata={"agent": "knowledge", "version": "1.0"})
def knowledge_node(state: TicketState) -> TicketState:
    """Retrieve relevant KB chunks and generate a resolution via LLM.

    Builds a hybrid FAISS + BM25 query from the ticket category and text,
    retrieves the top-3 chunks, then invokes the LLM to produce a one-sentence
    resolution from the highest-scoring chunk.

    Sets ``kb_grounded`` to report whether the knowledge base actually answered
    the ticket (top passage cleared ``rag_score_threshold``). It deliberately does
    NOT touch ``confidence``: that is the triage/injection signal the action node
    uses to decide whether it may act at all. A missing KB article must not stop a
    well-understood action (e.g. a password reset) — it only means the reply
    uses a standard message instead of a grounded one.

    Reads:  category, extracted_text, raw_text, org_kb_docs, trace_id
    Writes: retrieved_chunks, kb_grounded, resolution_template, resolution, status
    """
    category: str = state.get("category") or "unknown"
    ticket_text: str = (
        state.get("extracted_text") or state.get("raw_text") or ""
    )[:300]
    # Prepend the category only when it carries signal — "unknown" is a routing
    # label, not a search term, and would otherwise pollute the retrieval query.
    query: str = ticket_text if category == "unknown" else f"{category} {ticket_text}"

    log.info("knowledge_node.start", ticket_id=state.get("ticket_id"), category=category)

    org_kb_docs: list[dict] = state.get("org_kb_docs") or []
    retriever = get_retriever()
    chunks: list[RetrievedChunk] = retriever.search(
        query, top_k=3, org_chunks=org_kb_docs or None
    )

    # No results → the KB has no answer for this ticket.
    if not chunks:
        log.warning(
            "knowledge_node.empty_retrieval",
            ticket_id=state.get("ticket_id"),
            query_preview=query[:80],
            threshold=_RAG_SCORE_THRESHOLD,
        )
        return {
            **state,
            "retrieved_chunks": [],
            "kb_grounded": False,
            "status": "acting",
        }  # type: ignore[return-value]

    # Top chunk score below threshold means the KB has no real answer.
    top_chunk = chunks[0]
    if top_chunk["score"] < _RAG_SCORE_THRESHOLD:
        log.warning(
            "knowledge_node.low_rag_score",
            score=top_chunk["score"],
            threshold=_RAG_SCORE_THRESHOLD,
            ticket_id=state.get("ticket_id"),
        )
        return {
            **state,
            "retrieved_chunks": chunks,
            "kb_grounded": False,
            "status": "acting",
        }  # type: ignore[return-value]
    try:
        llm = get_llm()
        # Ground the resolution on the top-ranked chunks (not just the single
        # best) so multi-step answers aren't truncated to one paragraph.
        context: str = "\n\n".join(c["content"] for c in chunks[:_GROUNDING_CHUNKS])
        # For an actionable request NeuraDesk performs the action itself, so the
        # reply must add only follow-up guidance — never "submit a ticket" or
        # steps the system has already done.
        situation: str = (
            ""
            if category == "unknown"
            else (
                f"\n\nNeuraDesk is already carrying out this request ({category.replace('_', ' ')}) "
                "automatically; it has been submitted. Give only follow-up guidance the employee "
                "needs afterwards (rules, limits, what to do next) that the excerpts state. Do not "
                "tell them to submit, open or file a ticket or request, and do not repeat steps "
                f"the system is doing. If the excerpts contain no such guidance, reply exactly {_NO_GUIDANCE}."
            )
        )
        response = llm.invoke([
            SystemMessage(content=_RESOLUTION_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Employee's request:\n{ticket_text}\n\nKnowledge base excerpts:\n{context}{situation}"
            ),
        ])
        resolution: str = str(response.content).strip()
        if resolution.strip(" .").upper() == _NO_GUIDANCE:
            # Nothing in the KB adds to the action's own confirmation message.
            log.info("knowledge_node.no_followup_guidance", ticket_id=state.get("ticket_id"))
            return {**state, "retrieved_chunks": chunks, "kb_grounded": False, "status": "acting"}  # type: ignore[return-value]
    except Exception as exc:
        log.exception(
            "knowledge_node.llm_error",
            ticket_id=state.get("ticket_id"),
            exc_type=type(exc).__name__,
            error=str(exc),
            hint="LLM call failed — resolution degraded to raw KB chunk, not a retrieval failure",
        )
        resolution = top_chunk["content"][:200]

    # The reply is shown to the employee as-is (second person, no identifiers).
    resolution_template: str = resolution

    updates: dict = {
        "retrieved_chunks": chunks,
        "kb_grounded": True,
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
