"""A2A (Agent-to-Agent) protocol endpoint for the NeuraDesk Knowledge Agent.

Implements the Google A2A specification:
  - GET  /.well-known/agent.json    → AgentCard
  - POST /tasks/send                → synchronous task execution
  - POST /tasks/sendSubscribe       → SSE streaming (working → artifact → completed)

External agents submit a natural-language query via the A2A Task message format
and receive a grounded answer retrieved from the NeuraDesk knowledge base.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agents.knowledge_node import knowledge_node
from agents.state import TicketState

log = structlog.get_logger(__name__)

router = APIRouter(tags=["a2a"])

# ── Agent Card ─────────────────────────────────────────────────────────────────

_AGENT_CARD: dict[str, Any] = {
    "name": "NeuraDesk Knowledge Agent",
    "description": (
        "Resolves IT and HR support queries using hybrid FAISS + BM25 "
        "retrieval over the NeuraDesk knowledge base. Returns a grounded "
        "one-sentence resolution together with the source chunks."
    ),
    "version": "1.0.0",
    "documentationUrl": "/docs",
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    },
    "authentication": {"schemes": ["none"]},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "knowledge_retrieval",
            "name": "IT/HR Knowledge Retrieval",
            "description": (
                "Answer IT and HR support questions using the internal knowledge base. "
                "Covers: password reset, access requests, software installation, "
                "leave approval, and incident reporting."
            ),
            "tags": ["itsm", "hr", "knowledge-base", "rag"],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"],
            "examples": [
                "How do I reset my corporate password?",
                "What is the process for requesting software installation?",
                "How do I apply for annual leave?",
                "What are the P1 incident response times?",
            ],
        }
    ],
}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _extract_query(message: dict[str, Any]) -> str:
    """Return the first text part from an A2A message, or '' if none."""
    for part in message.get("parts", []):
        if isinstance(part, dict) and part.get("type") == "text":
            return str(part.get("text", "")).strip()
    return ""


def _run_knowledge_query(query: str) -> tuple[str, list[dict[str, Any]]]:
    """Build a minimal TicketState, run knowledge_node, return (answer, chunks).

    Args:
        query: Natural-language question from the calling agent.

    Returns:
        Tuple of (resolution text, list of RetrievedChunk dicts).
    """
    state: TicketState = {  # type: ignore[assignment]
        "ticket_id": str(uuid.uuid4()),
        "user_id": "a2a-caller",
        "created_at": datetime.now(timezone.utc),
        "trace_id": str(uuid.uuid4()),
        "channel": "text",
        "raw_text": query,
        "raw_image_b64": None,
        "extracted_text": None,
        "category": "unknown",
        "intent": None,
        "priority": "MEDIUM",
        "confidence": 0.9,
        "entities": {},
        "retrieved_chunks": None,
        "resolution_template": None,
        "action_taken": None,
        "action_result": None,
        "action_confirmed": None,
        "resolution": None,
        "escalated": None,
        "escalation_reason": None,
        "assignee_group": None,
        "status": "retrieving",
        "error": None,
        "trace_url": None,
    }
    result = knowledge_node(state)
    answer: str = result.get("resolution") or "No answer found in the knowledge base."
    chunks: list[dict[str, Any]] = [
        dict(c) for c in (result.get("retrieved_chunks") or [])
    ]
    return answer, chunks


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── Agent Card endpoint ────────────────────────────────────────────────────────


@router.get("/.well-known/agent.json", summary="A2A Agent Card")
async def agent_card(request: Request) -> dict[str, Any]:
    """Return the A2A AgentCard describing this agent's capabilities and skills."""
    base_url = str(request.base_url).rstrip("/")
    return {**_AGENT_CARD, "url": base_url}


# ── Synchronous task endpoint ──────────────────────────────────────────────────


@router.post("/tasks/send", summary="A2A synchronous task")
async def task_send(request: Request) -> dict[str, Any]:
    """Submit a knowledge-retrieval task and wait for synchronous completion.

    Request body (A2A Task)::

        {
            "id": "<uuid>",
            "sessionId": "<uuid>",
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "How do I reset my password?"}]
            }
        }

    Returns a completed Task with a resolution artifact and source metadata.
    """
    body: dict[str, Any] = await request.json()
    task_id: str = body.get("id") or str(uuid.uuid4())
    session_id: str = body.get("sessionId") or str(uuid.uuid4())
    message: dict[str, Any] = body.get("message") or {}
    query: str = _extract_query(message)

    log.info("a2a.task_send", task_id=task_id, query_preview=query[:80])

    if not query:
        return {
            "id": task_id,
            "sessionId": session_id,
            "status": {
                "state": "failed",
                "timestamp": _now_iso(),
                "message": {
                    "role": "agent",
                    "parts": [
                        {"type": "text", "text": "No text query found in message parts."}
                    ],
                },
            },
        }

    try:
        loop = asyncio.get_running_loop()
        answer, chunks = await loop.run_in_executor(None, _run_knowledge_query, query)
    except Exception as exc:
        log.exception("a2a.task_send.error", task_id=task_id)
        return {
            "id": task_id,
            "sessionId": session_id,
            "status": {"state": "failed", "timestamp": _now_iso()},
            "metadata": {"error": str(exc)},
        }

    log.info("a2a.task_send.done", task_id=task_id, chunks=len(chunks))
    return {
        "id": task_id,
        "sessionId": session_id,
        "status": {"state": "completed", "timestamp": _now_iso()},
        "artifacts": [
            {
                "name": "resolution",
                "index": 0,
                "lastChunk": True,
                "parts": [{"type": "text", "text": answer}],
            }
        ],
        "metadata": {
            "chunks_retrieved": len(chunks),
            "sources": [c.get("source", "") for c in chunks],
        },
    }


# ── SSE streaming task endpoint ────────────────────────────────────────────────


@router.post("/tasks/sendSubscribe", summary="A2A SSE streaming task")
async def task_send_subscribe(request: Request) -> StreamingResponse:
    """Submit a task and receive real-time status updates via Server-Sent Events.

    SSE event sequence::

        data: {"id": ..., "status": {"state": "working", ...}}

        data: {"id": ..., "artifact": {"name": "resolution", "parts": [...]}}

        data: {"id": ..., "status": {"state": "completed", ...}, "final": true}

    Each event is a JSON object on a ``data:`` line, separated by blank lines.
    """
    body: dict[str, Any] = await request.json()
    task_id: str = body.get("id") or str(uuid.uuid4())
    message: dict[str, Any] = body.get("message") or {}
    query: str = _extract_query(message)

    log.info("a2a.task_subscribe", task_id=task_id, query_preview=query[:80])

    async def _event_stream() -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events: working → artifact → completed."""

        def _sse(payload: dict[str, Any]) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        # 1. Working event — immediately signals processing has started.
        yield _sse(
            {
                "id": task_id,
                "status": {
                    "state": "working",
                    "timestamp": _now_iso(),
                    "message": {
                        "role": "agent",
                        "parts": [
                            {
                                "type": "text",
                                "text": "Retrieving from knowledge base…",
                            }
                        ],
                    },
                },
            }
        )

        if not query:
            yield _sse(
                {
                    "id": task_id,
                    "status": {"state": "failed", "timestamp": _now_iso()},
                    "final": True,
                }
            )
            return

        # 2. Run retrieval in a background thread (keeps the event loop unblocked).
        result_queue: asyncio.Queue[tuple[str, Any, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _run_in_thread() -> None:
            try:
                answer, chunks = _run_knowledge_query(query)
                loop.call_soon_threadsafe(result_queue.put_nowait, ("ok", answer, chunks))
            except Exception as exc:
                loop.call_soon_threadsafe(
                    result_queue.put_nowait, ("error", str(exc), [])
                )

        threading.Thread(target=_run_in_thread, daemon=True).start()
        status, answer, chunks = await result_queue.get()

        if status == "error":
            log.error("a2a.task_subscribe.error", task_id=task_id, error=answer)
            yield _sse(
                {
                    "id": task_id,
                    "status": {"state": "failed", "timestamp": _now_iso()},
                    "final": True,
                }
            )
            return

        # 3. Artifact event — streams the resolution text.
        yield _sse(
            {
                "id": task_id,
                "artifact": {
                    "name": "resolution",
                    "index": 0,
                    "lastChunk": True,
                    "parts": [{"type": "text", "text": answer}],
                    "metadata": {
                        "chunks_retrieved": len(chunks),
                        "sources": [c.get("source", "") for c in chunks],
                    },
                },
            }
        )

        # 4. Completed event — final=True signals end of stream.
        yield _sse(
            {
                "id": task_id,
                "status": {"state": "completed", "timestamp": _now_iso()},
                "final": True,
            }
        )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
