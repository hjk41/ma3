from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api.ui_i18n import html_response, resolve_locale, tr, ui_locale
from app.api.ui_session import oidc_required_ui_response
from app.api.ui_theme import esc, render_page, render_password_input
from app.auth import authing_client
from app.auth.session import (
    clear_session_cookie,
    get_access_token,
    pop_oauth_next,
    resolve_session_user,
    set_oauth_state_cookies,
    set_session_cookie,
    validate_oauth_state,
)
from app.core.config import settings
from app.core.security import assert_same_origin as _assert_same_origin
from app.services import local_auth_service
from app.services import setup_service
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import display_name_setup_required, ensure_user_principal
from app.storage import db as storage_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_authing() -> None:
    if not settings.authing_configured:
        raise HTTPException(status_code=503, detail="Authing auth is not configured")


def _auth_unavailable_html(request: Request) -> Response | None:
    """When neither OIDC nor local auth is available."""
    if settings.portal_auth_enabled:
        return None
    return oidc_required_ui_response(request)


def _normalize_next_path(next_path: str) -> str:
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/ui/me/"
    return next_path


def _auth_error_page(request: Request, next_path: str, message: str, *, status_code: int = 400) -> HTMLResponse:
    locale = resolve_locale(request)
    body = f"""
  <div class="card" style="margin-top:24px;">
    <div class="card-body">
      <h1>{esc(tr(locale, "auth.error.title"))}</h1>
      <p>{esc(message)}</p>
      <p><a class="btn primary" href="/auth/login?next={esc(next_path)}">{esc(tr(locale, "auth.error.retry"))}</a></p>
    </div>
  </div>"""
    return html_response(
        request,
        render_page(
            title=tr(locale, "auth.error.title"),
            base=str(request.base_url).rstrip("/"),
            active_nav="",
            body=body,
            show_minimal_header=True,
            locale=locale,
            request=request,
        ),
        status_code=status_code,
    )


def _start_authing_login(request: Request, next_path: str) -> Response:
    state = authing_client.new_oauth_state()
    authorize_url = authing_client.build_authorize_url(state=state)
    response = RedirectResponse(authorize_url, status_code=302)
    set_oauth_state_cookies(response, request, state=state, next_path=next_path)
    return response


def _password_fields_html(t, *, register: bool) -> str:
    show = t("auth.local.show_password")
    hide = t("auth.local.hide_password")
    fields = render_password_input(
        name="password",
        label=t("auth.local.password"),
        autocomplete="new-password" if register else "current-password",
        show_label=show,
        hide_label=hide,
    )
    if register:
        fields += render_password_input(
            name="password_confirm",
            label=t("auth.local.password_confirm"),
            autocomplete="new-password",
            show_label=show,
            hide_label=hide,
        )
    return fields


def _local_auth_form_page(
    request: Request,
    *,
    mode: str,
    next_path: str,
    error: str = "",
    invite_token: str = "",
    invite_banner: str = "",
) -> HTMLResponse:
    locale, t = ui_locale(request)
    base = str(request.base_url).rstrip("/")
    is_register = mode == "register"
    needs_owner = is_register and setup_service.setup_needs_owner()
    reg_open = local_auth_service.is_registration_open()
    invite_ok = bool(invite_token) and is_register and not needs_owner
    allow_register_form = (not is_register) or needs_owner or reg_open or invite_ok
    if needs_owner:
        title = t("setup.admin_title")
        subtitle = t("setup.admin_lead")
        submit = t("setup.admin_submit")
    elif is_register and not reg_open and not invite_ok:
        title = t("auth.local.register_title")
        subtitle = t("auth.local.registration_closed")
        submit = title
    elif is_register and invite_ok:
        title = t("auth.local.register_title")
        subtitle = invite_banner or t("auth.local.invite_subtitle")
        submit = title
    elif is_register:
        title = t("auth.local.register_title")
        subtitle = t("auth.local.subtitle_member")
        submit = title
    else:
        title = t("auth.local.login_title")
        subtitle = t("auth.local.subtitle_login")
        submit = title
    action = "/auth/register" if is_register else "/auth/login"
    switch = (
        f'<p class="card-muted">{esc(t("auth.local.have_account"))} '
        f'<a href="/auth/login?next={esc(next_path)}">{esc(t("auth.local.login_link"))}</a></p>'
        if is_register and not needs_owner and (reg_open or invite_ok)
        else (
            ""
            if needs_owner or (is_register and not allow_register_form)
            else f'<p class="card-muted">{esc(t("auth.local.need_account"))} '
            f'<a href="/auth/register?next={esc(next_path)}">{esc(t("auth.local.register_link"))}</a></p>'
        )
    )
    err = f'<div class="alert error">{esc(error)}</div>' if error else ""
    form_body = ""
    if is_register and not allow_register_form:
        form_body = f"""
      <p class="card-muted">{esc(t("auth.local.registration_closed_help"))}</p>
      <p><a class="btn primary" href="/auth/login?next={esc(next_path)}">{esc(t("auth.local.login_link"))}</a></p>
"""
    else:
        display_field = ""
        if is_register:
            display_field = f"""
        <label style="display:block;margin:12px 0 4px;">{esc(t("auth.local.display_name"))}</label>
        <input name="display_name" type="text" maxlength="32" placeholder="{esc(t("auth.local.display_name_hint"))}" style="width:100%;max-width:360px;" />
        """
        invite_hidden = ""
        if is_register and invite_token:
            invite_hidden = f'<input type="hidden" name="invite" value="{esc(invite_token)}" />'
        pw_fields = _password_fields_html(t, register=is_register)
        mismatch = esc(t("auth.local.password_mismatch"))
        onsubmit = ' onsubmit="return ma3CheckPasswordConfirm(this)"' if is_register else ""
        form_attrs = f' method="post" action="{esc(action)}"{onsubmit}'
        if is_register:
            form_attrs += f' data-password-mismatch="{mismatch}"'
        form_body = f"""
      <form{form_attrs}>
        <input type="hidden" name="next" value="{esc(next_path)}" />
        {invite_hidden}
        <label style="display:block;margin:12px 0 4px;">{esc(t("auth.local.username"))}</label>
        <input name="username" type="text" required autocomplete="username" style="width:100%;max-width:360px;" />
        {pw_fields}
        {display_field}
        <div class="actions" style="margin-top:16px;">
          <button type="submit" class="btn primary">{esc(submit)}</button>
        </div>
      </form>
      {switch}
"""
    body = f"""
  <div class="card" style="margin-top:24px;max-width:480px;">
    <div class="card-header"><h1 style="margin:0;font-size:20px;">{esc(title)}</h1></div>
    <div class="card-body">
      <p class="card-muted">{esc(subtitle)}</p>
      {err}
      {form_body}
    </div>
  </div>"""
    return html_response(
        request,
        render_page(
            title=title,
            base=base,
            active_nav="",
            body=body,
            show_minimal_header=True,
            show_login=not needs_owner,
            locale=locale,
            request=request,
        ),
    )


@router.get("/login")
def auth_login(
    request: Request,
    next: str = Query("/ui/me/", alias="next"),
) -> Response:
    denied = _auth_unavailable_html(request)
    if denied is not None:
        return denied
    next_path = _normalize_next_path(next)
    if settings.authing_configured:
        return _start_authing_login(request, next_path)
    return _local_auth_form_page(request, mode="login", next_path=next_path)


@router.get("/login/start")
def auth_login_start(
    request: Request,
    next: str = Query("/ui/me/", alias="next"),
) -> Response:
    return auth_login(request, next=next)


@router.post("/login")
async def auth_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/ui/me/"),
) -> Response:
    denied = _auth_unavailable_html(request)
    if denied is not None:
        return denied
    if settings.authing_configured:
        return RedirectResponse(f"/auth/login?next={quote(_normalize_next_path(next), safe='')}", status_code=303)
    _assert_same_origin(request)
    next_path = _normalize_next_path(next)
    try:
        account = local_auth_service.authenticate_local_user(username=username, password=password)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _local_auth_form_page(request, mode="login", next_path=next_path, error=detail)
    token = local_auth_service.issue_local_session_token(account)
    response = RedirectResponse(next_path, status_code=303)
    set_session_cookie(response, request, token)
    return response


@router.get("/register")
def auth_register_get(
    request: Request,
    next: str = Query("/ui/me/", alias="next"),
    invite: str = Query("", alias="invite"),
) -> Response:
    denied = _auth_unavailable_html(request)
    if denied is not None:
        return denied
    if settings.authing_configured:
        return RedirectResponse(f"/auth/login?next={quote(_normalize_next_path(next), safe='')}", status_code=302)
    if not settings.local_auth_enabled:
        return oidc_required_ui_response(request)
    if setup_service.setup_needs_owner():
        return RedirectResponse("/ui/setup/", status_code=302)
    invite_token = (invite or "").strip()
    invite_banner = ""
    if invite_token:
        from app.services import org_invite_service

        try:
            preview = org_invite_service.preview_invite(invite_token)
            org_name = preview.get("org_name") or preview.get("org_id")
            invite_banner = f"邀请加入组织：{org_name}（角色 {preview.get('role')}）"
            alias = preview.get("member_alias")
            if alias:
                invite_banner += f"；组织内别名「{alias}」"
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return _local_auth_form_page(
                request,
                mode="register",
                next_path=_normalize_next_path(next),
                error=detail,
            )
    return _local_auth_form_page(
        request,
        mode="register",
        next_path=_normalize_next_path(next),
        invite_token=invite_token,
        invite_banner=invite_banner,
    )


@router.post("/register")
async def auth_register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(""),
    display_name: str = Form(""),
    next: str = Form("/ui/me/"),
    invite: str = Form(""),
) -> Response:
    denied = _auth_unavailable_html(request)
    if denied is not None:
        return denied
    if not settings.local_auth_enabled:
        return oidc_required_ui_response(request)
    _assert_same_origin(request)
    next_path = _normalize_next_path(next)
    invite_token = (invite or "").strip()
    was_first = setup_service.setup_needs_owner()
    locale, t = ui_locale(request)
    if password != password_confirm:
        detail = t("auth.local.password_mismatch")
        if was_first:
            from app.api.routes_setup import _render_needs_owner

            return _render_needs_owner(request, error=detail)
        return _local_auth_form_page(
            request,
            mode="register",
            next_path=next_path,
            error=detail,
            invite_token=invite_token,
        )
    try:
        account = local_auth_service.register_local_user(
            username=username,
            password=password,
            display_name=display_name or None,
            invite_token=invite_token or None,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        if was_first:
            from app.api.routes_setup import _render_needs_owner

            return _render_needs_owner(request, error=detail)
        return _local_auth_form_page(
            request,
            mode="register",
            next_path=next_path,
            error=detail,
            invite_token=invite_token,
        )
    token = local_auth_service.issue_local_session_token(account)
    if was_first and next_path in {"/ui/me/", "/ui/home/", "/"}:
        next_path = "/ui/setup/"
    elif account.get("org_membership") and next_path in {"/ui/me/", "/ui/home/", "/"}:
        org_id = account["org_membership"].get("org_id")
        if org_id:
            next_path = f"/ui/orgs/{org_id}/"
    response = RedirectResponse(next_path, status_code=303)
    set_session_cookie(response, request, token)
    return response


@router.get("/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if not settings.authing_configured:
        return oidc_required_ui_response(request)
    next_path = pop_oauth_next(request)
    if error:
        logger.warning("authing callback error=%s", error)
        return _auth_error_page(request, next_path, f"Authing 登录失败：{error}")
    if not code:
        return _auth_error_page(request, next_path, tr(resolve_locale(request), "auth.error.missing_code"))
    if not validate_oauth_state(request, state):
        logger.warning("authing callback invalid oauth state got=%s", state)
        return _auth_error_page(request, next_path, "登录状态已过期，请重新登录")

    try:
        tokens = authing_client.exchange_code(code)
    except httpx.HTTPError as exc:
        logger.exception("authing token exchange failed")
        return _auth_error_page(request, next_path, f"Authing 令牌交换失败：{exc}", status_code=502)

    access_token = tokens.get("access_token")
    if not access_token:
        return _auth_error_page(request, next_path, "Authing 未返回 access_token", status_code=502)

    try:
        user = authing_client.resolve_user(access_token)
        principal = ensure_user_principal(user)
        try:
            ensure_personal_library(principal["principal_id"], str(principal["display_name"]))
        except Exception:
            logger.exception(
                "ensure_personal_library failed during auth callback for %s",
                principal.get("principal_id"),
            )
    except Exception as exc:
        logger.exception("authing user resolution failed")
        return _auth_error_page(request, next_path, f"用户信息解析失败：{exc}", status_code=502)

    if display_name_setup_required(principal["principal_id"]):
        setup_next = next_path if not next_path.startswith("/ui/me/setup") else "/ui/me/"
        redirect_target = f"/ui/me/setup/?next={quote(setup_next, safe='')}"
    else:
        redirect_target = next_path
    response = RedirectResponse(redirect_target, status_code=302)
    set_session_cookie(response, request, access_token)
    response.delete_cookie(settings.auth_oauth_state_cookie, path="/")
    response.delete_cookie("ma3_oauth_next", path="/")
    return response


@router.get("/whoami")
def auth_whoami(request: Request) -> JSONResponse:
    if not settings.portal_auth_enabled:
        raise HTTPException(status_code=503, detail="portal auth is not configured")
    user = resolve_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return JSONResponse(user.to_dict())


@router.get("/account")
def auth_account(request: Request) -> Response:
    if settings.local_auth_enabled:
        return RedirectResponse("/ui/me/settings/", status_code=302)
    if not settings.authing_configured:
        return oidc_required_ui_response(request)
    if resolve_session_user(request) is None:
        return RedirectResponse("/auth/login?next=/auth/account", status_code=302)
    return RedirectResponse(settings.resolve_authing_account_url(), status_code=302)


@router.get("/logout")
@router.post("/logout")
def auth_logout(request: Request) -> Response:
    if not settings.portal_auth_enabled:
        return oidc_required_ui_response(request)
    if settings.local_auth_enabled and not settings.authing_configured:
        response = RedirectResponse("/ui/home/", status_code=302)
        clear_session_cookie(response, request)
        return response
    token = get_access_token(request)
    if token:
        authing_client.invalidate_userinfo_cache(token)
    post_logout = settings.resolve_authing_post_logout_redirect_uri()
    logout_url = authing_client.build_logout_url(post_logout_redirect=post_logout)
    response = RedirectResponse(logout_url, status_code=302)
    clear_session_cookie(response, request)
    return response
