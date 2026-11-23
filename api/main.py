"""FastAPI application — ticket routes, WebSocket streaming, health endpoint."""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, nullcontext, suppress
from datetime import UTC, datetime, timedelta

import structlog
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from agents.graph import build_graph, build_initial_state, get_checkpointer
from agents.graph import graph as langgraph_graph
from api.a2a import router as a2a_router
from api.admin import _publish_sse, admin_router
from api.auth import _decode_token, auth_router, get_current_user
from api.email import send_ticket_notification
from api.models import (
    Base,
    CommentListResponse,
    CommentResponse,
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
    engine,
    get_db,
)
from api.org import org_router
from core.config import get_settings
from core.dspy_config import configure_dspy
from storage.gcs import upload_image_b64
from tracing.langsmith import get_trace_url

_cfg = get_settings()

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

# Maximum seconds the LangGraph execution may run before the WebSocket is aborted.
_GRAPH_EXECUTION_TIMEOUT: int = _cfg.graph_execution_timeout

# How often the stale-ticket recovery job runs (seconds).
_STALE_TICKET_POLL_SECONDS: int = _cfg.stale_ticket_poll_seconds

# How often each worker polls the FAISS sentinel file for cross-worker index updates.
_FAISS_RELOAD_POLL_SECONDS: int = _cfg.faiss_reload_poll_seconds


def _recover_stale_tickets() -> None:
    """Mark tickets stuck in 'pending'/'processing' beyond the graph timeout as failed.

    'pending'    → no runner ever claimed it (worker down).
    'processing' → a runner claimed it but died mid-run (crash / instance recycle).
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=_GRAPH_EXECUTION_TIMEOUT)
    db = SessionLocal()
    try:
        stale = (
            db.query(TicketModel)
            .filter(
                TicketModel.status.in_(["pending", "processing"]),
                TicketModel.created_at < cutoff,
            )
            .all()
        )
        for ticket in stale:
            ticket.status = "failed"
            ticket.escalation_reason = "Recovered: graph execution did not complete"
            log.warning("stale_ticket_recovery.recovered", ticket_id=ticket.id)
        if stale:
            db.commit()
    except Exception:
        db.rollback()
        log.exception("stale_ticket_recovery.db_error")
    finally:
        db.close()


async def _stale_ticket_recovery_loop() -> None:
    """Run _recover_stale_tickets every _STALE_TICKET_POLL_SECONDS indefinitely."""
    while True:
        await asyncio.sleep(_STALE_TICKET_POLL_SECONDS)
        try:
            _recover_stale_tickets()
        except Exception:
            log.exception("stale_ticket_recovery.loop_error")


async def _faiss_reload_loop() -> None:
    """Per-worker sentinel poller: reload the in-process FAISS retriever when
    another worker has persisted an updated index after a KB upload.

    Each worker maintains its own last_ts so a freshly-started worker whose
    __init__ already loaded from disk does not immediately trigger a redundant
    reload on the first poll.
    """
    from pathlib import Path
    sentinel_path = Path(os.environ.get("FAISS_RELOAD_SENTINEL", "faiss_reload.sentinel"))
    last_ts: float = 0.0
    while True:
        await asyncio.sleep(_FAISS_RELOAD_POLL_SECONDS)
        try:
            if sentinel_path.exists():
                ts = float(sentinel_path.read_text().strip())
                if ts > last_ts:
                    from rag.retriever import get_retriever
                    get_retriever().reload()
                    last_ts = ts
                    log.info("faiss_reload.triggered", sentinel_ts=ts)
        except Exception:
            log.exception("faiss_reload.loop_error")


# How often the worker scans for unclaimed tickets, and how long it waits before
# claiming one (a grace window that lets a browser WebSocket claim first so the
# user still gets the live per-node timeline).
_PENDING_TICKET_POLL_SECONDS: float = 2.0
_PENDING_TICKET_GRACE_SECONDS: int = 5


async def _pending_ticket_worker() -> None:
    """Process tickets that no WebSocket claimed (API clients, dropped connections).

    Ticket processing is decoupled from the client connection: every ticket is
    guaranteed to run here even if a WebSocket never opens. The claim is atomic,
    so this never double-runs a ticket a WebSocket is already handling.
    """
    while True:
        await asyncio.sleep(_PENDING_TICKET_POLL_SECONDS)
        try:
            cutoff = datetime.now(UTC) - timedelta(seconds=_PENDING_TICKET_GRACE_SECONDS)
            db = SessionLocal()
            try:
                ids = [
                    r.id
                    for r in db.query(TicketModel.id)
                    .filter(TicketModel.status == "pending", TicketModel.created_at < cutoff)
                    .order_by(TicketModel.created_at.asc())
                    .limit(20)
                    .all()
                ]
            finally:
                db.close()
            for tid in ids:
                if _claim_ticket(tid):
                    try:
                        await _process_ticket(tid)
                    except Exception:
                        log.exception("pending_worker.process_error", ticket_id=tid)
        except Exception:
            log.exception("pending_worker.loop_error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: create DB tables, configure DSPy, init checkpointer, start recovery loop.
    Shutdown: cancel recovery loop, release checkpointer connection.
    """
    global langgraph_graph
    Base.metadata.create_all(bind=engine)
    configure_dspy()

    checkpointer_cm = get_checkpointer()
    async with (checkpointer_cm if checkpointer_cm is not None else nullcontext()) as checkpointer:
        if checkpointer is not None:
            await checkpointer.setup()
            langgraph_graph = build_graph(checkpointer)
            log.info("app.startup", db_url=str(engine.url), checkpointer="postgres")
        else:
            log.info("app.startup", db_url=str(engine.url), checkpointer="none")

        recovery_task = asyncio.create_task(_stale_ticket_recovery_loop())
        faiss_reload_task = asyncio.create_task(_faiss_reload_loop())
        pending_worker_task = asyncio.create_task(_pending_ticket_worker())
        try:
            yield
        finally:
            log.info("app.shutdown")
            for task in (recovery_task, faiss_reload_task, pending_worker_task):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


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

    # LLM provider config check — cheap (verifies a key is present, no round-trip),
    # so the UI "agents online" badge reflects real reachability, not just liveness.
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    _key_var = {
        "groq": "GROQ_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(provider)
    if _key_var and os.getenv(_key_var):
        checks["llm"] = "ok"
    else:
        checks["llm"] = f"error: {_key_var or 'LLM_PROVIDER'} not configured"

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
        ) from exc


@app.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
    summary="Create a ticket — processed server-side; open /ws/{ticket_id} for the live timeline",
)
@limiter.limit("30/minute")
def create_ticket(
    request: Request,
    req: TicketCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Persist a pending ticket and return immediately.

    Processing is decoupled from the client: a background worker runs the agent
    graph whether or not a WebSocket connects, so API clients work too. Opening
    ``/ws/{ticket_id}`` claims the ticket first and streams the live per-node
    timeline; the result is always persisted and visible in ticket history.
    """
    ticket_id = str(uuid.uuid4())
    try:
        image_url: str | None = None
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
        ) from exc


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
        ) from exc


@app.post(
    "/tickets/{ticket_id}/confirm-action",
    response_model=TicketResponse,
    tags=["tickets"],
    summary="Confirm a destructive action awaiting explicit authorization",
)
async def confirm_action(
    ticket_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Execute a destructive action the owner has explicitly confirmed.

    Atomically moves the ticket from 'awaiting_confirmation' to 'processing' so a
    double-click (or two tabs) can never run the action twice, then resumes the
    graph from the ORIGINAL triage (no LLM re-classification) through the same
    _process_ticket path as every other ticket — persistence, admin SSE and the
    owner email included.

    Returns 404 if the ticket does not exist or is not owned by the caller.
    Returns 409 if the ticket is not awaiting confirmation (or is already being confirmed).
    """
    ticket = db.get(TicketModel, ticket_id)
    if ticket is None or ticket.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ticket not found", "code": "TICKET_NOT_FOUND"},
        )
    if ticket.status != "awaiting_confirmation" or not _claim_ticket(
        ticket_id, from_status="awaiting_confirmation"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Ticket is not awaiting confirmation", "code": "INVALID_TICKET_STATUS"},
        )

    await _process_ticket(ticket_id, resume_confirmed=True)

    db.expire_all()  # _process_ticket committed through its own session
    ticket = db.get(TicketModel, ticket_id)
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


# ── Ticket processing (decoupled from the client connection) ──────────────────
# The agent graph runs here, not inside the WebSocket. Both the WebSocket (for a
# live timeline) and the background worker (for API clients / dropped sockets)
# call _process_ticket after winning an atomic claim, so a ticket is always
# processed exactly once regardless of whether a client is watching.

_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"resolved", "escalated", "failed", "awaiting_confirmation"}
)


def _load_org_context(db: Session, ticket: TicketModel) -> dict:
    """Return org-scoped runtime context (KB docs, API/SMTP/Slack overrides)."""
    ctx: dict = {
        "org_name": "",
        "org_kb_docs": [],
        "org_api_url": None,
        "support_email": os.getenv("SUPPORT_EMAIL", ""),
        "slack_webhook_url": None,
    }
    if ticket.org_id:
        kb_rows = (
            db.query(OrgKnowledgeDocModel)
            .filter(OrgKnowledgeDocModel.org_id == ticket.org_id)
            .all()
        )
        ctx["org_kb_docs"] = [{"title": r.title, "content": r.content} for r in kb_rows]
        org_cfg = db.get(OrgConfigModel, ticket.org_id)
        if org_cfg:
            ctx["org_api_url"] = org_cfg.itsm_url or None
            ctx["slack_webhook_url"] = org_cfg.slack_webhook_url or None
        org_obj = db.get(OrganizationModel, ticket.org_id)
        ctx["org_name"] = org_obj.name if org_obj else ""
    return ctx


def _claim_ticket(ticket_id: str, from_status: str = "pending") -> bool:
    """Atomically move a ticket from ``from_status`` to 'processing'.

    Returns True only for the single caller that won the claim, so the WebSocket
    and the background worker never process the same ticket twice — and a
    confirmed destructive action can never be executed twice.
    """
    db = SessionLocal()
    try:
        updated = (
            db.query(TicketModel)
            .filter(TicketModel.id == ticket_id, TicketModel.status == from_status)
            .update({"status": "processing"}, synchronize_session=False)
        )
        db.commit()
        return updated == 1
    except Exception:
        db.rollback()
        log.exception("ticket.claim_failed", ticket_id=ticket_id)
        return False
    finally:
        db.close()


async def _process_ticket(
    ticket_id: str,
    on_node: Callable[[str, dict], Awaitable[None]] | None = None,
    resume_confirmed: bool = False,
) -> dict:
    """Run the agent graph for an already-claimed ticket, persist, and notify.

    Call with ``on_node`` to stream per-node events to a WebSocket; call without
    it from the background worker. Opens its own DB session and never depends on
    a live client connection. Returns the terminal {status, resolution,
    escalation_reason, assignee_group, trace_url}.

    With ``resume_confirmed=True`` the graph resumes a ticket the owner has
    confirmed: the persisted triage is carried in (intake_node short-circuits, so
    the LLM never re-classifies) and ``action_confirmed`` is set.
    """
    db = SessionLocal()
    try:
        ticket = db.get(TicketModel, ticket_id)
        if ticket is None:
            return {"status": "failed"}
        owner = db.get(UserModel, ticket.user_id)
        user_email = owner.email if owner else ""
        ctx = _load_org_context(db, ticket)

        initial_state = build_initial_state(
            ticket.raw_text,
            user_email or ticket.user_id,
            ticket.channel or "text",
            org_id=ticket.org_id,
            raw_image_b64=ticket.raw_image_b64,
            user_email=user_email,
            **ctx,
        )
        if resume_confirmed:
            initial_state["category"] = ticket.category  # type: ignore[typeddict-item]
            initial_state["intent"] = ticket.intent or ticket.category  # type: ignore[typeddict-item]
            initial_state["priority"] = ticket.priority
            initial_state["confidence"] = ticket.confidence
            initial_state["action_confirmed"] = True
        final_state: dict = {}

        async def _run() -> None:
            async for chunk in langgraph_graph.astream(
                initial_state,
                config={"configurable": {"thread_id": ticket_id}},
                stream_mode="updates",
            ):
                for node_name, node_output in chunk.items():
                    final_state.update(node_output)
                    if on_node is not None:
                        await on_node(node_name, node_output)

        try:
            await asyncio.wait_for(_run(), timeout=_GRAPH_EXECUTION_TIMEOUT)
        except TimeoutError:
            log.error("ticket.process_timeout", ticket_id=ticket_id)
            ticket.status = "failed"
            ticket.escalation_reason = "Graph execution timed out"
            db.commit()
            return {"status": "failed", "escalation_reason": "Graph execution timed out"}
        except asyncio.CancelledError:
            # Client vanished (WS path) — keep going so results still persist.
            log.info("ticket.process_cancelled", ticket_id=ticket_id)
        except Exception as exc:
            log.exception("ticket.process_error", ticket_id=ticket_id, error=str(exc))

        trace_url: str | None = get_trace_url() or final_state.get("trace_url")
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
        log.info("ticket.processed", ticket_id=ticket_id, status=ticket.status)

        result = {
            "status": ticket.status,
            "resolution": ticket.resolution,
            "escalation_reason": ticket.escalation_reason,
            "assignee_group": ticket.assignee_group,
            "category": ticket.category,
            "trace_url": trace_url,
        }

        if ticket.org_id:
            _publish_sse(ticket.org_id, {
                "ticket_id": ticket.id,
                "status": ticket.status,
                "category": ticket.category,
                "resolution": ticket.resolution,
                "escalation_reason": ticket.escalation_reason,
                "user_email": user_email or None,
                "priority": ticket.priority,
                "assignee_group": ticket.assignee_group,
            })

        # Owner email on resolution (escalations notify from escalation_node).
        if ticket.status == "resolved" and user_email:
            try:
                asyncio.get_running_loop().run_in_executor(
                    None, send_ticket_notification,
                    user_email, ticket_id, ticket.status,
                    ticket.resolution, ticket.escalation_reason,
                )
            except Exception:
                log.warning("ticket.notify_failed", ticket_id=ticket_id)

        return result
    finally:
        db.close()


async def _observe_ticket(ticket_id: str, websocket: WebSocket) -> dict:
    """Stream a ticket's outcome to a WebSocket that did NOT win the claim.

    Used when another runner (the worker, or a prior connection) is already
    processing — polls the DB until terminal and emits a synthetic final event
    so the client's timeline still renders the result.
    """
    deadline = time.monotonic() + _GRAPH_EXECUTION_TIMEOUT
    while time.monotonic() < deadline:
        db = SessionLocal()
        try:
            t = db.get(TicketModel, ticket_id)
            if t is None:
                return {"status": "failed"}
            fields = {
                "status": t.status,
                "resolution": t.resolution,
                "escalation_reason": t.escalation_reason,
                "assignee_group": t.assignee_group,
                "category": t.category,
                "trace_url": t.trace_url,
            }
        finally:
            db.close()
        if fields["status"] in _TERMINAL_STATUSES:
            with suppress(Exception):
                await websocket.send_json({
                    "node": "action_node",
                    "status": "done",
                    "output": {k: str(v) for k, v in fields.items() if v is not None},
                })
            return fields
        await asyncio.sleep(0.4)
    return {"status": "failed"}


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
        for _ in range(_cfg.ticket_poll_attempts):
            ticket = db.query(TicketModel).filter_by(id=ticket_id).first()
            if ticket:
                break
            await asyncio.sleep(_cfg.ticket_poll_interval)

        if ticket is None:
            await websocket.send_json({"error": "ticket not found", "code": "TICKET_NOT_FOUND"})
            await websocket.close(1008)
            return

        log.info("ws.ticket_found", ticket_id=ticket_id, status=ticket.status)

        try:
            payload: dict = await asyncio.wait_for(
                websocket.receive_json(), timeout=5.0
            )
        except TimeoutError:
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

        # The WebSocket no longer runs the graph itself — processing is decoupled.
        # Win the atomic claim → run the graph here and stream the live timeline.
        # Lose it (the background worker or an earlier connection is already on it,
        # or it is already done) → observe the outcome from the DB. Either way the
        # ticket is guaranteed to be processed exactly once.
        async def _send_node(node_name: str, node_output: dict) -> None:
            with suppress(Exception):
                await websocket.send_json({
                    "node": node_name,
                    "status": "done",
                    "output": {
                        k: str(v)
                        for k, v in node_output.items()
                        if k in _STREAM_FIELDS and v is not None
                    },
                })

        if _claim_ticket(ticket_id):
            result = await _process_ticket(ticket_id, on_node=_send_node)
        else:
            result = await _observe_ticket(ticket_id, websocket)

        try:
            await asyncio.sleep(0.3)
            if result.get("status") == "failed":
                await websocket.send_json(
                    {"error": "An internal error occurred.", "code": "WS_PROCESSING_FAILED"}
                )
            else:
                await websocket.send_json({
                    "node": "graph",
                    "status": "complete",
                    "resolution": result.get("resolution"),
                    "trace_url": result.get("trace_url"),
                })
            log.info("ws.complete", ticket_id=ticket_id, status=result.get("status"))
        except (WebSocketDisconnect, RuntimeError):
            log.info("ws.complete.client_gone", ticket_id=ticket_id)

    except WebSocketDisconnect:
        log.info("ws.disconnect", ticket_id=ticket_id)
    except Exception:
        log.exception("ws.error", ticket_id=ticket_id)
        with suppress(Exception):
            await websocket.send_json({"error": "An internal error occurred.", "code": "WS_ERROR"})
    finally:
        db.close()
        with suppress(Exception):
            await websocket.close()


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
