"""Resolve portal principals for JSON APIs (session cookie or X-API-Key)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException, Request

from app.auth.session import resolve_session_user
from app.core.config import settings
from app.core.security import assert_same_origin, extract_credential, resolve_from_credential
from app.services.local_admin_service import account_admin_flags
from app.storage import db

ActorVia = Literal["session", "api_key"]


@dataclass(slots=True)
class PortalActor:
    principal_id: str
    display_name: str
    is_admin: bool
    via: ActorVia
    api_key_id: str | None = None


def _is_product_admin(principal_id: str) -> bool:
    account = db.get_local_account_by_principal(principal_id)
    if account is not None:
        is_admin, _ = account_admin_flags(account)
        if is_admin:
            return True
    admins = {a.lower() for a in settings.auth_admin_users}
    if not admins:
        return False
    candidates = {str(principal_id).lower()}
    if str(principal_id).startswith("user:"):
        candidates.add(str(principal_id).removeprefix("user:").lower())
    principal = db.get_user_principal(principal_id)
    if principal is not None:
        candidates.add(str(principal.get("display_name") or "").lower())
    return bool(candidates & admins)


def resolve_portal_actor(
    request: Request,
    *,
    x_api_key: str | None = None,
    authorization: str | None = None,
) -> PortalActor | None:
    """Resolve a user principal from X-API-Key/Bearer or session cookie."""
    if not settings.portal_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail="portal auth is not enabled (enable MA3_LOCAL_AUTH or OIDC)",
        )

    cred = extract_credential(x_api_key, authorization)
    if cred is not None:
        principal = resolve_from_credential(cred)
        if principal.kind == "anonymous" or principal.via == "invalid_credentials":
            raise HTTPException(status_code=401, detail="authentication required")
        if principal.principal_id == settings.bootstrap_principal_id:
            raise HTTPException(
                status_code=403,
                detail="bootstrap key cannot manage portal resources; use a user API key",
            )
        if principal.kind not in {"user", "api_key"} or not str(principal.principal_id).startswith("user:"):
            raise HTTPException(status_code=403, detail="user API key or session required")
        return PortalActor(
            principal_id=str(principal.principal_id),
            display_name=str(principal.display_name or principal.principal_id),
            is_admin=_is_product_admin(str(principal.principal_id)),
            via="api_key",
            api_key_id=principal.key_id,
        )

    user = resolve_session_user(request)
    if user is None:
        return None
    return PortalActor(
        principal_id=user.principal_id,
        display_name=user.display_name,
        is_admin=bool(user.is_admin),
        via="session",
        api_key_id=None,
    )


def require_portal_actor(
    request: Request,
    *,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> PortalActor:
    actor = resolve_portal_actor(request, x_api_key=x_api_key, authorization=authorization)
    if actor is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return actor


def require_product_admin_actor(
    request: Request,
    *,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> PortalActor:
    actor = require_portal_actor(request, x_api_key=x_api_key, authorization=authorization)
    if not actor.is_admin:
        raise HTTPException(status_code=403, detail="product admin access required")
    return actor


def assert_mutating_auth(request: Request, actor: PortalActor) -> None:
    """Cookie sessions need same-origin; API keys skip CSRF checks."""
    if actor.via == "session":
        assert_same_origin(request)
