"""SQLAlchemy 2.0 ORM models and Pydantic request/response schemas."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
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
        default=lambda: datetime.now(timezone.utc),
    )


class OrgConfigModel(Base):
    """Per-org configuration — enterprise API endpoints, SMTP overrides, etc."""

    __tablename__ = "org_configs"

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), primary_key=True
    )
    itsm_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hr_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    iam_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_user: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_pass: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    custom_categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class UserModel(Base):
    """Registered user who submits tickets."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    org_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    otp: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    otp_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TicketModel(Base):
    """Persisted ticket record — created as 'pending' on POST, updated after the WS graph run."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_image_b64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assignee_group: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    trace_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
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
    source_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="manual")
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
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
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


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
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
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

class RegisterRequest(BaseModel):
    """POST /auth/register body."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    first_name: str = Field(..., min_length=1, max_length=100, description="Given name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Family name")
    org_name: Optional[str] = Field(None, min_length=2, max_length=100, description="Create a new org (caller becomes admin)")
    invite_code: Optional[str] = Field(None, description="Join an existing org by invite code")
    org_creation_token: Optional[str] = Field(None, description="Platform token required when ORG_CREATION_SECRET is set")


class LoginRequest(BaseModel):
    """POST /auth/login body."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful login or OTP verification."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user representation (no password hash)."""

    id: str
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OtpVerifyRequest(BaseModel):
    """POST /auth/verify-otp body."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OtpResendRequest(BaseModel):
    """POST /auth/resend-otp body."""

    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    """POST /auth/forgot-password body."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """POST /auth/reset-password body."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8)


class OtpSentResponse(BaseModel):
    """Returned when an OTP email is dispatched successfully."""

    message: str
    email: str
    dev_otp: Optional[str] = None  # populated only in development when SMTP is not configured


# ── Org schemas ───────────────────────────────────────────────────────────────

class OrgResponse(BaseModel):
    """Public org representation returned by /orgs/me."""

    id: str
    name: str
    slug: str
    invite_code: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    """Single member entry returned by GET /orgs/members."""

    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


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
    image_b64: Optional[str] = Field(
        None, max_length=_MAX_IMAGE_B64_CHARS, description="Base-64 encoded screenshot (max ~1 MB decoded)"
    )
    user_id: Optional[str] = Field(None, description="Resolved from JWT — ignored if provided")


class TicketResponse(BaseModel):
    """Single ticket returned by POST /tickets and GET /tickets/{id}."""

    ticket_id: str
    status: str
    raw_text: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    resolution: Optional[str] = None
    escalation_reason: Optional[str] = None
    admin_note: Optional[str] = None
    assignee_group: Optional[str] = None
    priority: Optional[str] = None
    user_email: Optional[str] = None
    trace_url: Optional[str] = None
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
    admin_note: Optional[str] = Field(None, max_length=2000)


# ── Knowledge base schemas ────────────────────────────────────────────────────

class KnowledgeDocCreate(BaseModel):
    """POST /admin/kb body."""

    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=10)


class KnowledgeDocResponse(BaseModel):
    """Single org KB document."""

    id: str
    title: str
    content: str
    source_type: Optional[str] = "manual"
    file_name: Optional[str] = None
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


class CommentResponse(BaseModel):
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

class InviteCreateRequest(BaseModel):
    """POST /admin/invites body."""

    note: Optional[str] = Field(None, max_length=200, description="Optional label for this invite (e.g. 'For Alice from Marketing')")
    expires_days: int = Field(7, ge=1, le=365, description="Days until the invite expires")


class InviteResponse(BaseModel):
    """Single invite returned by the admin invite endpoints."""

    id: str
    code: str
    note: Optional[str] = None
    used_at: Optional[datetime] = None
    used_by_email: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteListResponse(BaseModel):
    """List of invites for an organisation."""

    invites: list[InviteResponse]
    total: int
