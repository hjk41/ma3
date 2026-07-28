"""JSON APIs for local account administration."""
from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services import local_auth_service
from app.services.local_admin_service import (
    LocalActor,
    account_admin_flags,
    assert_mutating_auth,
    count_database_admins,
    public_account,
    require_local_admin_actor,
)
from app.storage import db

router = APIRouter(prefix="/api/local-users", tags=["local-users-api"])


class PatchUserBody(BaseModel):
    is_admin: bool


def _require_local_auth() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=503, detail="local auth is not enabled")


@router.get("")
@router.get("/")
def api_list_local_users(
    actor: LocalActor = Depends(require_local_admin_actor),
    limit: int = Query(default=200, ge=1, le=500),
) -> JSONResponse:
    _require_local_auth()
    users = [public_account(row) for row in local_auth_service.list_local_accounts(limit=limit)]
    return JSONResponse({"users": users})


@router.patch("/{username}")
def api_patch_local_user(
    request: Request,
    username: str,
    body: PatchUserBody,
    actor: LocalActor = Depends(require_local_admin_actor),
) -> JSONResponse:
    _require_local_auth()
    assert_mutating_auth(request, actor)
    uname = local_auth_service.normalize_username(username)
    row = db.get_local_account(uname)
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")

    _, admin_source = account_admin_flags(row)
    if not body.is_admin and admin_source in {"env", "both"}:
        raise HTTPException(
            status_code=409,
            detail="administrator is configured by MA3_AUTH_ADMIN_USERS",
        )

    if not body.is_admin and bool(int(row.get("is_admin") or 0)):
        if count_database_admins() <= 1:
            raise HTTPException(status_code=409, detail="cannot remove the last local admin")

    updated = local_auth_service.set_local_account_admin(username=uname, is_admin=body.is_admin)
    if updated is None:
        raise HTTPException(status_code=404, detail="user not found")
    return JSONResponse(public_account(updated))
