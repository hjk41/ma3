from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api.ui_theme import esc
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
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import display_name_setup_required, ensure_user_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_authing() -> None:
    if not settings.authing_configured:
        raise HTTPException(status_code=503, detail="Authing auth is not configured")


def _normalize_next_path(next_path: str) -> str:
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/ui/me/"
    return next_path


def _auth_error_page(next_path: str, message: str, *, status_code: int = 400) -> HTMLResponse:
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>登录失败 · ma3</title></head>
<body style="font-family:system-ui,sans-serif;margin:2rem;line-height:1.6;">
  <h1>登录失败</h1>
  <p>{esc(message)}</p>
  <p><a href="/auth/login?next={esc(next_path)}">重新登录</a></p>
</body></html>""",
        status_code=status_code,
    )


def _start_authing_login(request: Request, next_path: str) -> Response:
    state = authing_client.new_oauth_state()
    authorize_url = authing_client.build_authorize_url(state=state)
    response = RedirectResponse(authorize_url, status_code=302)
    set_oauth_state_cookies(response, request, state=state, next_path=next_path)
    return response


@router.get("/login")
def auth_login(
    request: Request,
    next: str = Query("/ui/me/", alias="next"),
) -> Response:
    _require_authing()
    return _start_authing_login(request, _normalize_next_path(next))


@router.get("/login/start")
def auth_login_start(
    request: Request,
    next: str = Query("/ui/me/", alias="next"),
) -> Response:
    _require_authing()
    return _start_authing_login(request, _normalize_next_path(next))


@router.get("/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    _require_authing()
    next_path = pop_oauth_next(request)
    if error:
        logger.warning("authing callback error=%s", error)
        return _auth_error_page(next_path, f"Authing 登录失败：{error}")
    if not code:
        return _auth_error_page(next_path, "缺少 authorization code")
    if not validate_oauth_state(request, state):
        logger.warning("authing callback invalid oauth state got=%s", state)
        return _auth_error_page(next_path, "登录状态已过期，请重新登录")

    try:
        tokens = authing_client.exchange_code(code)
    except httpx.HTTPError as exc:
        logger.exception("authing token exchange failed")
        return _auth_error_page(next_path, f"Authing 令牌交换失败：{exc}", status_code=502)

    access_token = tokens.get("access_token")
    if not access_token:
        return _auth_error_page(next_path, "Authing 未返回 access_token", status_code=502)

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
        return _auth_error_page(next_path, f"用户信息解析失败：{exc}", status_code=502)

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
    _require_authing()
    user = resolve_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return JSONResponse(user.to_dict())


@router.get("/account")
def auth_account(request: Request) -> Response:
    _require_authing()
    if resolve_session_user(request) is None:
        return RedirectResponse("/auth/login?next=/auth/account", status_code=302)
    return RedirectResponse(settings.resolve_authing_account_url(), status_code=302)


@router.get("/logout")
@router.post("/logout")
def auth_logout(request: Request) -> Response:
    _require_authing()
    token = get_access_token(request)
    if token:
        authing_client.invalidate_userinfo_cache(token)
    post_logout = settings.resolve_authing_post_logout_redirect_uri()
    logout_url = authing_client.build_logout_url(post_logout_redirect=post_logout)
    response = RedirectResponse(logout_url, status_code=302)
    clear_session_cookie(response, request)
    return response
