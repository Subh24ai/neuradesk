"""FastAPI application — ticket routes, WebSocket streaming, health endpoint."""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from agents.graph import build_initial_state, graph as langgraph_graph
from storage.gcs import upload_image_b64
from tracing.langsmith import get_trace_url
from api.a2a import router as a2a_router
from api.admin import admin_router, _publish_sse
from api.auth import auth_router, _decode_token, get_current_user
from api.email import send_ticket_notification
from api.org import org_router
from core.dspy_config import configure_dspy
from api.models import (
    Base,
    OrganizationModel,
    OrgConfigModel,
    OrgKnowledgeDocModel,
    SessionLocal,
    TicketCommentModel,
    TicketCreateRequest,
    TicketListResponse,
    TicketModel,
    TicketResponse,
    UserModel,
    CommentListResponse,
    CommentResponse,
    engine,
    get_db,
)

load_dotenv()
log = structlog.get_logger(__name__)

# Absolute path to the pre-built React SPA.  Present in production Docker image;
# absent in local dev (frontend runs on its own dev server with the Vite proxy).
_FRONTEND_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
    "dist",
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
# Disabled in test/development so the test suite doesn't trip its own limits
_RATELIMIT_ENABLED = os.getenv("APP_ENV", "development") == "production"
limiter = Limiter(key_func=get_remote_address, enabled=_RATELIMIT_ENABLED)

# Fields forwarded to the client in per-node WebSocket events.
_STREAM_FIELDS = frozenset(
    ("category", "confidence", "resolution", "status", "escalation_reason")
)


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

# ── Middleware ─────────────────────────────────────────────────────────────────

_ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Serve pre-built React SPA assets when the dist folder is present.
# The /assets mount must be registered before API routes so Starlette's
# sub-application lookup does not fall through to the SPA catch-all below.
_assets_dir = os.path.join(_FRONTEND_DIST, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="spa_assets")

app.include_router(auth_router)
app.include_router(org_router)
app.include_router(admin_router)
app.include_router(a2a_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"], summary="Liveness probe")
def health() -> dict:
    """Return 200 when the API process is running."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/health/deep", tags=["meta"], summary="Readiness probe — checks DB and RAG index")
def health_deep() -> dict:
    """Verify DB connectivity and RAG index availability. Returns 503 if any dependency is down."""
    checks: dict[str, str] = {}

    # Database check
    try:
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        db.close()
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    # RAG index check
    try:
        from rag.retriever import HybridRetriever
        HybridRetriever.get()
        checks["rag"] = "ok"
    except Exception as exc:
        checks["rag"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=checks)
    return {"status": "ok", "checks": checks}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _orm_to_response(ticket: TicketModel) -> TicketResponse:
    """Map a TicketModel ORM row to the Pydantic response schema."""
    return TicketResponse(
        ticket_id=ticket.id,
        status=ticket.status,
        raw_text=ticket.raw_text,
        category=ticket.category,
        confidence=ticket.confidence,
        resolution=ticket.resolution,
        escalation_reason=ticket.escalation_reason,
        image_url=ticket.image_url,
        trace_url=ticket.trace_url,
        created_at=ticket.created_at,
    )



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
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketListResponse:
    """Return tickets belonging to the caller, newest first, with pagination."""
    try:
        q = db.query(TicketModel).filter(TicketModel.user_id == current_user.id)
        total = q.count()
        rows = q.order_by(TicketModel.created_at.desc()).offset(offset).limit(limit).all()
        return TicketListResponse(tickets=[_orm_to_response(r) for r in rows], total=total, limit=limit, offset=offset)
    except Exception as exc:
        log.exception("tickets.list.error", user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Request could not be processed.", "code": "TICKET_LIST_FAILED"},
        )


@app.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
    summary="Create a pending ticket — caller must open /ws/{ticket_id} to run the agent graph",
)
@limiter.limit("30/minute")
def create_ticket(
    request: Request,
    req: TicketCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Persist a pending ticket and return immediately. The agent graph runs over WebSocket."""
    ticket_id = str(uuid.uuid4())
    try:
        image_url: Optional[str] = None
        if req.image_b64:
            image_url = upload_image_b64(ticket_id, req.image_b64)

        ticket = TicketModel(
            id=ticket_id,
            user_id=current_user.id,
            org_id=current_user.org_id,
            raw_text=req.text,
            raw_image_b64=req.image_b64,
            image_url=image_url,
            channel="image" if req.image_b64 else "text",
            status="pending",
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        log.info("tickets.create.pending", ticket_id=ticket.id)
        return _orm_to_response(ticket)
    except Exception as exc:
        db.rollback()
        log.exception("tickets.create.error", ticket_id=ticket_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Request could not be processed.", "code": "TICKET_CREATE_FAILED", "ticket_id": ticket_id},
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
            detail={"error": "Request could not be processed.", "code": "TICKET_GET_FAILED", "ticket_id": ticket_id},
        )


@app.post(
    "/tickets/{ticket_id}/confirm-action",
    response_model=TicketResponse,
    tags=["tickets"],
    summary="Confirm a destructive action awaiting explicit authorization",
)
def confirm_action(
    ticket_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Re-run the agent graph with action_confirmed=True for a ticket in awaiting_confirmation status.

    Returns 404 if the ticket does not exist or is not owned by the caller.
    Returns 409 if the ticket is not in 'awaiting_confirmation' status.
    """
    ticket = db.get(TicketModel, ticket_id)
    if ticket is None or ticket.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ticket not found", "code": "TICKET_NOT_FOUND"},
        )
    if ticket.status != "awaiting_confirmation":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Ticket is not awaiting confirmation", "code": "INVALID_TICKET_STATUS"},
        )

    # Load org context (mirrors WS handler logic).
    org_kb_docs: list[dict] = []
    org_api_url: Optional[str] = None
    org_api_secret: Optional[str] = None
    org_name: str = ""
    support_email: str = os.getenv("SUPPORT_EMAIL", "")
    slack_webhook_url: Optional[str] = None
    if ticket.org_id:
        kb_rows = (
            db.query(OrgKnowledgeDocModel)
            .filter(OrgKnowledgeDocModel.org_id == ticket.org_id)
            .all()
        )
        org_kb_docs = [{"title": r.title, "content": r.content} for r in kb_rows]
        org_cfg = db.get(OrgConfigModel, ticket.org_id)
        if org_cfg:
            org_api_url = org_cfg.itsm_url or None
            slack_webhook_url = org_cfg.slack_webhook_url or None
        org_obj = db.get(OrganizationModel, ticket.org_id)
        org_name = org_obj.name if org_obj else ""

    initial_state = build_initial_state(
        ticket.raw_text, current_user.email, ticket.channel or "text",
        org_id=ticket.org_id,
        org_name=org_name,
        org_kb_docs=org_kb_docs,
        org_api_url=org_api_url,
        org_api_secret=org_api_secret,
        raw_image_b64=ticket.raw_image_b64,
        support_email=support_email,
        user_email=current_user.email,
        slack_webhook_url=slack_webhook_url,
    )
    initial_state["action_confirmed"] = True  # type: ignore[index]

    final_state: dict = langgraph_graph.invoke(initial_state)

    ticket.status = final_state.get("status", "resolved")
    ticket.category = final_state.get("category")
    ticket.intent = final_state.get("intent")
    ticket.confidence = final_state.get("confidence")
    ticket.resolution = final_state.get("resolution")
    ticket.escalation_reason = final_state.get("escalation_reason")
    ticket.assignee_group = final_state.get("assignee_group")
    ticket.priority = final_state.get("priority")
    db.commit()
    db.refresh(ticket)

    log.info("tickets.confirm_action.done", ticket_id=ticket_id, status=ticket.status)
    return _orm_to_response(ticket)


@app.post(
    "/tickets/{ticket_id}/cancel",
    response_model=TicketResponse,
    tags=["tickets"],
    summary="Cancel a destructive action awaiting confirmation",
)
def cancel_action(
    ticket_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Set an awaiting_confirmation ticket to escalated.

    Returns 404 if the ticket does not exist or is not owned by the caller.
    Returns 409 if the ticket is not in 'awaiting_confirmation' status.
    """
    ticket = db.get(TicketModel, ticket_id)
    if ticket is None or ticket.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ticket not found", "code": "TICKET_NOT_FOUND"},
        )
    if ticket.status != "awaiting_confirmation":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Ticket is not awaiting confirmation", "code": "INVALID_TICKET_STATUS"},
        )

    ticket.status = "escalated"
    ticket.escalation_reason = "Destructive action cancelled by user."
    db.commit()
    db.refresh(ticket)

    log.info("tickets.cancel_action.done", ticket_id=ticket_id)
    return _orm_to_response(ticket)


@app.get(
    "/tickets/{ticket_id}/comments",
    response_model=CommentListResponse,
    tags=["tickets"],
    summary="Get admin comments on a ticket visible to the owner",
)
def get_ticket_comments(
    ticket_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    """Return all admin notes on a ticket. Only accessible by the ticket owner."""
    ticket = db.get(TicketModel, ticket_id)
    if ticket is None or ticket.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ticket not found", "code": "TICKET_NOT_FOUND"},
        )
    rows = (
        db.query(TicketCommentModel)
        .filter(TicketCommentModel.ticket_id == ticket_id)
        .order_by(TicketCommentModel.created_at.asc())
        .all()
    )
    comments = [
        CommentResponse(
            id=c.id, ticket_id=c.ticket_id, content=c.content,
            is_admin_note=c.is_admin_note, created_at=c.created_at,
        )
        for c in rows
    ]
    return CommentListResponse(comments=comments, total=len(comments))


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{ticket_id}")
async def websocket_ticket(
    websocket: WebSocket,
    ticket_id: str,
) -> None:
    """Run the agent graph for a pending ticket and stream the final result.

    Protocol
    --------
    Client → server (first message)::

        {"user_id": "..."}

    Server → client::

        {"node": "graph", "status": "complete", "resolution": "...", "trace_url": "..."}
    """
    log.info("ws.handler_entered", ticket_id=ticket_id)
    await websocket.accept()
    log.info("ws.accepted", ticket_id=ticket_id)
    db = SessionLocal()
    try:
        ticket = None
        for _ in range(10):  # up to 2 seconds
            ticket = db.query(TicketModel).filter_by(id=ticket_id).first()
            if ticket:
                break
            await asyncio.sleep(0.2)

        if ticket is None:
            await websocket.send_json({"error": "ticket not found", "code": "TICKET_NOT_FOUND"})
            await websocket.close(1008)
            return

        log.info("ws.ticket_found", ticket_id=ticket_id, status=ticket.status)

        try:
            payload: dict = await asyncio.wait_for(
                websocket.receive_json(), timeout=5.0
            )
        except asyncio.TimeoutError:
            await websocket.send_json({"error": "Auth timeout", "code": "WS_AUTH_TIMEOUT"})
            await websocket.close(1008)
            return

        # Validate JWT sent in the first message
        token: str = payload.get("token", "")
        try:
            jwt_payload = _decode_token(token)
            caller_id: str = jwt_payload.get("sub", "")
        except Exception:
            await websocket.send_json({"error": "Unauthorized", "code": "WS_UNAUTHORIZED"})
            await websocket.close(1008)
            return

        if ticket.user_id != caller_id:
            await websocket.send_json({"error": "Ticket not owned by caller", "code": "WS_FORBIDDEN"})
            await websocket.close(1008)
            return

        owner = db.get(UserModel, ticket.user_id)
        display_name: str = owner.email if owner else caller_id

        # Load org context: per-org KB docs and API config overrides.
        org_kb_docs: list[dict] = []
        org_api_url: Optional[str] = None
        org_api_secret: Optional[str] = None
        org_name: str = ""
        support_email: str = os.getenv("SUPPORT_EMAIL", "")
        slack_webhook_url: Optional[str] = None
        if ticket.org_id:
            kb_rows = (
                db.query(OrgKnowledgeDocModel)
                .filter(OrgKnowledgeDocModel.org_id == ticket.org_id)
                .all()
            )
            org_kb_docs = [{"title": r.title, "content": r.content} for r in kb_rows]
            org_cfg = db.get(OrgConfigModel, ticket.org_id)
            if org_cfg:
                org_api_url = org_cfg.itsm_url or None
                org_api_secret = None  # secret managed server-side only
                support_email = org_cfg.smtp_host and support_email or support_email
                slack_webhook_url = org_cfg.slack_webhook_url or None
            org_obj = db.get(OrganizationModel, ticket.org_id)
            org_name = org_obj.name if org_obj else ""

        initial_state = build_initial_state(
            ticket.raw_text, display_name, ticket.channel or "text",
            org_id=ticket.org_id,
            org_name=org_name,
            org_kb_docs=org_kb_docs,
            org_api_url=org_api_url,
            org_api_secret=org_api_secret,
            raw_image_b64=ticket.raw_image_b64,
            support_email=support_email,
            user_email=owner.email if owner else "",
            slack_webhook_url=slack_webhook_url,
        )
        final_state: dict = {}

        try:
            async for chunk in langgraph_graph.astream(initial_state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    log.debug("ws.node_complete", ticket_id=ticket_id, node=node_name)
                    try:
                        await websocket.send_json({
                            "node": node_name,
                            "status": "done",
                            "output": {
                                k: str(v)
                                for k, v in node_output.items()
                                if k in _STREAM_FIELDS and v is not None
                            },
                        })
                    except Exception:
                        pass
                    final_state.update(node_output)
        except asyncio.CancelledError:
            log.info("ws.astream_cancelled", ticket_id=ticket_id)
            # Do NOT re-raise — DB commit must still run below.
        except BaseException as exc:
            log.exception("ws.astream_failed", ticket_id=ticket_id, error=str(exc))

        # Always persist to DB regardless of whether the client is still connected.
        trace_url: Optional[str] = get_trace_url() or final_state.get("trace_url")
        if not final_state:
            ticket.status = "failed"
            ticket.escalation_reason = "Graph execution failed before any node completed"
        else:
            ticket.status = final_state.get("status", "failed")
        ticket.category = final_state.get("category")
        ticket.intent = final_state.get("intent")
        ticket.confidence = final_state.get("confidence")
        ticket.resolution = final_state.get("resolution")
        ticket.escalation_reason = final_state.get("escalation_reason")
        ticket.assignee_group = final_state.get("assignee_group")
        ticket.priority = final_state.get("priority")
        ticket.trace_url = trace_url
        db.commit()
        log.info("ws.ticket.saved", ticket_id=ticket_id, status=ticket.status)

        if ticket.org_id:
            _publish_sse(ticket.org_id, {
                "ticket_id": ticket.id,
                "status": ticket.status,
                "category": ticket.category,
                "resolution": ticket.resolution,
                "escalation_reason": ticket.escalation_reason,
                "user_email": owner.email if owner else None,
                "priority": ticket.priority,
                "assignee_group": ticket.assignee_group,
            })

        # Notify the owner when their ticket is resolved.
        # Escalated tickets are notified directly from escalation_node (Fix 1)
        # to keep notification logic self-contained in each node.
        if ticket.status == "resolved" and owner:
            asyncio.get_running_loop().run_in_executor(
                None,
                send_ticket_notification,
                owner.email,
                ticket_id,
                ticket.status,
                ticket.resolution,
                ticket.escalation_reason,
            )

        try:
            await asyncio.sleep(0.5)
            await websocket.send_json({
                "node": "graph",
                "status": "complete",
                "resolution": final_state.get("resolution"),
                "trace_url": trace_url,
            })
            log.info("ws.complete", ticket_id=ticket_id)
        except (WebSocketDisconnect, RuntimeError):
            log.info("ws.complete.client_gone", ticket_id=ticket_id)

    except WebSocketDisconnect:
        log.info("ws.disconnect", ticket_id=ticket_id)
    except Exception as exc:
        log.exception("ws.error", ticket_id=ticket_id)
        try:
            await websocket.send_json({"error": "An internal error occurred.", "code": "WS_ERROR"})
        except Exception:
            pass
    finally:
        db.close()
        try:
            await websocket.close()
        except Exception:
            pass


# ── SPA catch-all — must be registered LAST ───────────────────────────────────
# Serves index.html for every path not handled by the API routes above.
# React Router then handles client-side navigation.

@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_spa(full_path: str) -> FileResponse:
    """Return the React SPA shell for any unknown path."""
    index = os.path.join(_FRONTEND_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend not built — run: cd frontend && npm run build")
