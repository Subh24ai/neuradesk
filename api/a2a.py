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
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents.knowledge_node import knowledge_node
from agents.state import TicketState

log = structlog.get_logger(__name__)

router = APIRouter(tags=["a2a"])

# ── A2A authentication ─────────────────────────────────────────────────────────

_A2A_API_KEY: str = os.environ.get("A2A_API_KEY", "")
if not _A2A_API_KEY:
    raise RuntimeError(
        "A2A_API_KEY env var is not set — refusing to start with A2A task endpoints unauthenticated"
    )

_A2A_QUERY_TIMEOUT: int = int(os.environ.get("A2A_QUERY_TIMEOUT_SECONDS", "30"))
_A2A_MAX_CONCURRENT_SUBSCRIPTIONS: int = int(
    os.environ.get("A2A_MAX_CONCURRENT_SUBSCRIPTIONS", "10")
)
_subscribe_semaphore: asyncio.Semaphore = asyncio.Semaphore(_A2A_MAX_CONCURRENT_SUBSCRIPTIONS)

_a2a_bearer = HTTPBearer(auto_error=True)


def get_a2a_key(
    credentials: HTTPAuthorizationCredentials = Depends(_a2a_bearer),
) -> None:
    """Validate the A2A Bearer token; raise 401 on any mismatch."""
    if credentials.credentials != _A2A_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

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
    "authentication": {"schemes": ["bearer"]},
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
async def task_send(
    request: Request,
    _: None = Depends(get_a2a_key),
) -> dict[str, Any]:
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
async def task_send_subscribe(
    request: Request,
    _: None = Depends(get_a2a_key),
) -> StreamingResponse | JSONResponse:
    """Submit a task and receive real-time status updates via Server-Sent Events.

    SSE event sequence::

        data: {"id": ..., "status": {"state": "working", ...}}

        data: {"id": ..., "artifact": {"name": "resolution", "parts": [...]}}

        data: {"id": ..., "status": {"state": "completed", ...}, "final": true}

    Each event is a JSON object on a ``data:`` line, separated by blank lines.
    Returns 503 immediately when the concurrent subscription limit is reached.
    """
    body: dict[str, Any] = await request.json()
    task_id: str = body.get("id") or str(uuid.uuid4())
    message: dict[str, Any] = body.get("message") or {}
    query: str = _extract_query(message)

    log.info("a2a.task_subscribe", task_id=task_id, query_preview=query[:80])

    # Fail fast: claim a concurrency slot now, at request time, before we commit
    # to an SSE stream. The acquire MUST happen here rather than inside the
    # generator — the generator only runs once Starlette starts consuming it,
    # which is after the 200 + SSE headers are already on the wire, so an
    # acquire there can no longer reject and would silently queue requests.
    # locked() + acquire() with no await in between is atomic under asyncio's
    # single-threaded scheduling, so the acquire below cannot block.
    if _subscribe_semaphore.locked():
        log.warning(
            "a2a.task_subscribe.overloaded",
            task_id=task_id,
            limit=_A2A_MAX_CONCURRENT_SUBSCRIPTIONS,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "Too many concurrent SSE subscriptions. Retry later.",
                "code": "SUBSCRIBE_OVERLOADED",
            },
        )
    await _subscribe_semaphore.acquire()

    async def _event_stream() -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events: working → artifact → completed.

        The concurrency slot claimed in task_send_subscribe is released in the
        finally block when the stream ends — normally, on timeout, on error, or
        when the client disconnects (Starlette calls aclose() in all cases).
        """

        def _sse(payload: dict[str, Any]) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
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
            try:
                status, answer, chunks = await asyncio.wait_for(
                    result_queue.get(), timeout=_A2A_QUERY_TIMEOUT
                )
            except asyncio.TimeoutError:
                log.error("a2a.task_subscribe.timeout", task_id=task_id, timeout=_A2A_QUERY_TIMEOUT)
                yield _sse(
                    {
                        "id": task_id,
                        "status": {"state": "failed", "timestamp": _now_iso()},
                        "final": True,
                    }
                )
                return

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
        finally:
            _subscribe_semaphore.release()

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
