"""Shared SSR session helpers for UI routes."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.auth.session import SessionUser, resolve_session_user
from app.core.config import settings
from app.services.principal_service import display_name_setup_required


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


def redirect_if_setup_required(request: Request, user: SessionUser) -> Response | None:
    if request.url.path.startswith("/ui/me/setup"):
        return None
    if not display_name_setup_required(user.principal_id):
        return None
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(f"/ui/me/setup/?next={quote(next_path, safe='')}", status_code=302)


def require_authed_ui_user(request: Request, *, require_setup: bool = True) -> SessionUser | Response:
    require_authing_for_ui()
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    if require_setup:
        setup_redirect = redirect_if_setup_required(request, user)
        if setup_redirect is not None:
            return setup_redirect
    return user


def require_authing_for_ui() -> None:
    if not settings.authing_configured:
        raise HTTPException(
            status_code=503,
            detail="this page requires Authing login",
        )
