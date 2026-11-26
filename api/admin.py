"""Admin-only endpoints — org-wide ticket views, resolution, comments, knowledge base, and invites."""

import asyncio
import io
import json
import secrets
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.auth import _decode_token, get_current_user
from api.models import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    InviteCreateRequest,
    InviteListResponse,
    InviteModel,
    InviteResponse,
    KnowledgeDocCreate,
    KnowledgeDocListResponse,
    KnowledgeDocResponse,
    OrgKnowledgeDocModel,
    TicketCommentModel,
    TicketListResponse,
    TicketModel,
    TicketResolveRequest,
    TicketResponse,
    TokenBlocklistModel,
    UserModel,
    get_db,
)

log = structlog.get_logger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# ── SSE state ─────────────────────────────────────────────────────────────────
# Events are persisted to the admin_events table and polled by each SSE
# connection, so the dashboard feed is correct across multiple web workers
# (in-process queues would only reach admins on the same worker).

_SSE_POLL_SECONDS: float = 1.5
# Delete delivered events older than this on publish so the table stays small.
_SSE_EVENT_TTL_SECONDS: int = 3600


def _publish_sse(org_id: str, event_data: dict) -> None:
    """Persist a ticket event for org_id so every admin SSE connection sees it.

    Opens a short-lived session and never raises — ticket processing must not
    fail because the dashboard feed is unavailable.
    """
    from api.models import AdminEventModel, SessionLocal

    db = SessionLocal()
    try:
        db.add(AdminEventModel(org_id=org_id, payload=json.dumps(event_data)))
        # Opportunistic prune of old, already-delivered events.
        cutoff = datetime.now(UTC) - timedelta(seconds=_SSE_EVENT_TTL_SECONDS)
        db.query(AdminEventModel).filter(AdminEventModel.created_at < cutoff).delete()
        db.commit()
    except Exception:
        db.rollback()
        log.warning("admin.sse.publish_failed", org_id=org_id)
    finally:
        db.close()


def _require_admin(user: UserModel) -> None:
    """Raise 403 if the user is not an org admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin access required", "code": "FORBIDDEN"},
        )


def _orm_to_response(ticket: TicketModel, db: Session | None = None) -> TicketResponse:
    user_email: str | None = None
    if db is not None:
        user = db.get(UserModel, ticket.user_id)
        user_email = user.email if user else None
    return TicketResponse(
        ticket_id=ticket.id,
        status=ticket.status,
        category=ticket.category,
        confidence=ticket.confidence,
        resolution=ticket.resolution,
        escalation_reason=ticket.escalation_reason,
        admin_note=ticket.admin_note,
        assignee_group=ticket.assignee_group,
        priority=ticket.priority,
        user_email=user_email,
        trace_url=ticket.trace_url,
        created_at=ticket.created_at,
        raw_text=ticket.raw_text,
    )


# ── Ticket list & stats ───────────────────────────────────────────────────────

@admin_router.get(
    "/tickets",
    response_model=TicketListResponse,
    summary="List all tickets in the organisation (admin only)",
)
def list_org_tickets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(
        None, alias="status", max_length=120,
        description="Comma-separated statuses to include",
    ),
    search: str | None = Query(
        None, alias="q", max_length=200,
        description="Search request text, resolution, category, or the employee's email",
    ),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketListResponse:
    """Return org-wide tickets ordered by newest first. Admin only."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    q = db.query(TicketModel).filter(TicketModel.org_id == current_user.org_id)
    statuses = [x.strip() for x in (status_filter or "").split(",") if x.strip()]
    if statuses:
        q = q.filter(TicketModel.status.in_(statuses))
    term = (search or "").strip()
    if term:
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        matching_users = db.query(UserModel.id).filter(
            UserModel.org_id == current_user.org_id, UserModel.email.ilike(like, escape="\\")
        )
        q = q.filter(or_(
            TicketModel.raw_text.ilike(like, escape="\\"),
            TicketModel.resolution.ilike(like, escape="\\"),
            TicketModel.category.ilike(like, escape="\\"),
            TicketModel.user_id.in_(matching_users),
        ))

    total = q.count()
    rows = q.order_by(TicketModel.created_at.desc()).offset(offset).limit(limit).all()
    return TicketListResponse(
        tickets=[_orm_to_response(r, db) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.get("/stats", summary="Aggregate ticket statistics for the organisation (admin only)")
def org_stats(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return resolved/escalated/pending counts for the org."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    def _count(s: str) -> int:
        return (
            db.query(TicketModel)
            .filter(TicketModel.org_id == current_user.org_id, TicketModel.status == s)
            .count()
        )

    total = db.query(TicketModel).filter(TicketModel.org_id == current_user.org_id).count()
    resolved_q = db.query(TicketModel).filter(
        TicketModel.org_id == current_user.org_id, TicketModel.status == "resolved"
    )
    human_resolved = resolved_q.filter(TicketModel.resolved_by.isnot(None)).count()
    resolved = resolved_q.count()
    return {
        "total": total,
        "resolved": resolved,
        # Resolved by the agents with no admin involvement vs. by an admin.
        "auto_resolved": resolved - human_resolved,
        "human_resolved": human_resolved,
        "processing": _count("processing"),
        "escalated": _count("escalated"),
        "pending": _count("pending"),
        "failed": _count("failed"),
        "awaiting_confirmation": _count("awaiting_confirmation"),
    }


# ── Ticket resolution ─────────────────────────────────────────────────────────

@admin_router.patch(
    "/tickets/{ticket_id}",
    response_model=TicketResponse,
    summary="Manually resolve or update a ticket (admin only)",
)
def resolve_ticket(
    ticket_id: str,
    req: TicketResolveRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    """Allow an admin to manually set ticket status and add a resolution note."""
    _require_admin(current_user)

    ticket = db.get(TicketModel, ticket_id)
    if not ticket or ticket.org_id != current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ticket not found", "code": "TICKET_NOT_FOUND"},
        )

    ticket.status = req.status
    if req.admin_note:
        ticket.admin_note = req.admin_note
        if req.status == "resolved":
            # The admin's reply is the final word. An escalated ticket may carry
            # the agents' draft answer (which the system chose not to trust) —
            # it must never outrank what a human decided.
            ticket.resolution = req.admin_note
    ticket.resolved_by = current_user.id
    ticket.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(ticket)

    log.info("admin.ticket_resolved", ticket_id=ticket_id, status=req.status, admin=current_user.id)
    return _orm_to_response(ticket, db)


# ── Ticket comments ───────────────────────────────────────────────────────────

@admin_router.post(
    "/tickets/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an admin note/comment to a ticket",
)
def add_comment(
    ticket_id: str,
    req: CommentCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentResponse:
    """Attach a visible comment/note to a ticket. Visible to the ticket owner."""
    _require_admin(current_user)

    ticket = db.get(TicketModel, ticket_id)
    if not ticket or ticket.org_id != current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Ticket not found", "code": "TICKET_NOT_FOUND"},
        )

    comment = TicketCommentModel(
        ticket_id=ticket_id,
        user_id=current_user.id,
        content=req.content,
        is_admin_note=True,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    log.info("admin.comment_added", ticket_id=ticket_id, comment_id=comment.id)
    return CommentResponse(
        id=comment.id,
        ticket_id=comment.ticket_id,
        content=comment.content,
        is_admin_note=comment.is_admin_note,
        created_at=comment.created_at,
    )


@admin_router.get(
    "/tickets/{ticket_id}/comments",
    response_model=CommentListResponse,
    summary="List all comments on a ticket (admin only)",
)
def list_comments(
    ticket_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    """Return all comments on a ticket, newest first."""
    _require_admin(current_user)

    ticket = db.get(TicketModel, ticket_id)
    if not ticket or ticket.org_id != current_user.org_id:
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


# ── Per-org knowledge base ────────────────────────────────────────────────────

@admin_router.post(
    "/kb",
    response_model=KnowledgeDocResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge base document for this organisation",
)
def create_kb_doc(
    req: KnowledgeDocCreate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocResponse:
    """Add a document to the org's private KB. Used at retrieval time alongside the global KB."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    doc = OrgKnowledgeDocModel(
        org_id=current_user.org_id,
        title=req.title,
        content=req.content,
        source_type="manual",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log.info("admin.kb_doc_created", doc_id=doc.id, org_id=current_user.org_id)

    return KnowledgeDocResponse.model_validate(doc)


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


def _extract_text(filename: str, raw: bytes) -> str:
    """Extract plain text from an uploaded file based on its extension."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == ".pdf":
        try:
            import pypdf  # noqa: PLC0415
            reader = pypdf.PdfReader(io.BytesIO(raw))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p.strip() for p in pages if p.strip())
            if not text:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "PDF contains no extractable text (scanned image PDF?)", "code": "PDF_NO_TEXT"},
                )
            return text
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": f"Failed to parse PDF: {exc}", "code": "PDF_PARSE_ERROR"},
            ) from exc
    if ext == ".docx":
        try:
            import docx  # noqa: PLC0415
            document = docx.Document(io.BytesIO(raw))
            paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
            if not paragraphs:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "DOCX file contains no readable text", "code": "DOCX_NO_TEXT"},
                )
            return "\n\n".join(paragraphs)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": f"Failed to parse DOCX: {exc}", "code": "DOCX_PARSE_ERROR"},
            ) from exc
    # .txt and .md
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1").strip()


@admin_router.post(
    "/kb/upload",
    response_model=KnowledgeDocResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file (PDF, TXT, MD, DOCX) as a knowledge base document",
)
async def upload_kb_doc(
    file: UploadFile = File(..., description="PDF, TXT, MD, or DOCX file — max 10 MB"),
    title: str | None = Form(None, max_length=255),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocResponse:
    """Extract text from an uploaded file and add it to the org's KB."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": f"Unsupported file type '{ext}'. Allowed: PDF, TXT, MD, DOCX",
                "code": "UNSUPPORTED_FILE_TYPE",
            },
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "File exceeds 10 MB limit", "code": "FILE_TOO_LARGE"},
        )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Uploaded file is empty", "code": "EMPTY_FILE"},
        )

    content = _extract_text(filename, raw)
    doc_title = (title.strip() if title and title.strip() else filename.rsplit(".", 1)[0])[:255]

    doc = OrgKnowledgeDocModel(
        org_id=current_user.org_id,
        title=doc_title,
        content=content,
        source_type="upload",
        file_name=filename,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log.info("admin.kb_doc_uploaded", doc_id=doc.id, filename=filename, org_id=current_user.org_id)

    return KnowledgeDocResponse.model_validate(doc)


@admin_router.get(
    "/kb",
    response_model=KnowledgeDocListResponse,
    summary="List all knowledge base documents for this organisation",
)
def list_kb_docs(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeDocListResponse:
    """Return all org KB docs, newest first."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    rows = (
        db.query(OrgKnowledgeDocModel)
        .filter(OrgKnowledgeDocModel.org_id == current_user.org_id)
        .order_by(OrgKnowledgeDocModel.created_at.desc())
        .all()
    )
    docs = [KnowledgeDocResponse.model_validate(d) for d in rows]
    return KnowledgeDocListResponse(docs=docs, total=len(docs))


@admin_router.delete(
    "/kb/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge base document",
)
def delete_kb_doc(
    doc_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a KB document from this org's private knowledge base."""
    _require_admin(current_user)

    doc = db.get(OrgKnowledgeDocModel, doc_id)
    if not doc or doc.org_id != current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Document not found", "code": "KB_DOC_NOT_FOUND"},
        )
    db.delete(doc)
    db.commit()
    log.info("admin.kb_doc_deleted", doc_id=doc_id, org_id=current_user.org_id)


# ── Single-use invites ────────────────────────────────────────────────────────

@admin_router.post(
    "/invites",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a single-use invite code (admin only)",
)
def create_invite(
    req: InviteCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteResponse:
    """Create a unique, one-time-use invite token for joining this org."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    invite = InviteModel(
        org_id=current_user.org_id,
        code=secrets.token_urlsafe(20),
        created_by=current_user.id,
        note=req.note or None,
        expires_at=datetime.now(UTC) + timedelta(days=req.expires_days),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    log.info("admin.invite_created", invite_id=invite.id, org_id=current_user.org_id)
    return InviteResponse(
        id=invite.id, code=invite.code, note=invite.note,
        used_at=invite.used_at, used_by_email=invite.used_by_email,
        expires_at=invite.expires_at, created_at=invite.created_at,
    )


@admin_router.get(
    "/invites",
    response_model=InviteListResponse,
    summary="List all invite codes for this organisation (admin only)",
)
def list_invites(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteListResponse:
    """Return all invites for the org, newest first."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(status_code=404, detail={"code": "NO_ORG"})

    rows = (
        db.query(InviteModel)
        .filter(InviteModel.org_id == current_user.org_id)
        .order_by(InviteModel.created_at.desc())
        .all()
    )
    invites = [
        InviteResponse(
            id=i.id, code=i.code, note=i.note,
            used_at=i.used_at, used_by_email=i.used_by_email,
            expires_at=i.expires_at, created_at=i.created_at,
        )
        for i in rows
    ]
    return InviteListResponse(invites=invites, total=len(invites))


@admin_router.delete(
    "/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an unused invite code (admin only)",
)
def revoke_invite(
    invite_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Permanently delete an invite that has not been used yet."""
    _require_admin(current_user)

    invite = db.get(InviteModel, invite_id)
    if not invite or invite.org_id != current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Invite not found", "code": "INVITE_NOT_FOUND"},
        )
    if invite.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Cannot revoke a used invite", "code": "INVITE_ALREADY_USED"},
        )
    db.delete(invite)
    db.commit()
    log.info("admin.invite_revoked", invite_id=invite_id, org_id=current_user.org_id)


# ── Admin SSE stream ──────────────────────────────────────────────────────────


async def _sse_event_stream(org_id: str, start_after_id: int) -> AsyncGenerator[str, None]:
    """Poll admin_events for org_id and yield new rows as SSE data frames.

    Starts after ``start_after_id`` so a reconnecting client doesn't replay
    events it already saw. Emits a keepalive ping during idle periods. Works
    across any number of web workers because the source of truth is the DB.
    """
    from api.models import AdminEventModel, SessionLocal

    last_id = start_after_id
    idle = 0.0
    while True:
        db = SessionLocal()
        try:
            rows = (
                db.query(AdminEventModel)
                .filter(AdminEventModel.org_id == org_id, AdminEventModel.id > last_id)
                .order_by(AdminEventModel.id.asc())
                .all()
            )
            payloads = [(r.id, r.payload) for r in rows]
        except Exception:
            payloads = []
        finally:
            db.close()

        if payloads:
            idle = 0.0
            for ev_id, payload in payloads:
                last_id = ev_id
                yield f"data: {payload}\n\n"
        else:
            idle += _SSE_POLL_SECONDS
            if idle >= 25.0:  # keepalive roughly every 25s of silence
                idle = 0.0
                yield "event: ping\ndata: {}\n\n"

        await asyncio.sleep(_SSE_POLL_SECONDS)


@admin_router.get(
    "/stream",
    summary="SSE stream of resolved/escalated ticket events for this organisation (admin only)",
)
async def admin_stream(
    token: str = Query(..., description="Bearer JWT — EventSource cannot set custom headers"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # NOTE: JWT passed as query param — EventSource does not support custom headers.
    # Ensure server access logs filter sensitive query params in production.

    payload = _decode_token(token)  # raises 401 if invalid or expired

    jti: str | None = payload.get("jti")
    if jti and db.get(TokenBlocklistModel, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has been revoked", "code": "TOKEN_REVOKED"},
        )
    user_id: str | None = payload.get("sub")
    user = db.get(UserModel, user_id) if user_id else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )
    _require_admin(user)  # raises 403 if role != "admin"
    if not user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NO_ORG"})
    org_id: str = user.org_id

    # Only stream events created from now on — skip the backlog already persisted.
    from api.models import AdminEventModel
    start_after_id: int = (
        db.query(func.max(AdminEventModel.id))
        .filter(AdminEventModel.org_id == org_id)
        .scalar()
        or 0
    )

    return StreamingResponse(
        _sse_event_stream(org_id, start_after_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
