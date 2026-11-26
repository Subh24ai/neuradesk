"""SQLAlchemy 2.0 ORM models and Pydantic request/response schemas."""

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy import true as sa_true
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

_DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./neuradesk.db")
_is_sqlite = _DATABASE_URL.startswith("sqlite")
_connect_args: dict[str, Any] = {"check_same_thread": False} if _is_sqlite else {}

# Connection pool tuning: SQLite doesn't pool; PostgreSQL benefits from explicit limits.
_pool_kwargs: dict[str, Any] = (
    {}
    if _is_sqlite
    else {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": 3600,   # avoid stale connections after 1h
        "pool_pre_ping": True,  # test connections before handing them out
    }
)
engine = create_engine(_DATABASE_URL, connect_args=_connect_args, echo=False, **_pool_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""


# ── ORM models ────────────────────────────────────────────────────────────────

class OrganizationModel(Base):
    """A tenant organisation — every user and ticket belongs to one."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class OrgConfigModel(Base):
    """Per-org configuration — enterprise API endpoints, SMTP overrides, etc."""

    __tablename__ = "org_configs"

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), primary_key=True
    )
    itsm_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    iam_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_pass: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_categories: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class UserModel(Base):
    """Registered user who submits tickets."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # False once an admin deactivates the account (offboarding). Kept instead of
    # deleting so the user's ticket history and audit trail stay intact.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=sa_true())
    otp: Mapped[str | None] = mapped_column(String(6), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Failed OTP verification attempts for the current code — locks after a cap
    # to stop brute-forcing the 6-digit code. Reset whenever a new OTP is issued.
    otp_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class TicketModel(Base):
    """Persisted ticket record — created as 'pending' on POST, updated after the WS graph run."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_image_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    trace_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class OrgKnowledgeDocModel(Base):
    """Per-org knowledge base document uploaded by the admin."""

    __tablename__ = "org_knowledge_docs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True, default="manual")
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class InviteModel(Base):
    """Single-use invite token for joining an organisation."""

    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class TokenBlocklistModel(Base):
    """Revoked JWT IDs — checked on every authenticated request to enforce logout."""

    __tablename__ = "token_blocklist"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserSessionModel(Base):
    """Active user session — one row per issued JWT, used for session listing and remote revocation."""

    __tablename__ = "user_sessions"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Where the session was signed in from — shown so users can recognise and
    # revoke devices. Display-only; never used for authorization.
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TicketCommentModel(Base):
    """Comment or admin note attached to a ticket."""

    __tablename__ = "ticket_comments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tickets.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin_note: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AdminEventModel(Base):
    """Durable admin-dashboard event enabling cross-worker SSE fan-out.

    In-process queues only reach admins connected to the same web worker.
    Persisting each ticket event and having every /admin/stream connection poll
    this table makes the live feed correct under any number of workers.
    """

    __tablename__ = "admin_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
        default=lambda: datetime.now(UTC),
    )


# ── DB session dependency ─────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a SQLAlchemy session, closing it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Auth schemas ──────────────────────────────────────────────────────────────

class UTCResponse(BaseModel):
    """Base for response schemas: every datetime is sent as explicit UTC.

    SQLite returns timezone-naive datetimes even for ``DateTime(timezone=True)``
    columns, which serialised as e.g. ``2026-11-24T12:00:00`` with no offset.
    Browsers read that as *local* time, so tickets appeared hours old outside UTC.
    """

    @field_validator("*", mode="after")
    @classmethod
    def _assume_utc(cls, value: Any) -> Any:
        """Mark naive datetimes as UTC (the app only ever stores UTC)."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class EmailRequest(BaseModel):
    """Base for auth requests: emails are case-insensitive, so store/compare lowercase."""

    @field_validator("email", mode="after", check_fields=False)
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        """Lower-case and trim so 'Ada@Corp.com' and 'ada@corp.com' are one account."""
        return value.strip().lower()


class RegisterRequest(EmailRequest):
    """POST /auth/register body."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    first_name: str = Field(..., min_length=1, max_length=100, description="Given name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Family name")
    org_name: str | None = Field(None, min_length=2, max_length=100, description="Create a new org (caller becomes admin)")
    invite_code: str | None = Field(None, description="Join an existing org by invite code")
    org_creation_token: str | None = Field(None, description="Platform token required when ORG_CREATION_SECRET is set")


class LoginRequest(EmailRequest):
    """POST /auth/login body."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful login or OTP verification."""

    access_token: str
    token_type: str = "bearer"


class PasswordChangedResponse(TokenResponse):
    """Returned by POST /auth/change-password."""

    other_sessions_signed_out: int = 0


class ProfileUpdateRequest(BaseModel):
    """PATCH /auth/me body."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class UserResponse(UTCResponse):
    """Public user representation (no password hash)."""

    id: str
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OtpVerifyRequest(EmailRequest):
    """POST /auth/verify-otp body."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OtpResendRequest(EmailRequest):
    """POST /auth/resend-otp body."""

    email: EmailStr


class ForgotPasswordRequest(EmailRequest):
    """POST /auth/forgot-password body."""

    email: EmailStr


class ResetPasswordRequest(EmailRequest):
    """POST /auth/reset-password body."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8)


class OtpSentResponse(BaseModel):
    """Returned when an OTP email is dispatched successfully."""

    message: str
    email: str
    dev_otp: str | None = None  # populated only in development when SMTP is not configured


# ── Org schemas ───────────────────────────────────────────────────────────────

class OrgResponse(UTCResponse):
    """Public org representation returned by /orgs/me."""

    id: str
    name: str
    slug: str
    invite_code: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberResponse(UTCResponse):
    """Single member entry returned by GET /orgs/members."""

    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberUpdateRequest(BaseModel):
    """PATCH /orgs/members/{user_id} body — change role and/or access."""

    role: str | None = Field(None, pattern="^(admin|member)$")
    is_active: bool | None = None


class MembersListResponse(BaseModel):
    """List of org members."""

    members: list[MemberResponse]
    total: int


# ── Ticket schemas ────────────────────────────────────────────────────────────

_MAX_TEXT_CHARS = 4_000
_MAX_IMAGE_B64_CHARS = 1_400_000  # ~1 MB decoded (~1.4 MB base64)


class TicketCreateRequest(BaseModel):
    """POST /tickets body."""

    text: str = Field(..., min_length=1, max_length=_MAX_TEXT_CHARS, description="Free-text ticket description")
    image_b64: str | None = Field(
        None, max_length=_MAX_IMAGE_B64_CHARS, description="Base-64 encoded screenshot (max ~1 MB decoded)"
    )
    user_id: str | None = Field(None, description="Resolved from JWT — ignored if provided")


class TicketResponse(UTCResponse):
    """Single ticket returned by POST /tickets and GET /tickets/{id}."""

    ticket_id: str
    status: str
    raw_text: str | None = None
    category: str | None = None
    confidence: float | None = None
    resolution: str | None = None
    escalation_reason: str | None = None
    admin_note: str | None = None
    assignee_group: str | None = None
    priority: str | None = None
    user_email: str | None = None
    image_url: str | None = None
    trace_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    """Paginated list returned by GET /tickets/ and GET /admin/tickets."""

    tickets: list[TicketResponse]
    total: int
    limit: int = 20
    offset: int = 0


class TicketResolveRequest(BaseModel):
    """PATCH /admin/tickets/{ticket_id} body."""

    status: str = Field("resolved", pattern="^(resolved|escalated|pending)$")
    admin_note: str | None = Field(None, max_length=2000)


# ── Knowledge base schemas ────────────────────────────────────────────────────

class KnowledgeDocCreate(BaseModel):
    """POST /admin/kb body."""

    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=10)


class KnowledgeDocResponse(UTCResponse):
    """Single org KB document."""

    id: str
    title: str
    content: str
    source_type: str | None = "manual"
    file_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocListResponse(BaseModel):
    """List of org KB documents."""

    docs: list[KnowledgeDocResponse]
    total: int


# ── Comment schemas ───────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    """POST /admin/tickets/{id}/comments body."""

    content: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(UTCResponse):
    """Single ticket comment."""

    id: str
    ticket_id: str
    content: str
    is_admin_note: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentListResponse(BaseModel):
    """List of ticket comments."""

    comments: list[CommentResponse]
    total: int


# ── Invite schemas ────────────────────────────────────────────────────────────

class SessionResponse(UTCResponse):
    """Single active session returned by GET /auth/sessions."""

    jti: str
    created_at: datetime
    expires_at: datetime
    is_current: bool
    user_agent: str | None = None
    ip_address: str | None = None

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """List of active sessions returned by GET /auth/sessions."""

    sessions: list[SessionResponse]
    total: int


class InviteCreateRequest(BaseModel):
    """POST /admin/invites body."""

    note: str | None = Field(None, max_length=200, description="Optional label for this invite (e.g. 'For Alice from Marketing')")
    expires_days: int = Field(7, ge=1, le=365, description="Days until the invite expires")


class InviteResponse(UTCResponse):
    """Single invite returned by the admin invite endpoints."""

    id: str
    code: str
    note: str | None = None
    used_at: datetime | None = None
    used_by_email: str | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteListResponse(BaseModel):
    """List of invites for an organisation."""

    invites: list[InviteResponse]
    total: int
