"""SQLAlchemy 2.0 ORM models and Pydantic request/response schemas."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

_DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./neuradesk.db")
_connect_args: dict[str, Any] = {"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(_DATABASE_URL, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""


# ── ORM models ────────────────────────────────────────────────────────────────

class UserModel(Base):
    """Registered user who submits tickets."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class TicketModel(Base):
    """Persisted ticket record — written after the agent graph completes."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="triaging")
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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


class LoginRequest(BaseModel):
    """POST /auth/login body."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful register or login."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user representation (no password hash)."""

    id: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Ticket schemas ────────────────────────────────────────────────────────────

class TicketCreateRequest(BaseModel):
    """POST /tickets body."""

    text: str = Field(..., min_length=1, description="Free-text ticket description")
    image_b64: Optional[str] = Field(None, description="Base-64 encoded screenshot")
    # user_id from JWT always takes precedence; this field is accepted but ignored.
    user_id: Optional[str] = Field(None, description="Resolved from JWT — ignored if provided")


class TicketResponse(BaseModel):
    """Single ticket returned by POST /tickets and GET /tickets/{id}."""

    ticket_id: str
    status: str
    category: Optional[str] = None
    confidence: Optional[float] = None
    resolution: Optional[str] = None
    escalation_reason: Optional[str] = None
    trace_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    """Paginated list returned by GET /tickets/."""

    tickets: list[TicketResponse]
    total: int
