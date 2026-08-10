"""JSON APIs for Observatory / product-admin operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import billing_ops_service
from app.services import billing_service
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


class PatchBillingAccountBody(BaseModel):
    plan_code: str | None = None
    status: str | None = None


class QuotaOverrideBody(BaseModel):
    value: int
    reason: str | None = None
    expires_at: str | None = None


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


@router.get("/billing-accounts/{ba_id}")
def api_billing_account_detail(
    ba_id: str, actor: PortalActor = Depends(require_product_admin_actor)
) -> JSONResponse:
    _ = actor
    account = billing_service.get_billing_account(ba_id)
    if not account:
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    return JSONResponse(account)


@router.patch("/billing-accounts/{ba_id}")
def api_patch_billing_account(
    request: Request,
    ba_id: str,
    body: PatchBillingAccountBody,
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    if body.plan_code is None and body.status is None:
        raise HTTPException(status_code=400, detail="plan_code or status required")
    result = billing_service.set_billing_account_plan(
        ba_id, plan_code=body.plan_code, status=body.status, actor_principal_id=actor.principal_id
    )
    return JSONResponse(result)


@router.put("/billing-accounts/{ba_id}/overrides/{quota_key}")
def api_put_billing_override(
    request: Request,
    ba_id: str,
    quota_key: str,
    body: QuotaOverrideBody,
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    return JSONResponse(
        billing_service.set_quota_override(
            ba_id, quota_key, body.value, reason=body.reason, expires_at=body.expires_at
        )
    )


@router.delete("/billing-accounts/{ba_id}/overrides/{quota_key}")
def api_delete_billing_override(
    request: Request,
    ba_id: str,
    quota_key: str,
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    assert_mutating_auth(request, actor)
    if not billing_service.get_billing_account(ba_id):
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    billing_service.clear_quota_override(ba_id, quota_key)
    return JSONResponse({"ok": True})


@router.get("/orgs")
def api_admin_orgs(
    limit: int = Query(200, ge=1, le=500),
    actor: PortalActor = Depends(require_product_admin_actor),
) -> JSONResponse:
    _ = actor
    rows = db.list_organizations_for_ops(limit=limit)
    return JSONResponse({"orgs": rows, "limit": limit})
