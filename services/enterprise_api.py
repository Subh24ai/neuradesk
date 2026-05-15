"""Mock enterprise API — ITSM and HR endpoints for NeuraDesk integration.

Run with:
    uvicorn services.enterprise_api:app --port 8001

Every endpoint requires:
    Authorization: Bearer <ENTERPRISE_API_SECRET>

Every call is appended to services/audit.jsonl via async write.
"""

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from services.audit_log import log_audit

load_dotenv()

log = structlog.get_logger(__name__)

_SECRET: str = os.environ.get("ENTERPRISE_API_SECRET", "")
_http_bearer = HTTPBearer(auto_error=True)

app = FastAPI(
    title="NeuraDesk Mock Enterprise API",
    version="0.1.0",
    description="Stub ITSM/HR service endpoints — local dev and testing only.",
)


# ── Auth dependency ───────────────────────────────────────────────────────────

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


# ── Response envelope ─────────────────────────────────────────────────────────

def _envelope(action: str, destructive: bool, result: dict[str, Any]) -> dict[str, Any]:
    """Wrap result data in the standard enterprise API response shape."""
    return {
        "success": True,
        "action": action,
        "destructive": destructive,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Request schemas ───────────────────────────────────────────────────────────

class ResetPasswordRequest(BaseModel):
    """Body for POST /itsm/reset-password."""

    user_id: str
    email: str


class ProvisionAccessRequest(BaseModel):
    """Body for POST /itsm/provision-access."""

    user_id: str
    resource: str
    role: str


class ApproveLeaveRequest(BaseModel):
    """Body for POST /hr/approve-leave."""

    user_id: str
    start_date: str
    end_date: str
    days: int


class CreateIncidentRequest(BaseModel):
    """Body for POST /itsm/create-incident."""

    user_id: str
    description: str
    severity: str


class NotifyManagerRequest(BaseModel):
    """Body for POST /itsm/notify-manager."""

    user_id: str
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post(
    "/itsm/reset-password",
    summary="Reset a user's password (DESTRUCTIVE)",
    tags=["itsm"],
)
async def reset_password(
    req: ResetPasswordRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Generate a temporary password for the user. Requires explicit upstream confirmation."""
    response_status = 500
    start = time.monotonic()
    try:
        result = _envelope(
            action="reset-password",
            destructive=True,
            result={
                "user_id": req.user_id,
                "email": req.email,
                "temp_password": f"Tmp-{uuid.uuid4().hex[:8]}!",
                "expires_in_hours": 24,
                "ref": f"PWD-{uuid.uuid4().hex[:6].upper()}",
            },
        )
        response_status = 200
        log.info("enterprise.reset-password", user_id=req.user_id, email=req.email)
        return result
    except Exception as exc:
        log.exception("enterprise.reset-password.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "RESET_FAILED"},
        )
    finally:
        await log_audit(
            "/itsm/reset-password", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )


@app.post(
    "/itsm/provision-access",
    summary="Provision resource access for a user (DESTRUCTIVE)",
    tags=["itsm"],
)
async def provision_access(
    req: ProvisionAccessRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Grant a user a role on a named resource. Requires explicit upstream confirmation."""
    response_status = 500
    start = time.monotonic()
    try:
        result = _envelope(
            action="provision-access",
            destructive=True,
            result={
                "user_id": req.user_id,
                "resource": req.resource,
                "role": req.role,
                "ticket_ref": f"ACC-{uuid.uuid4().hex[:6].upper()}",
                "effective_immediately": True,
            },
        )
        response_status = 200
        log.info("enterprise.provision-access", user_id=req.user_id, resource=req.resource, role=req.role)
        return result
    except Exception as exc:
        log.exception("enterprise.provision-access.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "PROVISION_FAILED"},
        )
    finally:
        await log_audit(
            "/itsm/provision-access", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )


@app.post(
    "/hr/approve-leave",
    summary="Approve an employee leave request",
    tags=["hr"],
)
async def approve_leave(
    req: ApproveLeaveRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Approve the requested leave dates and return an approval reference."""
    response_status = 500
    start = time.monotonic()
    try:
        result = _envelope(
            action="approve-leave",
            destructive=False,
            result={
                "user_id": req.user_id,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "days_approved": req.days,
                "approval_ref": f"LVE-{uuid.uuid4().hex[:6].upper()}",
                "approver": "system-auto",
            },
        )
        response_status = 200
        log.info("enterprise.approve-leave", user_id=req.user_id, days=req.days)
        return result
    except Exception as exc:
        log.exception("enterprise.approve-leave.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "LEAVE_FAILED"},
        )
    finally:
        await log_audit(
            "/hr/approve-leave", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )


@app.post(
    "/itsm/create-incident",
    summary="Open a new incident record",
    tags=["itsm"],
)
async def create_incident(
    req: CreateIncidentRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Create an incident ticket and route it to the appropriate team."""
    response_status = 500
    start = time.monotonic()
    try:
        assigned = "sre-oncall" if req.severity.lower() in ("p1", "critical") else "tier-2-support"
        result = _envelope(
            action="create-incident",
            destructive=False,
            result={
                "incident_id": f"INC-{uuid.uuid4().hex[:8].upper()}",
                "user_id": req.user_id,
                "severity": req.severity,
                "description_preview": req.description[:200],
                "status": "open",
                "assigned_team": assigned,
            },
        )
        response_status = 200
        log.info("enterprise.create-incident", user_id=req.user_id, severity=req.severity, team=assigned)
        return result
    except Exception as exc:
        log.exception("enterprise.create-incident.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "INCIDENT_FAILED"},
        )
    finally:
        await log_audit(
            "/itsm/create-incident", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )


@app.post(
    "/itsm/notify-manager",
    summary="Send a notification to the user's manager",
    tags=["itsm"],
)
async def notify_manager(
    req: NotifyManagerRequest,
    token: str = Depends(verify_token),
) -> dict:
    """Deliver an email notification to the reporting manager of the given user."""
    response_status = 500
    start = time.monotonic()
    try:
        result = _envelope(
            action="notify-manager",
            destructive=False,
            result={
                "user_id": req.user_id,
                "message_preview": req.message[:100],
                "notification_id": f"NTF-{uuid.uuid4().hex[:6].upper()}",
                "channel": "email",
                "delivered": True,
            },
        )
        response_status = 200
        log.info("enterprise.notify-manager", user_id=req.user_id)
        return result
    except Exception as exc:
        log.exception("enterprise.notify-manager.error", user_id=req.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "NOTIFY_FAILED"},
        )
    finally:
        await log_audit(
            "/itsm/notify-manager", token, req.model_dump(),
            response_status, (time.monotonic() - start) * 1000,
        )
