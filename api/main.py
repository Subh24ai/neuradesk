"""FastAPI application — ticket routes, WebSocket streaming, health endpoint."""

import asyncio
import threading
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from agents.graph import graph as langgraph_graph
from agents.graph import run_ticket
from api.auth import auth_router, get_current_user
from core.dspy_config import configure_dspy
from api.models import (
    Base,
    TicketCreateRequest,
    TicketListResponse,
    TicketModel,
    TicketResponse,
    UserModel,
    engine,
    get_db,
)

load_dotenv()
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create all DB tables and configure DSPy on startup; log shutdown."""
    Base.metadata.create_all(bind=engine)
    configure_dspy()
    log.info("app.startup", db_url=str(engine.url))
    yield
    log.info("app.shutdown")


app = FastAPI(
    title="NeuraDesk API",
    version="0.1.0",
    description="Agentic IT/HR service desk platform powered by LangGraph.",
    lifespan=lifespan,
)

app.include_router(auth_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"], summary="Liveness probe")
def health() -> dict:
    """Return 200 when the API process is running."""
    return {"status": "ok", "version": "0.1.0"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _orm_to_response(ticket: TicketModel) -> TicketResponse:
    """Map a TicketModel ORM row to the Pydantic response schema."""
    return TicketResponse(
        ticket_id=ticket.id,
        status=ticket.status,
        category=ticket.category,
        confidence=ticket.confidence,
        resolution=ticket.resolution,
        escalation_reason=ticket.escalation_reason,
        trace_url=ticket.trace_url,
        created_at=ticket.created_at,
    )


def _build_ws_initial_state(
    ticket_id: str,
    raw_text: str,
    user_id: str,
    image_b64: Optional[str],
) -> dict:
    """Construct the initial TicketState dict for a WebSocket-submitted ticket."""
    return {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "created_at": None,
        "trace_id": str(uuid.uuid4()),
        "channel": "image" if image_b64 else "text",
        "raw_text": raw_text,
        "raw_image_b64": image_b64,
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
        "status": "triaging",
        "error": None,
        "trace_url": None,
    }


# ── Ticket routes ─────────────────────────────────────────────────────────────

# IMPORTANT: /tickets/ must be declared BEFORE /tickets/{ticket_id} so FastAPI
# does not swallow the trailing slash as a path parameter.

@app.get(
    "/tickets/",
    response_model=TicketListResponse,
    tags=["tickets"],
    summary="List last 20 tickets for the authenticated user",
)
def list_tickets(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketListResponse:
    """Return the 20 most-recent tickets belonging to the caller."""
    try:
        rows = (
            db.query(TicketModel)
            .filter(TicketModel.user_id == current_user.id)
            .order_by(TicketModel.created_at.desc())
            .limit(20)
            .all()
        )
        return TicketListResponse(tickets=[_orm_to_response(r) for r in rows], total=len(rows))
    except Exception as exc:
        log.exception("tickets.list.error", user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "TICKET_LIST_FAILED"},
        )


@app.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
    summary="Submit a ticket and run the agent graph synchronously",
)
def create_ticket(
    req: TicketCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Run the full agent graph and persist the result. Returns when the graph finishes."""
    ticket_id = str(uuid.uuid4())
    try:
        state = run_ticket(
            raw_text=req.text,
            user_id=current_user.id,
            channel="image" if req.image_b64 else "text",
        )
        ticket = TicketModel(
            id=ticket_id,
            user_id=current_user.id,
            raw_text=req.text,
            status=state.get("status", "resolved"),
            category=state.get("category"),
            intent=state.get("intent"),
            confidence=state.get("confidence"),
            resolution=state.get("resolution"),
            escalation_reason=state.get("escalation_reason"),
            trace_url=state.get("trace_url"),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        log.info("tickets.create.done", ticket_id=ticket.id, status=ticket.status)
        return _orm_to_response(ticket)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        log.exception("tickets.create.error", ticket_id=ticket_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "TICKET_CREATE_FAILED", "ticket_id": ticket_id},
        )


@app.get(
    "/tickets/{ticket_id}",
    response_model=TicketResponse,
    tags=["tickets"],
    summary="Fetch a single ticket by ID",
)
def get_ticket(
    ticket_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Return full ticket state. Returns 404 if the ticket is not found or not owned by the caller."""
    try:
        ticket = db.get(TicketModel, ticket_id)
        if ticket is None or ticket.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Ticket not found",
                    "code": "TICKET_NOT_FOUND",
                    "ticket_id": ticket_id,
                },
            )
        return _orm_to_response(ticket)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("tickets.get.error", ticket_id=ticket_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "TICKET_GET_FAILED", "ticket_id": ticket_id},
        )


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{ticket_id}")
async def websocket_ticket(websocket: WebSocket, ticket_id: str) -> None:
    """Stream per-node agent events to the client as the graph runs.

    Protocol
    --------
    Client → server (first message)::

        {"text": "I forgot my password", "user_id": "...", "image_b64": null}

    Server → client (one message per completed node)::

        {"node": "intake_node",  "status": "done", "output": {"category": "IT", ...}}
        {"node": "knowledge_node", "status": "done", "output": {...}}
        {"node": "action_node",  "status": "done", "output": {...}}
        {"node": "graph",        "status": "complete"}

    LangSmith per-node "running" events will be added in week 2 via callbacks.
    """
    await websocket.accept()
    try:
        payload: dict = await websocket.receive_json()
        raw_text: str = payload.get("text", "")
        user_id: str = payload.get("user_id", "anonymous")
        image_b64: Optional[str] = payload.get("image_b64")

        if not raw_text.strip():
            await websocket.send_json({"error": "'text' is required", "code": "MISSING_TEXT"})
            return

        initial_state = _build_ws_initial_state(ticket_id, raw_text, user_id, image_b64)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

        def _stream_graph() -> None:
            """Run graph.stream() synchronously in a background thread.

            Each completed node pushes one dict onto the async queue.
            None signals the coroutine to stop reading.
            """
            try:
                for step in langgraph_graph.stream(initial_state, stream_mode="updates"):
                    for node_name, node_output in step.items():
                        # Coerce non-JSON-serialisable values to strings.
                        safe: dict = {
                            k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                            for k, v in node_output.items()
                            if v is not None
                        }
                        asyncio.run_coroutine_threadsafe(
                            queue.put({"node": node_name, "status": "done", "output": safe}),
                            loop,
                        ).result(timeout=10)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(
                    queue.put({"node": "graph", "status": "error", "error": str(exc)}),
                    loop,
                ).result(timeout=5)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result(timeout=5)

        threading.Thread(target=_stream_graph, daemon=True).start()

        while True:
            message = await queue.get()
            if message is None:
                break
            await websocket.send_json(message)

        await websocket.send_json({"node": "graph", "status": "complete"})
        log.info("ws.complete", ticket_id=ticket_id)

    except WebSocketDisconnect:
        log.info("ws.disconnect", ticket_id=ticket_id)
    except Exception as exc:
        log.exception("ws.error", ticket_id=ticket_id)
        try:
            await websocket.send_json({"error": str(exc), "code": "WS_ERROR"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
