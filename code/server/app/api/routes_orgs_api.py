"""JSON APIs for organizations and membership."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.library_admin_service import create_org_library
from app.services.onboarding_service import ensure_personal_org
from app.services.org_quota_service import team_org_creation_summary
from app.services.org_service import (
    add_org_member,
    assert_active_org_member,
    create_team_org,
    remove_org_member,
    update_org_member,
)
from app.services.portal_actor_service import (
    PortalActor,
    assert_mutating_auth,
    require_portal_actor,
)
from app.storage import db

router = APIRouter(prefix="/api/orgs", tags=["orgs-api"])

OrgMemberRole = Literal["admin", "member"]
LibraryVisibility = Literal["private", "org"]


class CreateOrgBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class AddMemberBody(BaseModel):
    principal_id: str | None = None
    username: str | None = None
    display_name: str | None = None
    role: OrgMemberRole = "member"
    alias: str | None = Field(default=None, max_length=32)


class PatchMemberBody(BaseModel):
    role: OrgMemberRole | None = None
    alias: str | None = Field(default=None, max_length=32)


class CreateLibraryBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    visibility: LibraryVisibility = "private"
    confirm_org_visibility: bool = False
    write_buffer_hours: int = Field(default=24, ge=0, le=168)


def _public_org(row: dict) -> dict:
    return {
        "id": row.get("id") or row.get("org_id"),
        "name": row.get("name"),
        "kind": row.get("kind"),
        "owner_principal_id": row.get("owner_principal_id"),
        "billing_account_id": row.get("billing_account_id"),
        "role": row.get("role"),
        "seat_status": row.get("seat_status"),
        "joined_at": row.get("joined_at"),
    }


def _public_member(row: dict) -> dict:
    return {
        "org_id": row.get("org_id"),
        "principal_id": row.get("principal_id"),
        "display_name": row.get("display_name"),
        "alias": row.get("alias"),
        "role": row.get("role"),
        "seat_status": row.get("seat_status"),
        "joined_at": row.get("joined_at"),
    }


def _public_library(row: dict) -> dict:
    lid = row.get("library_id") or row.get("id")
    return {
        "library_id": lid,
        "name": row.get("name"),
        "visibility": row.get("visibility"),
        "kind": row.get("kind"),
        "org_id": row.get("org_id"),
        "write_buffer_hours": db.get_library_write_buffer_hours(str(lid)) if lid else None,
    }


@router.get("")
@router.get("/")
def api_list_orgs(actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    ensure_personal_org(actor.principal_id, actor.display_name)
    rows = db.list_orgs_for_principal(actor.principal_id)
    return JSONResponse({"orgs": [_public_org(r) for r in rows]})


@router.post("")
@router.post("/")
def api_create_org(
    request: Request,
    body: CreateOrgBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    org = create_team_org(
        name=body.name,
        owner_principal_id=actor.principal_id,
        is_product_admin=actor.is_admin,
    )
    return JSONResponse(_public_org(org), status_code=201)


@router.get("/creation-quota")
def api_org_creation_quota(actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    return JSONResponse(team_org_creation_summary(actor.principal_id, is_product_admin=actor.is_admin))


@router.get("/{org_id}")
def api_get_org(org_id: str, actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    assert_active_org_member(org_id, actor.principal_id)
    org = db.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    member = db.get_org_member(org_id, actor.principal_id) or {}
    libs = db.list_org_libraries(org_id)
    return JSONResponse(
        {
            **_public_org({**org, **member}),
            "members_count": db.count_active_org_members(org_id),
            "storage_bytes": db.sum_org_storage_bytes(org_id),
            "libraries": [_public_library(lib) for lib in libs],
        }
    )


@router.get("/{org_id}/settings")
def api_org_settings(org_id: str, actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    assert_active_org_member(org_id, actor.principal_id)
    org = db.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    return JSONResponse(
        {
            "id": org["id"],
            "name": org.get("name"),
            "kind": org.get("kind"),
            "billing_account_id": org.get("billing_account_id"),
            "owner_principal_id": org.get("owner_principal_id"),
            "members_count": db.count_active_org_members(org_id),
            "storage_bytes": db.sum_org_storage_bytes(org_id),
        }
    )


@router.get("/{org_id}/members")
def api_list_members(org_id: str, actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    assert_active_org_member(org_id, actor.principal_id)
    rows = db.list_org_members(org_id)
    return JSONResponse({"org_id": org_id, "members": [_public_member(r) for r in rows]})


@router.post("/{org_id}/members")
def api_add_member(
    request: Request,
    org_id: str,
    body: AddMemberBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    row = add_org_member(
        org_id=org_id,
        actor_principal_id=actor.principal_id,
        principal_id=body.principal_id,
        username=body.username,
        display_name=body.display_name,
        role=body.role,
        alias=body.alias,
    )
    principal = db.get_user_principal(str(row["principal_id"]))
    return JSONResponse(
        _public_member({**row, "display_name": principal.get("display_name") if principal else None}),
        status_code=201,
    )


@router.patch("/{org_id}/members/{principal_id}")
def api_patch_member(
    request: Request,
    org_id: str,
    principal_id: str,
    body: PatchMemberBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    if body.role is None and "alias" not in body.model_fields_set:
        raise HTTPException(status_code=400, detail="role or alias required")
    row = update_org_member(
        org_id=org_id,
        actor_principal_id=actor.principal_id,
        target_principal_id=principal_id,
        role=body.role,
        alias=body.alias,
        alias_provided="alias" in body.model_fields_set,
    )
    principal = db.get_user_principal(principal_id)
    return JSONResponse(
        _public_member({**row, "display_name": principal.get("display_name") if principal else None})
    )


@router.delete("/{org_id}/members/{principal_id}")
def api_remove_member(
    request: Request,
    org_id: str,
    principal_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    remove_org_member(
        org_id=org_id,
        actor_principal_id=actor.principal_id,
        target_principal_id=principal_id,
    )
    return JSONResponse({"deleted": True, "org_id": org_id, "principal_id": principal_id})


@router.post("/{org_id}/libraries")
def api_create_org_library(
    request: Request,
    org_id: str,
    body: CreateLibraryBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    lib = create_org_library(
        org_id=org_id,
        actor_principal_id=actor.principal_id,
        name=body.name,
        visibility=body.visibility,
        confirm_org_visibility=body.confirm_org_visibility,
        write_buffer_hours=body.write_buffer_hours,
    )
    return JSONResponse(_public_library(lib), status_code=201)
