"""Resolve local-auth actors for JSON management APIs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException, Request

from app.auth.session import resolve_session_user
from app.core.config import settings
from app.core.security import assert_same_origin, extract_credential, resolve_from_credential
from app.storage import db

ActorVia = Literal["session", "api_key"]


@dataclass(slots=True)
class LocalActor:
    username: str
    principal_id: str
    display_name: str
    is_admin: bool
    via: ActorVia
    admin_source: str  # database | env | both


def _require_local_auth() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=503, detail="local auth is not enabled")


def _env_admin_usernames() -> set[str]:
    return {a.lower() for a in settings.auth_admin_users}


def account_admin_flags(account: dict) -> tuple[bool, str]:
    """Return (is_admin, admin_source) for a local_accounts row."""
    username = str(account.get("username") or "").lower()
    db_admin = bool(int(account.get("is_admin") or 0))
    env_admin = username in _env_admin_usernames()
    if db_admin and env_admin:
        return True, "both"
    if db_admin:
        return True, "database"
    if env_admin:
        return True, "env"
    return False, "none"


def public_account(account: dict, *, display_name: str | None = None) -> dict:
    is_admin, admin_source = account_admin_flags(account)
    username = str(account["username"])
    pid = str(account["principal_id"])
    if display_name is None:
        principal = db.get_user_principal(pid)
        display_name = str(principal["display_name"]) if principal else username
    return {
        "username": username,
        "principal_id": pid,
        "display_name": display_name,
        "is_admin": is_admin,
        "admin_source": admin_source,
        "created_at": account.get("created_at"),
    }


def resolve_local_actor(
    request: Request,
    *,
    x_api_key: str | None = None,
    authorization: str | None = None,
) -> LocalActor | None:
    """Resolve a local account actor from session cookie or X-API-Key/Bearer."""
    _require_local_auth()
    cred = extract_credential(x_api_key, authorization)
    if cred is not None:
        principal = resolve_from_credential(cred)
        if principal.kind == "anonymous":
            raise HTTPException(status_code=401, detail="authentication required")
        if principal.principal_id == settings.bootstrap_principal_id:
            raise HTTPException(status_code=403, detail="bootstrap key cannot manage local users")
        account = db.get_local_account_by_principal(principal.principal_id)
        if account is None:
            raise HTTPException(status_code=403, detail="local account required")
        is_admin, admin_source = account_admin_flags(account)
        return LocalActor(
            username=str(account["username"]),
            principal_id=str(account["principal_id"]),
            display_name=principal.display_name,
            is_admin=is_admin,
            via="api_key",
            admin_source=admin_source,
        )

    user = resolve_session_user(request)
    if user is None:
        return None
    if user.via != "local":
        raise HTTPException(status_code=403, detail="local account required")
    account = db.get_local_account_by_principal(user.principal_id)
    if account is None:
        raise HTTPException(status_code=403, detail="local account required")
    is_admin, admin_source = account_admin_flags(account)
    return LocalActor(
        username=str(account["username"]),
        principal_id=str(account["principal_id"]),
        display_name=user.display_name,
        is_admin=is_admin,
        via="session",
        admin_source=admin_source,
    )


def require_local_actor(
    request: Request,
    *,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> LocalActor:
    actor = resolve_local_actor(request, x_api_key=x_api_key, authorization=authorization)
    if actor is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return actor


def require_local_admin_actor(
    request: Request,
    *,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> LocalActor:
    actor = require_local_actor(request, x_api_key=x_api_key, authorization=authorization)
    if not actor.is_admin:
        raise HTTPException(status_code=403, detail="local admin access required")
    return actor


def assert_mutating_auth(request: Request, actor: LocalActor) -> None:
    """Cookie sessions need same-origin; API keys skip CSRF checks."""
    if actor.via == "session":
        assert_same_origin(request)


def count_database_admins() -> int:
    return int(db.count_local_admins())
