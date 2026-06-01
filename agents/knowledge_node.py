"""Knowledge node — hybrid RAG retrieval + LLM resolution generation."""

from __future__ import annotations

import numpy as np
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from rank_bm25 import BM25Okapi

from agents.state import RetrievedChunk, TicketState
from core.llm import get_llm
from rag.retriever import get_retriever
from tracing.langsmith import traceable

log = structlog.get_logger(__name__)

# Cross-encoder scores below this threshold indicate the KB has no useful answer.
# ms-marco-MiniLM-L-6-v2 sigmoid scores: > 0.35 = plausible match; < 0.35 = off-topic.
# Force confidence low so the escalation router picks it up.
_RAG_SCORE_THRESHOLD: float = 0.35

_RESOLUTION_SYSTEM_PROMPT: str = (
    "You are an IT/HR support assistant. "
    "Given the following knowledge base excerpt, write a "
    "single clear resolution step for the employee. "
    "Use {username} as a placeholder where the person's "
    "name is needed. Be concise — one sentence maximum."
)


@traceable(name="knowledge_node", run_type="chain", metadata={"agent": "knowledge", "version": "1.0"})
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

    log.info("knowledge_node.start", ticket_id=state.get("ticket_id"), category=category)

    retriever = get_retriever()
    chunks: list[RetrievedChunk] = retriever.search(query, top_k=3)

    # Merge in org-specific KB docs via BM25 if the org has uploaded any.
    org_kb_docs: list[dict] = state.get("org_kb_docs") or []
    if org_kb_docs:
        org_texts = [d["content"] for d in org_kb_docs]
        bm25 = BM25Okapi([t.lower().split() for t in org_texts])
        org_scores = bm25.get_scores(query.lower().split())
        top_org_idxs = list(np.argsort(org_scores)[::-1][:3])
        org_chunks: list[RetrievedChunk] = [
            {
                "source": f"org-kb:{org_kb_docs[i]['title']}",
                "content": org_texts[i],
                "score": float(org_scores[i]) + 5.0,  # boost so org docs rank above global
            }
            for i in top_org_idxs
            if org_scores[i] > 0
        ]
        # Merge: org docs first, then global (deduplicate by content prefix)
        seen_prefixes: set[str] = {c["content"][:80] for c in org_chunks}
        for c in chunks:
            if c["content"][:80] not in seen_prefixes:
                org_chunks.append(c)
        chunks = sorted(org_chunks, key=lambda c: c["score"], reverse=True)[:3]

    # No results → low confidence so the graph router escalates.
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
            "confidence": 0.3,
            "status": "acting",
        }  # type: ignore[return-value]

    # Top chunk score below threshold means KB has no real answer — escalate.
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
            "confidence": 0.3,
            "status": "acting",
        }  # type: ignore[return-value]
    try:
        llm = get_llm()
        response = llm.invoke([
            SystemMessage(content=_RESOLUTION_SYSTEM_PROMPT),
            HumanMessage(content=top_chunk["content"]),
        ])
        resolution: str = str(response.content).strip()
    except Exception as exc:
        log.exception(
            "knowledge_node.llm_error",
            ticket_id=state.get("ticket_id"),
            exc_type=type(exc).__name__,
            error=str(exc),
            hint="LLM call failed — resolution degraded to raw KB chunk, not a retrieval failure",
        )
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
