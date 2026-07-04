from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

_discovery_cache: dict[str, Any] | None = None
_userinfo_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@dataclass(slots=True)
class AuthingUser:
    sub: str
    display_name: str
    email: str | None = None
    phone: str | None = None
    username: str | None = None
    photo: str | None = None
    is_admin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "display_name": self.display_name,
            "email": self.email,
            "phone": self.phone,
            "username": self.username,
            "photo": self.photo,
            "is_admin": self.is_admin,
        }


def _issuer() -> str:
    return settings.authing_issuer_base()


def _discovery() -> dict[str, Any]:
    global _discovery_cache
    if _discovery_cache is not None:
        return _discovery_cache
    url = f"{_issuer()}/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    _discovery_cache = resp.json()
    return _discovery_cache


def build_authorize_url(*, state: str, redirect_uri: str | None = None) -> str:
    discovery = _discovery()
    redirect = redirect_uri or settings.resolve_authing_redirect_uri()
    params = {
        "client_id": settings.authing_app_id,
        "response_type": "code",
        "scope": "openid profile email phone",
        "redirect_uri": redirect,
        "state": state,
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(params)}"


def exchange_code(code: str, *, redirect_uri: str | None = None) -> dict[str, Any]:
    discovery = _discovery()
    redirect = redirect_uri or settings.resolve_authing_redirect_uri()
    resp = httpx.post(
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.authing_app_id,
            "client_secret": settings.authing_app_secret,
            "redirect_uri": redirect,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    now = time.time()
    cached = _userinfo_cache.get(access_token)
    if cached and cached[0] > now:
        return cached[1]

    discovery = _discovery()
    endpoint = discovery.get("userinfo_endpoint") or f"{_issuer()}/me"
    resp = httpx.get(
        endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=settings.auth_userinfo_cache_ttl_seconds,
    )
    resp.raise_for_status()
    body = resp.json()
    ttl = max(1, settings.auth_userinfo_cache_ttl_seconds)
    _userinfo_cache[access_token] = (now + ttl, body)
    if len(_userinfo_cache) > 2048:
        _userinfo_cache.clear()
    return body


def invalidate_userinfo_cache(access_token: str) -> None:
    _userinfo_cache.pop(access_token, None)


def build_logout_url(*, post_logout_redirect: str) -> str:
    discovery = _discovery()
    end_session = discovery.get("end_session_endpoint") or f"{_issuer()}/session/end"
    params = {
        "client_id": settings.authing_app_id,
        "post_logout_redirect_uri": post_logout_redirect,
    }
    return f"{end_session}?{urlencode(params)}"


def _display_name_from_claims(claims: dict[str, Any]) -> str:
    for key in ("nickname", "name", "username", "phone", "email", "sub"):
        value = claims.get(key)
        if value:
            return str(value)
    return "ma3 user"


def _is_admin_user(claims: dict[str, Any]) -> bool:
    if not settings.auth_admin_users:
        return False
    candidates = {
        str(claims.get("sub") or ""),
        str(claims.get("email") or ""),
        str(claims.get("phone") or ""),
        str(claims.get("phone_number") or ""),
        str(claims.get("username") or ""),
    }
    return any(item in settings.auth_admin_users for item in candidates if item)


def user_from_claims(claims: dict[str, Any]) -> AuthingUser:
    sub = str(claims.get("sub") or claims.get("userId") or claims.get("id") or "")
    if not sub:
        raise ValueError("missing subject in userinfo")
    phone = claims.get("phone") or claims.get("phone_number")
    return AuthingUser(
        sub=sub,
        display_name=_display_name_from_claims(claims),
        email=str(claims["email"]) if claims.get("email") else None,
        phone=str(phone) if phone else None,
        username=str(claims["username"]) if claims.get("username") else None,
        photo=str(claims["picture"]) if claims.get("picture") else None,
        is_admin=_is_admin_user(claims),
    )


def resolve_user(access_token: str) -> AuthingUser:
    claims = fetch_userinfo(access_token)
    return user_from_claims(claims)


def new_oauth_state() -> str:
    return secrets.token_urlsafe(24)
