from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import authing_client
from app.auth.session import (
    clear_session_cookie,
    pop_oauth_next,
    resolve_session_user,
    set_oauth_state_cookies,
    set_session_cookie,
    validate_oauth_state,
)
from app.core.config import settings
from app.services.principal_service import ensure_user_principal

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_authing() -> None:
    if not settings.authing_configured:
        raise HTTPException(status_code=503, detail="Authing auth is not configured")


@router.get("/login")
def auth_login(
    request: Request,
    next: str = Query("/ui/observatory/", alias="next"),
) -> Response:
    _require_authing()
    if not next.startswith("/"):
        next = "/ui/observatory/"
    state = authing_client.new_oauth_state()
    authorize_url = authing_client.build_authorize_url(state=state)
    response = RedirectResponse(authorize_url, status_code=302)
    set_oauth_state_cookies(response, request, state=state, next_path=next)
    return response


@router.get("/callback")
def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    _require_authing()
    if error:
        raise HTTPException(status_code=400, detail=f"authing error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="missing authorization code")
    if not validate_oauth_state(request, state):
        raise HTTPException(status_code=400, detail="invalid oauth state")

    tokens = authing_client.exchange_code(code)
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="authing token response missing access_token")

    user = authing_client.resolve_user(access_token)
    ensure_user_principal(user)

    next_path = pop_oauth_next(request)
    response = RedirectResponse(next_path, status_code=302)
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
    post_logout = (settings.public_base_url or str(request.base_url).rstrip("/")) + "/ui/observatory/"
    logout_url = authing_client.build_logout_url(post_logout_redirect=post_logout)
    response = RedirectResponse(logout_url, status_code=302)
    clear_session_cookie(response, request)
    return response
