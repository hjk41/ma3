"""MCP Authorization Spec discovery + OAuth AS endpoints (ADR-016)."""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.session import resolve_session_user
from app.core.config import settings
from app.core.public_url import resolve_mcp_resource_url, resolve_public_base_url
from app.services import mcp_oauth_as_service
from app.services.principal_service import display_name_setup_required

router = APIRouter(tags=["mcp-oauth"])


def _public_base(request: Request) -> str:
    return resolve_public_base_url(request)


def _authorization_server_metadata(base: str) -> dict[str, Any]:
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
        "resource_indicators_supported": True,
    }


def _protected_resource_metadata(base: str) -> dict[str, Any]:
    resource = f"{base}/mcp"
    return {
        "resource": resource,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    }


def _login_next_for_authorize(request: Request) -> str:
    query = request.url.query
    path = "/oauth/authorize"
    return f"{path}?{query}" if query else path


def _append_query(url: str, **params: str) -> str:
    parts = urlsplit(url)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing.update({k: v for k, v in params.items() if v is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment))


def _oauth_error_redirect(redirect_uri: str, *, error: str, state: str | None, description: str) -> RedirectResponse:
    return RedirectResponse(
        _append_query(redirect_uri, error=error, error_description=description, **({"state": state} if state else {})),
        status_code=302,
    )


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def oauth_protected_resource_metadata(request: Request) -> dict[str, Any]:
    return _protected_resource_metadata(_public_base(request))


@router.get("/.well-known/oauth-authorization-server")
def oauth_authorization_server_metadata(request: Request) -> dict[str, Any]:
    return _authorization_server_metadata(_public_base(request))


@router.get("/oauth/authorize")
def oauth_authorize(
    request: Request,
    response_type: str = Query(default=""),
    client_id: str = Query(default=""),
    redirect_uri: str = Query(default=""),
    code_challenge: str = Query(default=""),
    code_challenge_method: str = Query(default="S256"),
    resource: str | None = Query(default=None),
    scope: str = Query(default=""),
    state: str | None = Query(default=None),
) -> RedirectResponse:
    if not settings.portal_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail="MCP OAuth requires portal auth (OIDC or MA3_LOCAL_AUTH)",
        )
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported response_type")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id required")
    if not redirect_uri or not mcp_oauth_as_service.redirect_uri_allowed(redirect_uri):
        raise HTTPException(status_code=400, detail="redirect_uri not allowed")
    if code_challenge_method.upper() != "S256":
        return _oauth_error_redirect(
            redirect_uri,
            error="invalid_request",
            state=state,
            description="only S256 PKCE is supported",
        )
    if not code_challenge or not mcp_oauth_as_service.validate_code_challenge(code_challenge):
        return _oauth_error_redirect(
            redirect_uri,
            error="invalid_request",
            state=state,
            description="code_challenge required (S256, 43 chars)",
        )
    expected_resource = resolve_mcp_resource_url(request)
    if not mcp_oauth_as_service.resource_matches(resource, expected=expected_resource):
        return _oauth_error_redirect(
            redirect_uri,
            error="invalid_target",
            state=state,
            description="resource must equal the MCP resource URL",
        )

    user = resolve_session_user(request)
    if user is None:
        next_path = _login_next_for_authorize(request)
        return RedirectResponse(f"/auth/login?next={quote(next_path, safe='')}", status_code=302)

    if display_name_setup_required(user.principal_id):
        next_path = _login_next_for_authorize(request)
        return RedirectResponse(f"/ui/me/setup/?next={quote(next_path, safe='')}", status_code=302)

    try:
        issued = mcp_oauth_as_service.issue_authorization_code(
            principal_id=user.principal_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            resource=mcp_oauth_as_service.normalize_resource(resource, fallback=expected_resource),
            scope=scope or "mcp",
            code_challenge_method="S256",
        )
    except ValueError as exc:
        return _oauth_error_redirect(
            redirect_uri,
            error="invalid_request",
            state=state,
            description=str(exc),
        )

    return RedirectResponse(
        _append_query(redirect_uri, code=issued.code, **({"state": state} if state else {})),
        status_code=302,
    )


@router.post("/oauth/token")
async def oauth_token(
    request: Request,
    grant_type: str | None = Form(default=None),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    resource: str | None = Form(default=None),
) -> JSONResponse:
    # Support application/json clients as well as form-urlencoded.
    if grant_type is None:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            grant_type = body.get("grant_type")
            code = body.get("code")
            redirect_uri = body.get("redirect_uri")
            client_id = body.get("client_id")
            code_verifier = body.get("code_verifier")
            resource = body.get("resource")

    if grant_type != "authorization_code":
        return JSONResponse(
            {"error": "unsupported_grant_type", "error_description": "only authorization_code is supported"},
            status_code=400,
        )
    if not code or not redirect_uri or not client_id or not code_verifier:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "code, redirect_uri, client_id, and code_verifier required"},
            status_code=400,
        )
    try:
        issued = mcp_oauth_as_service.exchange_authorization_code(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            resource=resource,
            expected_resource=resolve_mcp_resource_url(request),
            request=request,
        )
    except ValueError as exc:
        err = str(exc)
        status = 400
        return JSONResponse(
            {"error": err if err in {"invalid_grant", "invalid_target"} else "invalid_grant", "error_description": err},
            status_code=status,
        )

    return JSONResponse(
        {
            "access_token": issued.access_token,
            "token_type": issued.token_type,
            "expires_in": issued.expires_in,
            "scope": issued.scope or "mcp",
            "resource": issued.resource,
        }
    )
