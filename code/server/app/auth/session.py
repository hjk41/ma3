from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response

from app.auth import authing_client
from app.core.config import settings
from app.services.principal_service import ensure_user_principal


@dataclass(slots=True)
class SessionUser:
    principal_id: str
    sub: str
    display_name: str
    email: str | None
    phone: str | None
    is_admin: bool
    via: str = "authing"

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "sub": self.sub,
            "display_name": self.display_name,
            "email": self.email,
            "phone": self.phone,
            "is_admin": self.is_admin,
            "via": self.via,
        }


def _cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https"


def set_session_cookie(response: Response, request: Request, access_token: str, *, max_age: int = 7 * 24 * 3600) -> None:
    response.set_cookie(
        settings.auth_session_cookie,
        access_token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        max_age=max_age,
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        settings.auth_session_cookie,
        path="/",
        secure=_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )


def set_oauth_state_cookies(
    response: Response,
    request: Request,
    *,
    state: str,
    next_path: str,
) -> None:
    secure = _cookie_secure(request)
    response.set_cookie(
        settings.auth_oauth_state_cookie,
        state,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=600,
        path="/",
    )
    response.set_cookie(
        "ma3_oauth_next",
        next_path,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=600,
        path="/",
    )


def pop_oauth_next(request: Request) -> str:
    raw = (request.cookies.get("ma3_oauth_next") or "/ui/observatory/").strip().strip('"')
    if not raw.startswith("/") or raw.startswith("//"):
        return "/ui/observatory/"
    return raw


def validate_oauth_state(request: Request, state: str | None) -> bool:
    if not state:
        return False
    expected = request.cookies.get(settings.auth_oauth_state_cookie)
    return bool(expected and expected == state)


def get_access_token(request: Request) -> str | None:
    token = request.cookies.get(settings.auth_session_cookie)
    return token or None


def resolve_session_user(request: Request) -> SessionUser | None:
    token = get_access_token(request)
    if not token:
        return None

    if settings.local_auth_enabled and token.startswith("local.v1."):
        from app.services.local_auth_service import parse_local_session_token

        local = parse_local_session_token(token)
        if not local:
            return None
        return SessionUser(
            principal_id=local["principal_id"],
            sub=local["sub"],
            display_name=local["display_name"],
            email=None,
            phone=None,
            is_admin=bool(local["is_admin"]),
            via="local",
        )

    if not settings.authing_configured:
        return None
    try:
        authing_user = authing_client.resolve_user(token)
    except Exception:
        return None
    principal = ensure_user_principal(authing_user)
    return SessionUser(
        principal_id=principal["principal_id"],
        sub=authing_user.sub,
        display_name=principal["display_name"],
        email=authing_user.email,
        phone=authing_user.phone,
        is_admin=authing_user.is_admin,
        via="authing",
    )
