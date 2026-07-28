"""JSON APIs for Observatory / product-admin operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import billing_ops_service
from app.services.onboarding_service import set_user_paid
from app.services.portal_actor_service import (
    PortalActor,
    assert_mutating_auth,
    require_product_admin_actor,
)
from app.storage import db

router = APIRouter(prefix="/api/admin", tags=["admin-api"])


class PatchUserPlanBody(BaseModel):
    paid: bool


@router.get("/observatory/stats")
def api_observatory_stats(
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    _ = actor
    return JSONResponse(db.get_system_stats())


@router.get("/billing/overview")
def api_billing_overview(
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    _ = actor
    return JSONResponse(billing_ops_service.billing_overview())


@router.get("/users")
def api_admin_users(
    q: str | None = Query(default=None),
    paid_only: bool = Query(default=False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    _ = actor
    total, rows = billing_ops_service.list_users_for_billing(
        query=q, paid_only=paid_only, limit=limit, offset=offset
    )
    return JSONResponse({"total": total, "users": rows, "limit": limit, "offset": offset})


@router.patch("/users/{principal_id}/plan")
def api_patch_user_plan(
    request: Request,
    principal_id: str,
    body: PatchUserPlanBody,
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    try:
        result = set_user_paid(principal_id=principal_id, paid=body.paid)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.get("/orgs")
def api_admin_orgs(
    limit: int = Query(200, ge=1, le=500),
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    _ = actor
    rows = db.list_organizations_for_ops(limit=limit)
    return JSONResponse({"orgs": rows, "limit": limit})
