"""Mock IAM API — destructive identity endpoints for NeuraDesk.

Exposed as an APIRouter that is included into the mock enterprise API app
(services.enterprise_api), so these endpoints share the same base URL and the
same ENTERPRISE_API_SECRET as the ITSM and HR endpoints — no new port or env var.

Endpoints (all DESTRUCTIVE — gated behind explicit confirmation upstream):
    POST /iam/revoke-access   — remove a user's access to a resource
    POST /iam/lock-account    — disable/suspend a user's account
    POST /iam/delete-account  — permanently delete a user account
                                (requires confirm=true in the body)

Every call requires `Authorization: Bearer <ENTERPRISE_API_SECRET>` and is
appended to the audit log via services.audit_log.log_audit.
"""

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from services.audit_log import log_audit

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/iam", tags=["iam"])

# Same shared secret as the ITSM/HR endpoints — these run in the same app.
_SECRET: str = os.environ.get("ENTERPRISE_API_SECRET", "")
_http_bearer = HTTPBearer(auto_error=True)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> str:
    """Validate the Bearer token against ENTERPRISE_API_SECRET; raise 401 on mismatch."""
    if not _SECRET:
        raise RuntimeError(
            "ENTERPRISE_API_SECRET is not set. Set it in .env before starting the service."
        )
    if credentials.credentials != _SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid API token", "code": "TOKEN_INVALID"},
        )
    return credentials.credentials


def _envelope(action: str, result: dict[str, Any]) -> dict[str, Any]:
    """Wrap result data in the standard enterprise API response shape (always destructive)."""
    return {
        "success": True,
        "action": action,
        "destructive": True,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Request schemas ───────────────────────────────────────────────────────────

class RevokeAccessRequest(BaseModel):
    """Body for POST /iam/revoke-access."""

    user_id: str
    resource: str
    reason: str = ""


class LockAccountRequest(BaseModel):
    """Body for POST /iam/lock-account."""

    user_id: str
    reason: str = ""


class DeleteAccountRequest(BaseModel):
    """Body for POST /iam/delete-account."""

    user_id: str
    confirm: bool = False
    reason: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/revoke-access", summary="Revoke a user's access to a resource (DESTRUCTIVE)")
async def revoke_access(
    req: RevokeAccessRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Remove a user's existing access to a named resource. Requires explicit upstream confirmation."""
    response_status = 500
    start = time.monotonic()
    try:
        result = _envelope(
            action="revoke-access",
            result={
                "user_id": req.user_id,
                "resource": req.resource,
                "revoked": True,
                "ref": f"REV-{uuid.uuid4().hex[:6].upper()}",
            },
        )
        response_status = 200
        log.info("iam.revoke-access", user_id=req.user_id, resource=req.resource)
        return result
    except Exception as exc:
        log.exception("iam.revoke-access.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "REVOKE_FAILED"},
        )
    finally:
        await log_audit(
            "/iam/revoke-access", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )


@router.post("/lock-account", summary="Lock or suspend a user's account (DESTRUCTIVE)")
async def lock_account(
    req: LockAccountRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Disable a user's account/login. Requires explicit upstream confirmation."""
    response_status = 500
    start = time.monotonic()
    try:
        result = _envelope(
            action="lock-account",
            result={
                "user_id": req.user_id,
                "locked": True,
                "ref": f"LCK-{uuid.uuid4().hex[:6].upper()}",
            },
        )
        response_status = 200
        log.info("iam.lock-account", user_id=req.user_id)
        return result
    except Exception as exc:
        log.exception("iam.lock-account.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "LOCK_FAILED"},
        )
    finally:
        await log_audit(
            "/iam/lock-account", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )


@router.post("/delete-account", summary="Permanently delete a user account (DESTRUCTIVE)")
async def delete_account(
    req: DeleteAccountRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Permanently delete a user account.

    Defense in depth: refuses to act unless the request body carries
    confirm=true, even though the agent only reaches this endpoint after the
    upstream confirmation gate has been satisfied.
    """
    response_status = 500
    start = time.monotonic()
    try:
        if not req.confirm:
            response_status = 400
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Account deletion requires confirm=true",
                    "code": "CONFIRMATION_REQUIRED",
                },
            )
        result = _envelope(
            action="delete-account",
            result={
                "user_id": req.user_id,
                "deleted": True,
                "ref": f"DEL-{uuid.uuid4().hex[:6].upper()}",
            },
        )
        response_status = 200
        log.info("iam.delete-account", user_id=req.user_id)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("iam.delete-account.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "DELETE_FAILED"},
        )
    finally:
        await log_audit(
            "/iam/delete-account", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )
