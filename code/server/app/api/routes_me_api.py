"""JSON APIs for current principal (/api/me) and principal search."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.onboarding_service import ensure_personal_library, ensure_personal_org
from app.services.org_service import search_members_by_display_name
from app.services.portal_actor_service import (
    PortalActor,
    assert_mutating_auth,
    require_portal_actor,
)
from app.services.principal_service import (
    complete_display_name_setup,
    display_name_setup_required,
)
from app.storage import db

router = APIRouter(prefix="/api", tags=["me-api"])


class PatchMeBody(BaseModel):
    display_name: str = Field(min_length=2, max_length=32)


def _me_payload(actor: PortalActor) -> dict:
    ensure_personal_org(actor.principal_id, actor.display_name)
    personal = ensure_personal_library(actor.principal_id, actor.display_name)
    account = db.get_local_account_by_principal(actor.principal_id)
    return {
        "principal_id": actor.principal_id,
        "display_name": actor.display_name,
        "is_admin": actor.is_admin,
        "via": actor.via,
        "display_name_setup_required": display_name_setup_required(actor.principal_id),
        "username": str(account["username"]) if account else None,
        "personal_library_id": personal.get("library_id"),
        "plan_code": db.get_principal_plan_code(actor.principal_id),
    }


@router.get("/me")
def api_me(actor: PortalActor = Depends(require_portal_actor)) -> JSONResponse:
    return JSONResponse(_me_payload(actor))


@router.patch("/me")
def api_patch_me(
    request: Request,
    body: PatchMeBody,
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    name = complete_display_name_setup(actor.principal_id, body.display_name)
    actor = PortalActor(
        principal_id=actor.principal_id,
        display_name=name,
        is_admin=actor.is_admin,
        via=actor.via,
        api_key_id=actor.api_key_id,
    )
    return JSONResponse(_me_payload(actor))


@router.get("/principals")
def api_search_principals(
    q: str = Query("", min_length=0, max_length=80),
    limit: int = Query(10, ge=1, le=50),
    actor: PortalActor = Depends(require_portal_actor),
) -> JSONResponse:
    _ = actor
    rows = search_members_by_display_name(q, limit=limit) if q.strip() else []
    return JSONResponse({"principals": rows, "query": q})
