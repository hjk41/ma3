"""Shared SSR session helpers for UI routes."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.auth.session import SessionUser, resolve_session_user
from app.core.config import settings


def ui_user_line(user: SessionUser | None) -> str:
    if user is None:
        return ""
    admin = " · 管理员" if user.is_admin else ""
    return f"{user.display_name}{admin}"


def resolve_ui_user(request: Request) -> SessionUser | None:
    if not settings.authing_configured:
        return None
    return resolve_session_user(request)


def require_ui_user(request: Request) -> SessionUser | None:
    """Redirect to login when Authing is on and session missing."""
    user = resolve_ui_user(request)
    if settings.authing_configured and user is None:
        return None  # caller checks redirect
    return user


def login_redirect(request: Request) -> Response:
    return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=302)


def require_authing_for_ui() -> None:
    if not settings.authing_configured:
        raise HTTPException(
            status_code=503,
            detail="this page requires Authing login",
        )
