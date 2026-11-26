"""JWT authentication utilities and /auth router."""

import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
import structlog
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.email import send_otp_email  # noqa: F401 — re-exported for callers that mock it
from api.models import (
    ForgotPasswordRequest,
    InviteModel,
    LoginRequest,
    OrganizationModel,
    OtpResendRequest,
    OtpSentResponse,
    OtpVerifyRequest,
    PasswordChangedResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionListResponse,
    SessionResponse,
    TokenBlocklistModel,
    TokenResponse,
    UserModel,
    UserSessionModel,
    get_db,
)
from core.config import get_settings

load_dotenv()

log = structlog.get_logger(__name__)

_PERSONAL_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "icloud.com", "me.com", "mac.com", "aol.com", "protonmail.com",
    "proton.me", "ymail.com", "msn.com", "mail.com", "gmx.com",
    "zoho.com", "yandex.com", "inbox.com", "fastmail.com", "hey.com",
})


def _is_personal_email(email: str) -> bool:
    """Return True if the email belongs to a known personal email provider."""
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in _PERSONAL_EMAIL_DOMAINS

_SECRET_KEY: str = os.environ.get("API_SECRET_KEY", "")
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES: int = get_settings().token_expire_minutes
_OTP_EXPIRE_MINUTES = 10
# Wrong-OTP guesses allowed for one code before it is invalidated (anti-brute-force).
_MAX_OTP_ATTEMPTS = 5

def _smtp_configured() -> bool:
    """Return True if all three SMTP env vars are set."""
    return bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USER")
        and os.environ.get("SMTP_PASS")
    )

_ENV = os.environ.get("APP_ENV", "development")
if not _SECRET_KEY:
    if _ENV == "production":
        raise RuntimeError("API_SECRET_KEY must be set in production — refusing to start with no secret")
    _SECRET_KEY = "dev-insecure-key-change-me"

_http_bearer = HTTPBearer(auto_error=True)


# ── Password utilities ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if plaintext password matches its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT utilities ─────────────────────────────────────────────────────────────

def create_access_token(
    user_id: str, email: str, org_id: str, org_name: str, role: str,
    first_name: str = "", last_name: str = "",
) -> str:
    """Create a signed HS256 JWT valid for 8 hours."""
    expire = datetime.now(UTC) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "jti": str(uuid.uuid4()),  # unique token ID — stored in blocklist on logout
        "email": email,
        "org_id": org_id,
        "org_name": org_name,
        "role": role,
        "first_name": first_name,
        "last_name": last_name,
        "exp": expire,
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT; raise 401 HTTPException on any failure."""
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has expired", "code": "TOKEN_EXPIRED"},
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid token", "code": "TOKEN_INVALID"},
        ) from exc


# ── Session tracking ─────────────────────────────────────────────────────────


def _client_ip(request: Request | None) -> str | None:
    """Best-effort client IP for display (first X-Forwarded-For hop behind a proxy)."""
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64] or None
    return request.client.host[:64] if request.client else None


def _record_session(token_str: str, db: Session, request: Request | None = None) -> None:
    """Decode a freshly issued token and insert a UserSessionModel row.

    Stores the browser's User-Agent and client IP so users can recognise their
    devices. Silently skips on any error so a DB hiccup never blocks login.
    """
    try:
        payload = jwt.decode(token_str, _SECRET_KEY, algorithms=[_ALGORITHM])
        jti = payload.get("jti")
        user_id = payload.get("sub")
        exp = payload.get("exp")
        if not (jti and user_id and exp):
            return
        expires_at = datetime.fromtimestamp(exp, tz=UTC)
        ua = (request.headers.get("user-agent") or "")[:300] if request is not None else ""
        db.add(UserSessionModel(
            jti=jti, user_id=user_id, expires_at=expires_at,
            user_agent=ua or None, ip_address=_client_ip(request),
        ))
        # flush so errors surface before the outer commit
        db.flush()
    except Exception:
        log.warning("auth.record_session.failed")


def _deactivated() -> HTTPException:
    """Error for accounts an admin has deactivated."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "Your account has been deactivated. Contact your administrator.",
                "code": "ACCOUNT_DEACTIVATED"},
    )


# Shown when sign-in fails on our side (e.g. database down), so people don't
# assume their password is wrong and start resetting it.
_SERVER_FAULT_MSG: str = (
    "Sign-in is temporarily unavailable — a problem on our side, not your password. "
    "Please try again in a minute."
)


def _active_payload(credentials: HTTPAuthorizationCredentials, db: Session) -> dict[str, Any]:
    """Decode a bearer token and reject it if it has been revoked.

    Every endpoint that acts on a raw token must use this — decoding alone lets a
    signed-out (blocklisted) token keep working until it expires.
    """
    payload = _decode_token(credentials.credentials)
    # Account status first: deactivation also revokes sessions, and the employee
    # should be told *why* they lost access, not just that their session ended.
    user = db.get(UserModel, payload.get("sub")) if payload.get("sub") else None
    if user is not None and not user.is_active:
        raise _deactivated()
    jti = payload.get("jti")
    if jti and db.get(TokenBlocklistModel, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has been revoked", "code": "TOKEN_REVOKED"},
        )
    return payload


def _revoke_jti(db: Session, jti: str, expires_at: datetime) -> None:
    """Blocklist one token id (idempotent)."""
    if not db.get(TokenBlocklistModel, jti):
        db.add(TokenBlocklistModel(jti=jti, expires_at=expires_at))


def _revoke_other_sessions(db: Session, user_id: str, keep_jti: str | None) -> int:
    """Revoke every active session of ``user_id`` except ``keep_jti``. Returns how many."""
    now = datetime.now(UTC)
    rows = (
        db.query(UserSessionModel)
        .filter(UserSessionModel.user_id == user_id, UserSessionModel.expires_at > now)
        .all()
    )
    revoked = 0
    for r in rows:
        if r.jti != keep_jti and not db.get(TokenBlocklistModel, r.jti):
            db.add(TokenBlocklistModel(jti=r.jti, expires_at=r.expires_at))
            revoked += 1
    return revoked


# ── Org utilities ─────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Convert an org name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:50].strip("-") or "org"


def _unique_slug(name: str, db: Session) -> str:
    """Return a slug derived from name that is unique in the organizations table."""
    base = _slugify(name)
    slug = base
    counter = 1
    while db.query(OrganizationModel).filter(OrganizationModel.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


# ── OTP utilities ─────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    """Return a cryptographically random numeric OTP string."""
    return "".join([str(secrets.randbelow(10)) for _ in range(length)])


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> UserModel:
    """Resolve Bearer JWT to a UserModel; raise 401 if missing, invalid, expired, or revoked."""
    payload = _decode_token(credentials.credentials)
    jti: str | None = payload.get("jti")
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token payload missing subject", "code": "TOKEN_NO_SUB"},
        )
    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )
    if not user.is_active:
        raise _deactivated()  # before the blocklist: deactivation revokes sessions too
    if jti and db.get(TokenBlocklistModel, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has been revoked", "code": "TOKEN_REVOKED"},
        )
    return user


# ── Auth router ───────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/auth", tags=["auth"])
_RATELIMIT_ENABLED = os.environ.get("APP_ENV", "development") == "production"
_limiter = Limiter(key_func=get_remote_address, enabled=_RATELIMIT_ENABLED)

# If set, new-org creation (becoming admin) requires this token in the request.
# Joining an existing org via invite_code is always open.
_ORG_CREATION_SECRET: str = os.environ.get("ORG_CREATION_SECRET", "")


@auth_router.get(
    "/config",
    summary="Return public auth configuration flags (no auth required)",
)
def auth_config() -> dict[str, Any]:
    """Expose whether org creation is restricted so the frontend can show/hide the token field."""
    return {
        "org_creation_restricted": bool(_ORG_CREATION_SECRET),
        "work_email_required": _ENV == "production",
    }


@auth_router.get("/me", summary="Return the current user's profile")
def me(user: UserModel = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return first_name, last_name, email, role, and org_name for the authenticated user."""
    org = db.get(OrganizationModel, user.org_id)
    return {
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": user.email,
        "role": user.role,
        "org_name": org.name if org else "",
    }


@auth_router.post(
    "/register",
    response_model=OtpSentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register — creates a new org (admin) or joins an existing one via invite code",
)
@_limiter.limit("10/minute")
def register(request: Request, req: RegisterRequest, db: Session = Depends(get_db)) -> OtpSentResponse:
    """Create an unverified account and dispatch an OTP. Account is active only after /verify-otp."""
    if not req.org_name and not req.invite_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Provide org_name (create new org) or invite_code (join existing)",
                "code": "ORG_REQUIRED",
            },
        )

    # Org creation requires a token only when ORG_CREATION_SECRET is configured.
    # If the secret is not set, org creation is open to anyone.
    if (
        req.org_name
        and _ORG_CREATION_SECRET
        and not secrets.compare_digest(req.org_creation_token or "", _ORG_CREATION_SECRET)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Organisation creation requires a valid admin token",
                "code": "ORG_TOKEN_REQUIRED",
            },
        )

    if _ENV == "production" and _is_personal_email(req.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Please use your work email address, not a personal one (e.g. @company.com)",
                "code": "PERSONAL_EMAIL_NOT_ALLOWED",
            },
        )

    try:
        # Check email uniqueness first — before any org creation work.
        if db.query(UserModel).filter(func.lower(UserModel.email) == req.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Email already registered", "code": "EMAIL_TAKEN"},
            )

        # Resolve org ─────────────────────────────────────────────────────────
        if req.invite_code:
            invite = (
                db.query(InviteModel)
                .filter(InviteModel.code == req.invite_code)
                .first()
            )
            if not invite:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "Invalid invite code", "code": "INVALID_INVITE"},
                )
            if invite.used_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "This invite has already been used", "code": "INVITE_USED"},
                )
            if invite.expires_at and (
                invite.expires_at.replace(tzinfo=UTC)
                if invite.expires_at.tzinfo is None
                else invite.expires_at
            ) < datetime.now(UTC):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "This invite has expired", "code": "INVITE_EXPIRED"},
                )
            org = db.get(OrganizationModel, invite.org_id)
            if not org:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "Organisation not found", "code": "ORG_NOT_FOUND"},
                )
            # Mark invite as consumed — prevents any reuse, including concurrent attempts
            invite.used_at = datetime.now(UTC)
            invite.used_by_email = req.email
            role = "member"
        else:
            slug = _unique_slug(req.org_name, db)  # type: ignore[arg-type]
            org = OrganizationModel(
                name=req.org_name,
                slug=slug,
                invite_code=secrets.token_urlsafe(12),
            )
            db.add(org)
            db.flush()  # populate org.id before creating user
            role = "admin"

        otp = generate_otp()
        user = UserModel(
            hashed_password=hash_password(req.password),
            email=req.email,
            first_name=req.first_name,
            last_name=req.last_name,
            org_id=org.id,
            role=role,
            is_verified=False,
            otp=otp,
            otp_expires_at=datetime.now(UTC) + timedelta(minutes=_OTP_EXPIRE_MINUTES),
        )
        db.add(user)

        # Send email BEFORE committing so a delivery failure rolls back cleanly.
        # The user record never lands in the DB if email can't be sent.
        try:
            send_otp_email(req.email, otp)
        except Exception as exc:
            db.rollback()
            log.exception("auth.register.email_failed", email=req.email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "Failed to send verification email", "code": "EMAIL_FAILED"},
            ) from exc

        db.commit()
        db.refresh(user)
        log.info("auth.register.otp_created", user_id=user.id, email=user.email, org_id=org.id, role=role)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        log.exception("auth.register.error", email=req.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Registration failed. Please try again.", "code": "REGISTER_FAILED"},
        ) from exc

    dev_otp_hint: str | None = None
    if _ENV != "production" and not _smtp_configured():
        dev_otp_hint = otp
        log.warning("auth.register.dev_otp", email=req.email, otp=otp,
                    hint="SMTP not configured — OTP shown in response (dev only)")
    return OtpSentResponse(message="OTP sent", email=req.email, dev_otp=dev_otp_hint)


@auth_router.post(
    "/verify-otp",
    response_model=TokenResponse,
    summary="Verify the OTP and activate the account",
)
@_limiter.limit("10/minute")
def verify_otp(request: Request, req: OtpVerifyRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Validate the 6-digit OTP, mark the account verified, and return an access token."""
    user = db.query(UserModel).filter(func.lower(UserModel.email) == req.email).first()
    # Return generic error — do not reveal whether the email exists.
    _invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": "Incorrect or expired verification code", "code": "INVALID_OTP"},
    )
    if not user:
        raise _invalid

    # Already verified — OTP column is cleared. Redirect caller to /login.
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Account already verified — please sign in", "code": "ALREADY_VERIFIED"},
        )

    if not user.otp or not user.otp_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No pending OTP — request a new one", "code": "NO_OTP_PENDING"},
        )

    expires = user.otp_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)

    if datetime.now(UTC) > expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "OTP has expired — request a new one", "code": "OTP_EXPIRED"},
        )

    # Lock the code out after too many wrong guesses (brute-force protection).
    if (user.otp_attempts or 0) >= _MAX_OTP_ATTEMPTS:
        user.otp = None
        user.otp_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "Too many incorrect attempts — request a new code", "code": "OTP_LOCKED"},
        )

    if not secrets.compare_digest(user.otp, req.otp):
        user.otp_attempts = (user.otp_attempts or 0) + 1
        db.commit()
        raise _invalid

    user.is_verified = True
    user.otp = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()

    org = db.get(OrganizationModel, user.org_id) if user.org_id else None
    log.info("auth.verify_otp.success", user_id=user.id, org_id=user.org_id)
    token_str = create_access_token(
        user.id, user.email, user.org_id or "", org.name if org else "", user.role,
        user.first_name or "", user.last_name or "",
    )
    _record_session(token_str, db, request)
    db.commit()
    return TokenResponse(access_token=token_str)


@auth_router.post(
    "/resend-otp",
    response_model=OtpSentResponse,
    summary="Resend a fresh OTP to the registered email",
)
@_limiter.limit("3/minute")
def resend_otp(request: Request, req: OtpResendRequest, db: Session = Depends(get_db)) -> OtpSentResponse:
    """Generate a new OTP (invalidating the previous one) and send it by email.

    Always answers the same way for unknown, already-verified and pending accounts
    so the endpoint can't be used to discover which emails are registered.
    """
    user = db.query(UserModel).filter(func.lower(UserModel.email) == req.email).first()
    if not user or user.is_verified:
        log.info("auth.resend_otp.noop", reason="unknown" if not user else "already_verified")
        return OtpSentResponse(message="OTP sent", email=req.email, dev_otp=None)

    otp = generate_otp()
    user.otp = otp
    user.otp_expires_at = datetime.now(UTC) + timedelta(minutes=_OTP_EXPIRE_MINUTES)
    user.otp_attempts = 0
    db.commit()

    try:
        send_otp_email(req.email, otp)
    except Exception as exc:
        log.exception("auth.resend_otp.email_failed", email=req.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Failed to send email", "code": "EMAIL_FAILED"},
        ) from exc

    log.info("auth.resend_otp", email=req.email)
    dev_otp_hint: str | None = otp if _ENV != "production" and not _smtp_configured() else None
    if dev_otp_hint:
        log.warning("auth.resend_otp.dev_otp", email=req.email, otp=otp)
    return OtpSentResponse(message="OTP sent", email=req.email, dev_otp=dev_otp_hint)


@auth_router.post(
    "/forgot-password",
    response_model=OtpSentResponse,
    summary="Send a 6-digit reset code to the registered email",
)
@_limiter.limit("5/minute")
def forgot_password(request: Request, req: ForgotPasswordRequest, db: Session = Depends(get_db)) -> OtpSentResponse:
    """Generate a password-reset OTP and email it. Always returns 200 to avoid user enumeration."""
    dev_otp_hint: str | None = None
    user = db.query(UserModel).filter(func.lower(UserModel.email) == req.email).first()
    if user:
        otp = generate_otp()
        user.otp = otp
        user.otp_expires_at = datetime.now(UTC) + timedelta(minutes=_OTP_EXPIRE_MINUTES)
        user.otp_attempts = 0
        db.commit()
        try:
            send_otp_email(req.email, otp)
        except Exception:
            log.exception("auth.forgot_password.email_failed", email=req.email)
        if _ENV != "production" and not _smtp_configured():
            dev_otp_hint = otp
            log.warning("auth.forgot_password.dev_otp", email=req.email, otp=otp)
    # Always succeed — don't reveal whether the email exists
    return OtpSentResponse(message="OTP sent", email=req.email, dev_otp=dev_otp_hint)


@auth_router.post(
    "/reset-password",
    response_model=TokenResponse,
    summary="Verify the reset OTP and set a new password",
)
def reset_password(request: Request, req: ResetPasswordRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Validate the reset OTP, update the password, mark account verified, and return a token."""
    user = db.query(UserModel).filter(func.lower(UserModel.email) == req.email).first()
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": "Invalid or expired reset code", "code": "INVALID_RESET"},
    )
    if not user or not user.otp or not user.otp_expires_at:
        raise invalid

    expires = user.otp_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if datetime.now(UTC) > expires:
        raise invalid

    if (user.otp_attempts or 0) >= _MAX_OTP_ATTEMPTS:
        user.otp = None
        user.otp_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "Too many incorrect attempts — request a new code", "code": "OTP_LOCKED"},
        )

    if not secrets.compare_digest(user.otp, req.otp):
        user.otp_attempts = (user.otp_attempts or 0) + 1
        db.commit()
        raise invalid

    if not user.is_active:
        raise _deactivated()
    user.hashed_password = hash_password(req.new_password)
    user.is_verified = True
    user.otp = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    # Account recovery: whoever else was signed in (e.g. with a stolen session) loses access.
    _revoke_other_sessions(db, user.id, keep_jti=None)
    db.commit()

    org = db.get(OrganizationModel, user.org_id) if user.org_id else None
    log.info("auth.reset_password.success", user_id=user.id)
    token_str = create_access_token(
        user.id, user.email, user.org_id or "", org.name if org else "", user.role,
        user.first_name or "", user.last_name or "",
    )
    _record_session(token_str, db, request)
    db.commit()
    return TokenResponse(access_token=token_str)


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a valid token for a fresh one (extends session by 8 hours)",
)
def refresh_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid, non-revoked token for a fresh 8-hour one.

    The old token is retired, so a background refresh *replaces* the device's
    session instead of piling up parallel valid tokens.
    """
    payload = _active_payload(credentials, db)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token payload missing subject", "code": "TOKEN_NO_SUB"},
        )
    user = db.get(UserModel, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )
    org = db.get(OrganizationModel, user.org_id) if user.org_id else None
    log.info("auth.refresh", user_id=user.id)
    token_str = create_access_token(
        user.id, user.email, user.org_id or "", org.name if org else "", user.role,
        user.first_name or "", user.last_name or "",
    )
    old_jti, old_exp = payload.get("jti"), payload.get("exp")
    if old_jti and old_exp:
        _revoke_jti(db, old_jti, datetime.fromtimestamp(old_exp, tz=UTC))
    _record_session(token_str, db, request)
    db.commit()
    return TokenResponse(access_token=token_str)


class ChangePasswordRequest(BaseModel):
    """POST /auth/change-password body."""

    current_password: str
    new_password: str = Field(..., min_length=8)


@auth_router.post(
    "/change-password",
    response_model=PasswordChangedResponse,
    summary="Change password and sign out every other session",
)
def change_password(
    request: Request,
    req: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> PasswordChangedResponse:
    """Verify the current password, set the new one, and sign out all sessions.

    Standard practice: if the old password was compromised, any device signed in
    with it must lose access. The caller gets a fresh token for this device.
    """
    payload = _active_payload(credentials, db)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid token", "code": "TOKEN_INVALID"},
        )
    user = db.get(UserModel, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Current password is incorrect", "code": "WRONG_PASSWORD"},
        )
    if req.new_password == req.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "New password must be different from the current one", "code": "PASSWORD_UNCHANGED"},
        )
    user.hashed_password = hash_password(req.new_password)
    old_jti: str | None = payload.get("jti")
    others = _revoke_other_sessions(db, user.id, keep_jti=old_jti)
    if old_jti:
        exp = payload.get("exp")
        _revoke_jti(db, old_jti, datetime.fromtimestamp(exp, tz=UTC) if exp
                    else datetime.now(UTC) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES))
    db.commit()
    org = db.get(OrganizationModel, user.org_id) if user.org_id else None
    log.info("auth.change_password", user_id=user.id, other_sessions_signed_out=others)
    token_str = create_access_token(
        user.id, user.email, user.org_id or "", org.name if org else "", user.role,
        user.first_name or "", user.last_name or "",
    )
    _record_session(token_str, db, request)
    db.commit()
    return PasswordChangedResponse(access_token=token_str, other_sessions_signed_out=others)


@auth_router.post("/logout", summary="Invalidate the current Bearer token")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add the token's jti to the blocklist. Idempotent — safe to call multiple times."""
    payload = _decode_token(credentials.credentials)
    jti: str | None = payload.get("jti")
    if jti and not db.get(TokenBlocklistModel, jti):
        exp = payload.get("exp")
        expires_at = (
            datetime.fromtimestamp(exp, tz=UTC)
            if exp
            else datetime.now(UTC) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)
        )
        db.add(TokenBlocklistModel(jti=jti, expires_at=expires_at))
        db.commit()
    log.info("auth.logout", jti=jti)
    return {"message": "Logged out successfully"}


@auth_router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List active sessions for the current user",
)
def list_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> SessionListResponse:
    """Return all non-expired, non-revoked sessions for the authenticated user.

    The is_current flag is True for the session matching the caller's own JTI.
    """
    payload = _active_payload(credentials, db)
    caller_jti: str | None = payload.get("jti")
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid token", "code": "TOKEN_INVALID"},
        )

    now = datetime.now(UTC)
    rows = (
        db.query(UserSessionModel)
        .filter(
            UserSessionModel.user_id == user_id,
            UserSessionModel.expires_at > now,
        )
        .order_by(UserSessionModel.created_at.desc())
        .all()
    )

    revoked_jtis: set[str] = {
        r.jti
        for r in db.query(TokenBlocklistModel.jti)
        .filter(TokenBlocklistModel.jti.in_([r.jti for r in rows]))
        .all()
    }

    sessions = [
        SessionResponse(
            jti=r.jti,
            created_at=r.created_at,
            expires_at=r.expires_at,
            is_current=(r.jti == caller_jti),
            user_agent=r.user_agent,
            ip_address=r.ip_address,
        )
        for r in rows
        if r.jti not in revoked_jtis
    ]
    log.info("auth.list_sessions", user_id=user_id, count=len(sessions))
    return SessionListResponse(sessions=sessions, total=len(sessions))


@auth_router.delete(
    "/sessions/{jti}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a specific session by JTI (remote sign-out)",
)
def revoke_session(
    jti: str,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> None:
    """Add the given JTI to the token blocklist, immediately invalidating that session.

    Returns 404 if the session does not belong to the authenticated user.
    Returns 409 if the caller tries to revoke their own current session (use /auth/logout instead).
    """
    payload = _active_payload(credentials, db)
    caller_jti: str | None = payload.get("jti")
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid token", "code": "TOKEN_INVALID"},
        )
    if jti == caller_jti:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Use /auth/logout to end your current session", "code": "USE_LOGOUT"},
        )

    session = db.get(UserSessionModel, jti)
    if not session or session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found", "code": "SESSION_NOT_FOUND"},
        )

    if not db.get(TokenBlocklistModel, jti):
        db.add(TokenBlocklistModel(jti=jti, expires_at=session.expires_at))
        db.commit()

    log.info("auth.revoke_session", jti=jti, user_id=user_id)


@auth_router.delete("/sessions", summary="Sign out every other session (keep this one)")
def revoke_other_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Revoke all of the caller's sessions except the one making this request."""
    payload = _active_payload(credentials, db)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid token", "code": "TOKEN_INVALID"},
        )
    count = _revoke_other_sessions(db, user_id, keep_jti=payload.get("jti"))
    db.commit()
    log.info("auth.revoke_other_sessions", user_id=user_id, count=count)
    return {"signed_out": count}


@auth_router.patch("/me", summary="Update the current user's name")
def update_me(
    req: ProfileUpdateRequest,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update first and last name; returns the same shape as GET /auth/me."""
    first, last = req.first_name.strip(), req.last_name.strip()
    if not first or not last:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "First and last name are required", "code": "NAME_REQUIRED"},
        )
    user.first_name, user.last_name = first, last
    db.commit()
    org = db.get(OrganizationModel, user.org_id) if user.org_id else None
    log.info("auth.update_me", user_id=user.id)
    return {"first_name": first, "last_name": last, "email": user.email, "role": user.role,
            "org_name": org.name if org else ""}


@auth_router.post("/login", response_model=TokenResponse, summary="Login with email + password")
@_limiter.limit("20/minute")
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify credentials and return an 8-hour access token. Rejects unverified accounts."""
    try:
        user = db.query(UserModel).filter(func.lower(UserModel.email) == req.email).first()
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Invalid email or password", "code": "BAD_CREDENTIALS"},
            )
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Email not verified — check your inbox", "code": "EMAIL_NOT_VERIFIED"},
            )
        if not user.is_active:
            raise _deactivated()
        org = db.get(OrganizationModel, user.org_id) if user.org_id else None
        log.info("auth.login", user_id=user.id, org_id=user.org_id)
        token_str = create_access_token(
            user.id, user.email, user.org_id or "", org.name if org else "", user.role
        )
        _record_session(token_str, db, request)
        db.commit()
        return TokenResponse(access_token=token_str)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("auth.login.error", email=req.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": _SERVER_FAULT_MSG, "code": "LOGIN_FAILED"},
        ) from exc
