"""v4 authentication: sessions, ma3v4_* API keys, optional dev login."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.time import utc_now_iso
from app.models.auth import ResolvedPrincipal
from app.services.metrics_service import metrics
from app.storage.repositories import PrincipalRepository
from app.storage.v4_repositories import ApiKeyGrantRepository, SessionRepository, V4ApiKeyRepository
from app.core.auth import _extract_raw, _is_admin_key, hash_token

_ADMIN_PRINCIPAL = ResolvedPrincipal(
    principal_id="admin:root",
    kind="admin",
    display_name="ma3 root admin",
    via="admin_key",
    is_admin_bypass=True,
)
_ANONYMOUS_PRINCIPAL = ResolvedPrincipal(
    principal_id="anonymous",
    kind="anonymous",
    display_name="anonymous",
    via="anonymous",
    is_admin_bypass=False,
)


def _session_from_request(request: Request) -> str | None:
    return request.cookies.get(settings.session_cookie)


def _session_expired(expires_at: str) -> bool:
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _principal_from_session(session_id: str) -> ResolvedPrincipal | None:
    session = SessionRepository().get(session_id)
    if session is None or _session_expired(session.expires_at):
        return None
    principal = PrincipalRepository().get(session.principal_id)
    if principal is None:
        return None
    return ResolvedPrincipal(
        principal_id=principal.principal_id,
        kind=principal.kind,
        display_name=principal.display_name,
        via="session",
        is_admin_bypass=False,
    )


def _principal_from_api_key(raw: str) -> ResolvedPrincipal | None:
    if not raw.startswith("ma3v4_"):
        return None
    key_hash = hash_token(raw)
    resolved = V4ApiKeyRepository().get_by_hash(key_hash)
    if resolved is None:
        return None
    info, principal = resolved
    if info.revoked_at:
        return None
    if info.expires_at:
        if _session_expired(info.expires_at):
            return None
    V4ApiKeyRepository().touch_last_used(info.key_id, utc_now_iso())
    grants = {g.library_id: g.role for g in ApiKeyGrantRepository().list_by_key(info.key_id)}
    if not grants:
        return None
    return ResolvedPrincipal(
        principal_id=principal.principal_id,
        kind=principal.kind,
        display_name=principal.display_name,
        via="api_key",
        is_admin_bypass=False,
        api_key_id=info.key_id,
        api_key_grants=grants,
        label=info.label,
    )


def resolve_principal_v4(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> ResolvedPrincipal:
    raw = _extract_raw(x_api_key, authorization)
    if raw:
        if _is_admin_key(raw):
            metrics.record_auth_resolve("admin_key", "admin")
            return _ADMIN_PRINCIPAL
        principal = _principal_from_api_key(raw)
        if principal is not None:
            metrics.record_auth_resolve(principal.via, principal.kind)
            return principal
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_id = _session_from_request(request)
    if session_id:
        principal = _principal_from_session(session_id)
        if principal is not None:
            metrics.record_auth_resolve(principal.via, principal.kind)
            return principal

    metrics.record_auth_resolve("anonymous", "anonymous")
    return _ANONYMOUS_PRINCIPAL


def resolve_from_raw_only_v4(raw: str | None) -> ResolvedPrincipal:
    if not raw:
        metrics.record_auth_resolve("anonymous", "anonymous")
        return _ANONYMOUS_PRINCIPAL
    if _is_admin_key(raw):
        metrics.record_auth_resolve("admin_key", "admin")
        return _ADMIN_PRINCIPAL
    principal = _principal_from_api_key(raw)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    metrics.record_auth_resolve(principal.via, principal.kind)
    return principal


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(key=settings.session_cookie)
