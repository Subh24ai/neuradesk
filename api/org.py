"""Organisation management endpoints."""

import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.models import (
    MemberResponse,
    MembersListResponse,
    OrganizationModel,
    OrgResponse,
    UserModel,
    get_db,
)

log = structlog.get_logger(__name__)

org_router = APIRouter(prefix="/orgs", tags=["orgs"])


def _require_admin(user: UserModel) -> None:
    """Raise 403 if the user is not an org admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin access required", "code": "FORBIDDEN"},
        )


@org_router.get("/me", response_model=OrgResponse, summary="Get the caller's organisation")
def get_my_org(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgResponse:
    """Return the organisation the caller belongs to."""
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User has no organisation", "code": "NO_ORG"},
        )
    org = db.get(OrganizationModel, current_user.org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Organisation not found", "code": "ORG_NOT_FOUND"},
        )
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        invite_code=org.invite_code,
        created_at=org.created_at,
    )


@org_router.post(
    "/invite/regenerate",
    response_model=OrgResponse,
    summary="Regenerate the org invite code (admin only)",
)
def regenerate_invite(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgResponse:
    """Issue a new invite code and invalidate the old one. Admin only."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User has no organisation", "code": "NO_ORG"},
        )
    org = db.get(OrganizationModel, current_user.org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Organisation not found", "code": "ORG_NOT_FOUND"},
        )
    org.invite_code = secrets.token_urlsafe(12)
    db.commit()
    log.info("org.invite_regenerated", org_id=org.id)
    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        invite_code=org.invite_code,
        created_at=org.created_at,
    )


@org_router.get(
    "/members",
    response_model=MembersListResponse,
    summary="List all members of the caller's organisation (admin only)",
)
def list_members(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembersListResponse:
    """Return all verified users in the same org. Admin only."""
    _require_admin(current_user)
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User has no organisation", "code": "NO_ORG"},
        )
    members = (
        db.query(UserModel)
        .filter(UserModel.org_id == current_user.org_id, UserModel.is_verified == True)  # noqa: E712
        .order_by(UserModel.created_at)
        .all()
    )
    return MembersListResponse(
        members=[
            MemberResponse(
                id=m.id, email=m.email, first_name=m.first_name, last_name=m.last_name,
                role=m.role, created_at=m.created_at,
            )
            for m in members
        ],
        total=len(members),
    )
