"""JSON APIs for libraries, grants, settings, and storage."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.buffer_service import is_library_settings_editor
from app.services.entitlement_service import can_read_library
from app.services.library_admin_service import (
    add_library_grant,
    assert_library_maintainer,
    remove_library_grant,
)
from app.services.portal_actor_service import (
    PortalActor,
    assert_mutating_auth,
    require_portal_actor,
)
from app.services.portal_service import list_entitled_libraries
from app.services.storage_quota_service import personal_library_quota_summary
from app.storage import db

router = APIRouter(prefix="/api/libraries", tags=["libraries-api"])

GrantRole = Literal["reader", "writer", "maintainer"]


class AddGrantBody(BaseModel):
    principal_id: str | None = None
    username: str | None = None
    display_name: str | None = None
    role: GrantRole = "reader"


class PatchLibrarySettingsBody(BaseModel):
    write_buffer_hours: int = Field(ge=0, le=168)


def _public_grant(row: dict) -> dict:
    return {
        "library_id": row.get("library_id"),
        "principal_id": row.get("principal_id"),
        "display_name": row.get("display_name"),
        "role": row.get("role"),
        "created_at": row.get("created_at"),
        "created_by": row.get("created_by"),
    }


def _public_library_detail(lib: dict, *, actor: PortalActor) -> dict:
    lid = str(lib.get("library_id") or lib.get("id"))
    stats = db.get_library_stats(lid) or {}
    rec = stats.get("records") or {}
    return {
        "library_id": lid,
        "name": lib.get("name"),
        "visibility": lib.get("visibility"),
        "kind": lib.get("kind"),
        "org_id": lib.get("org_id"),
        "write_buffer_hours": db.get_library_write_buffer_hours(lid),
        "stats": {
            "cases": stats.get("cases", 0),
            "records_active": (rec.get("by_status") or {}).get("active", 0),
            "records_by_status": rec.get("by_status") or {},
        },
        "can_read": can_read_library(actor.principal_id, lid),
        "can_maintain": is_library_settings_editor(
            lid, actor.principal_id, is_admin=actor.is_admin
        ),
    }


@router.get("")
@router.get("/")
def api_list_libraries(actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    return JSONResponse({"libraries": list_entitled_libraries(actor.principal_id)})


@router.get("/{library_id}")
def api_get_library(
    library_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    if not can_read_library(actor.principal_id, library_id) and not actor.is_admin:
        raise HTTPException(status_code=404, detail="library not found")
    lib = db.get_library(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library not found")
    return JSONResponse(_public_library_detail(lib, actor=actor))


@router.get("/{library_id}/stats")
def api_library_stats(
    library_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    if not can_read_library(actor.principal_id, library_id) and not actor.is_admin:
        raise HTTPException(status_code=404, detail="library not found")
    stats = db.get_library_stats(library_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="library not found")
    return JSONResponse({"library_id": library_id, **stats})


@router.get("/{library_id}/records")
def api_library_records(
    library_id: str,
    page: int = Query(1, ge=1),
    status: str = Query("all"),
    per_page: int = Query(50, ge=1, le=200),
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    try:
        assert_library_maintainer(library_id, actor.principal_id)
    except HTTPException:
        if not actor.is_admin:
            raise HTTPException(status_code=404, detail="library not found") from None
    st = status if status in {"all", "active", "buffered", "draft", "invalid"} else "all"
    offset = (page - 1) * per_page
    records, total = db.list_records_for_library(
        library_id,
        status=None if st == "all" else st,
        limit=per_page,
        offset=offset,
    )
    items = []
    for rec in records:
        items.append(
            {
                "id": rec.get("id"),
                "status": rec.get("status"),
                "outcome": rec.get("outcome"),
                "problem": rec.get("problem"),
                "created_at": rec.get("created_at"),
                "created_by": rec.get("created_by"),
                "case_id": rec.get("case_id"),
            }
        )
    return JSONResponse(
        {
            "library_id": library_id,
            "page": page,
            "per_page": per_page,
            "total": total,
            "status": st,
            "records": items,
        }
    )


@router.get("/{library_id}/grants")
def api_list_grants(
    library_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    try:
        assert_library_maintainer(library_id, actor.principal_id)
    except HTTPException:
        if not actor.is_admin:
            raise HTTPException(status_code=404, detail="library not found") from None
    rows = db.list_library_grants(library_id)
    return JSONResponse({"library_id": library_id, "grants": [_public_grant(r) for r in rows]})


@router.post("/{library_id}/grants")
def api_add_grant(
    request: Request,
    library_id: str,
    body: AddGrantBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    row = add_library_grant(
        library_id=library_id,
        actor_principal_id=actor.principal_id,
        principal_id=body.principal_id,
        username=body.username,
        display_name=body.display_name,
        role=body.role,
    )
    principal = db.get_user_principal(str(row["principal_id"]))
    return JSONResponse(
        _public_grant({**row, "display_name": principal.get("display_name") if principal else None}),
        status_code=201,
    )


@router.delete("/{library_id}/grants/{principal_id}")
def api_remove_grant(
    request: Request,
    library_id: str,
    principal_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    remove_library_grant(
        library_id=library_id,
        actor_principal_id=actor.principal_id,
        target_principal_id=principal_id,
    )
    return JSONResponse({"deleted": True, "library_id": library_id, "principal_id": principal_id})


@router.get("/{library_id}/storage")
def api_library_storage(
    library_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    if not can_read_library(actor.principal_id, library_id) and not actor.is_admin:
        raise HTTPException(status_code=404, detail="library not found")
    if db.get_library(library_id) is None:
        raise HTTPException(status_code=404, detail="library not found")
    used = db.sum_library_record_content_bytes(library_id)
    quota = personal_library_quota_summary(principal_id=actor.principal_id, library_id=library_id)
    return JSONResponse(
        {
            "library_id": library_id,
            "used_bytes": used,
            "record_count": db.count_records_for_library(library_id),
            "max_record_bytes": settings.max_record_bytes,
            "quota": quota,
        }
    )


@router.get("/{library_id}/settings")
def api_get_library_settings(
    library_id: str,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    if not is_library_settings_editor(library_id, actor.principal_id, is_admin=actor.is_admin):
        raise HTTPException(status_code=404, detail="library not found")
    if db.get_library(library_id) is None:
        raise HTTPException(status_code=404, detail="library not found")
    return JSONResponse(
        {
            "library_id": library_id,
            "write_buffer_hours": db.get_library_write_buffer_hours(library_id),
        }
    )


@router.patch("/{library_id}/settings")
def api_patch_library_settings(
    request: Request,
    library_id: str,
    body: PatchLibrarySettingsBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    if not is_library_settings_editor(library_id, actor.principal_id, is_admin=actor.is_admin):
        raise HTTPException(status_code=404, detail="library not found")
    db.set_library_write_buffer_hours(library_id, body.write_buffer_hours)
    return JSONResponse(
        {
            "library_id": library_id,
            "write_buffer_hours": db.get_library_write_buffer_hours(library_id),
        }
    )
