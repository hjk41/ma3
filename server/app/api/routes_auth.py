from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.auth import _cookie_domain_for_host, verify_sso_cookie
from app.core.config import settings

router = APIRouter(tags=["auth"])


def _safe_next(req_host: str, raw: str | None) -> str:
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/ui/"
    return raw


@router.get("/auth/login")
async def auth_login(request: Request, next: str = "/ui/"):
    if not settings.auth_verify_url:
        return JSONResponse({"error": "sso_disabled"}, status_code=503)
    callback = f"{request.url.scheme}://{request.url.netloc}/auth/callback"
    return_to = _safe_next(request.url.netloc, next)
    qs = urlencode({"next": f"{callback}?return_to={return_to}"})
    return RedirectResponse(f"{settings.auth_login_url}?{qs}", status_code=302)


@router.get("/auth/callback")
async def auth_callback(
    request: Request,
    gateway_token: str | None = None,
    return_to: str = "/ui/",
):
    safe_return = _safe_next(request.url.netloc, return_to)
    if not gateway_token:
        return RedirectResponse(safe_return, status_code=302)
    verified = verify_sso_cookie(gateway_token)
    if verified is None:
        return RedirectResponse("/auth/login", status_code=302)
    resp = RedirectResponse(safe_return, status_code=302)
    resp.set_cookie(
        key=settings.auth_jwt_cookie,
        value=gateway_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=86400,
        domain=_cookie_domain_for_host(request.url.netloc),
        path="/",
    )
    return resp


@router.get("/auth/logout")
async def auth_logout(request: Request):
    resp = RedirectResponse("/ui/", status_code=302)
    resp.delete_cookie(
        settings.auth_jwt_cookie,
        domain=_cookie_domain_for_host(request.url.netloc),
        path="/",
    )
    return resp
