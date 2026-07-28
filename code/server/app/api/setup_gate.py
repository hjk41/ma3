"""HTTP gate: force /ui/setup/ when local-auth self-host has no owner yet."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.config import settings


def _path_allowed_during_needs_owner(path: str) -> bool:
    """Paths that must stay reachable before the first admin exists."""
    if path == "/ui/setup" or path.startswith("/ui/setup/"):
        return True
    # Public marketing landing should stay reachable during day-0.
    if path == "/ui/home" or path.startswith("/ui/home/"):
        return True
    # Setup form POSTs here; GET may still render or redirect in the handler.
    if path == "/auth/register" or path.startswith("/auth/register/"):
        return True
    if path == "/auth/login" or path.startswith("/auth/login/"):
        return True
    if path in {"/healthz", "/openapi.json", "/favicon.ico"}:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    # Agent / API rails (not product HTML pages).
    if path == "/mcp" or path.startswith("/mcp/"):
        return True
    if path.startswith("/api/"):
        return True
    if path.startswith("/client/"):
        return True
    # Machine-readable observatory snapshot used by smoke / ops checks.
    if path == "/ui/observatory/stats.json":
        return True
    return False


class NeedsOwnerSetupRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.local_auth_enabled:
            return await call_next(request)
        path = request.url.path or "/"
        if _path_allowed_during_needs_owner(path):
            return await call_next(request)
        try:
            from app.services import setup_service

            if not setup_service.setup_needs_owner():
                return await call_next(request)
        except Exception:
            return await call_next(request)
        if request.method in {"GET", "HEAD"}:
            return RedirectResponse("/ui/setup/", status_code=302)
        # Block stray browser POSTs until an owner exists (register is allowlisted).
        if request.method == "POST":
            return RedirectResponse("/ui/setup/", status_code=303)
        return await call_next(request)
