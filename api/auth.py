"""JWT authentication utilities and /auth router."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import structlog
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from api.models import LoginRequest, RegisterRequest, TokenResponse, UserModel, get_db

load_dotenv()

log = structlog.get_logger(__name__)

_SECRET_KEY: str = os.environ.get("API_SECRET_KEY", "dev-insecure-key-change-me")
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8-hour sessions for enterprise demo

_http_bearer = HTTPBearer(auto_error=True)


# ── Password utilities ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if plaintext password matches its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT utilities ─────────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    """Create a signed HS256 JWT valid for 8 hours."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT; raise 401 HTTPException on any failure."""
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has expired", "code": "TOKEN_EXPIRED"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid token", "code": "TOKEN_INVALID"},
        )


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> UserModel:
    """Resolve Bearer JWT to a UserModel; raise 401 if missing, invalid, or expired."""
    payload = _decode_token(credentials.credentials)
    user_id: Optional[str] = payload.get("sub")
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
    return user


# ── Auth router ───────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a user account and return an 8-hour access token."""
    try:
        if db.query(UserModel).filter(UserModel.email == req.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Email already registered", "code": "EMAIL_TAKEN"},
            )
        user = UserModel(hashed_password=hash_password(req.password), email=req.email)
        db.add(user)
        db.commit()
        db.refresh(user)
        log.info("auth.register", user_id=user.id, email=user.email)
        return TokenResponse(access_token=create_access_token(user.id, user.email))
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        log.exception("auth.register.error", email=req.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "REGISTER_FAILED"},
        )


@auth_router.post("/login", response_model=TokenResponse, summary="Login with email + password")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify credentials and return an 8-hour access token."""
    try:
        user = db.query(UserModel).filter(UserModel.email == req.email).first()
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Invalid email or password", "code": "BAD_CREDENTIALS"},
            )
        log.info("auth.login", user_id=user.id)
        return TokenResponse(access_token=create_access_token(user.id, user.email))
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("auth.login.error", email=req.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "LOGIN_FAILED"},
        )
