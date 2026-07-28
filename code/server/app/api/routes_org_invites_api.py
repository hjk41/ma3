"""REST APIs for organization invite links/codes."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services import org_invite_service
from app.services.portal_actor_service import (
    PortalActor,
    assert_mutating_auth,
    require_portal_actor,
)

router = APIRouter(tags=["org-invites-api"])

InviteRole = Literal["admin", "member"]


class CreateInviteBody(BaseModel):
    role: InviteRole = "member"
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_in_hours: int | None = Field(default=168, ge=1, le=2160)
    member_alias: str | None = Field(default=None, max_length=32)


class RedeemInviteBody(BaseModel):
    token: str = Field(min_length=8, max_length=200)


def _base_url(request: Request) -> str:
    from app.core.config import settings

    return (settings.public_base_url or str(request.base_url)).rstrip("/")


@router.post("/api/orgs/{org_id}/invites")
def api_create_invite(
    request: Request,
    org_id: str,
    body: CreateInviteBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    created = org_invite_service.create_org_invite(
        org_id=org_id,
        actor_principal_id=actor.principal_id,
        role=body.role,
        max_uses=body.max_uses,
        expires_in_hours=body.expires_in_hours,
        base_url=_base_url(request),
        member_alias=body.member_alias,
    )
    return JSONResponse(created, status_code=201)


@router.get("/api/orgs/{org_id}/invites")
def api_list_invites(
    org_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    rows = org_invite_service.list_org_invites(org_id=org_id, actor_principal_id=actor.principal_id)
    return JSONResponse({"org_id": org_id, "invites": rows})


@router.delete("/api/orgs/{org_id}/invites/{invite_id}")
def api_revoke_invite(
    request: Request,
    org_id: str,
    invite_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    row = org_invite_service.revoke_org_invite(
        org_id=org_id,
        invite_id=invite_id,
        actor_principal_id=actor.principal_id,
    )
    return JSONResponse(row)


@router.get("/api/invites/preview")
def api_preview_invite(token: str = Query(..., min_length=8, max_length=200)) -> JSONResponse:
    return JSONResponse(org_invite_service.preview_invite(token))


@router.post("/api/invites/redeem")
def api_redeem_invite(
    request: Request,
    body: RedeemInviteBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    """Existing account joins org via invite (no new registration)."""
    assert_mutating_auth(request, actor)
    result = org_invite_service.redeem_invite(token=body.token, principal_id=actor.principal_id)
    return JSONResponse(result)
