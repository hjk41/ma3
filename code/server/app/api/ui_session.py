"""Shared SSR session helpers for UI routes."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.auth.session import SessionUser, resolve_session_user
from app.core.config import settings
from app.services.principal_service import display_name_setup_required


def ui_user_line(user: SessionUser | None) -> str:
    if user is None:
        return ""
    admin = " · 管理员" if user.is_admin else ""
    return f"{user.display_name}{admin}"


def resolve_ui_user(request: Request) -> SessionUser | None:
    if not settings.portal_auth_enabled:
        return None
    return resolve_session_user(request)


def require_ui_user(request: Request) -> SessionUser | None:
    """Redirect to login when portal auth is on and session missing."""
    user = resolve_ui_user(request)
    if settings.portal_auth_enabled and user is None:
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


def oidc_required_ui_response(request: Request) -> HTMLResponse:
    """Friendly HTML when portal pages need auth but neither OIDC nor local auth is on."""
    from app.api.ui_i18n import html_response, ui_locale
    from app.api.ui_theme import esc, render_page

    locale, t = ui_locale(request)
    base = str(request.base_url).rstrip("/")
    if settings.bootstrap_selfhost:
        title = t("portal.oidc_required.bootstrap_title")
        message = t("portal.oidc_required.bootstrap_body")
        primary_href = f"{base}/mcp/info"
        primary_label = t("portal.oidc_required.cta_mcp")
        secondary_href = f"{base}/client/agent-onboarding.md"
        secondary_label = t("portal.oidc_required.cta_docs")
    else:
        title = t("portal.oidc_required.title")
        message = t("portal.oidc_required.body")
        primary_href = f"{base}/ui/home/"
        primary_label = t("portal.oidc_required.cta_home")
        secondary_href = f"{base}/client/agent-onboarding.md"
        secondary_label = t("portal.oidc_required.cta_docs")

    body = f"""
  <div class="page-403">
    <h1>{esc(title)}</h1>
    <p>{esc(message)}</p>
    <p>
      <a class="btn primary" href="{esc(primary_href)}">{esc(primary_label)}</a>
      <a class="btn subtle" href="{esc(secondary_href)}">{esc(secondary_label)}</a>
      <a class="btn" href="{esc(base)}/ui/home/">{esc(t("portal.oidc_required.cta_home"))}</a>
    </p>
  </div>"""
    return html_response(
        request,
        render_page(
            title=title,
            base=base,
            active_nav="",
            body=body,
            show_minimal_header=True,
            brand_href=f"{base}/ui/home/",
            locale=locale,
            request=request,
        ),
        status_code=503,
    )


def require_authed_ui_user(request: Request, *, require_setup: bool = True) -> SessionUser | Response:
    if not settings.portal_auth_enabled:
        return oidc_required_ui_response(request)
    user = resolve_ui_user(request)
    if user is None:
        return login_redirect(request)
    if require_setup:
        setup_redirect = redirect_if_setup_required(request, user)
        if setup_redirect is not None:
            return setup_redirect
    return user
