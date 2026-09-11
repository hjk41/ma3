"""Canonical public base / MCP resource URL helpers (design/28 U1/U2)."""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from starlette.requests import Request

from app.core.config import settings

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def resolve_public_base_url(request: Request | None = None) -> str:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8000"


def resolve_mcp_resource_url(request: Request | None = None) -> str:
    return f"{resolve_public_base_url(request)}/mcp"


def resolve_oauth_prm_url(request: Request | None = None) -> str:
    return f"{resolve_public_base_url(request)}/.well-known/oauth-protected-resource"


def _replace_hostname(url: str, hostname: str) -> str:
    parts = urlparse(url)
    port = parts.port
    if ":" in hostname and not hostname.startswith("["):
        host_for_netloc = f"[{hostname}]"
    else:
        host_for_netloc = hostname
    netloc = f"{host_for_netloc}:{port}" if port else host_for_netloc
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo = f"{userinfo}:{parts.password}"
        netloc = f"{userinfo}@{netloc}"
    return urlunparse(
        (parts.scheme, netloc, parts.path, parts.params, parts.query, parts.fragment)
    ).rstrip("/")


def localhost_aliases(url: str) -> set[str]:
    """Expand a URL with localhost / 127.0.0.1 / ::1 host aliases (same scheme/port/path)."""
    raw = (url or "").rstrip("/")
    out = {raw}
    host = (urlparse(raw).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        return out
    for alias in ("127.0.0.1", "localhost", "::1"):
        out.add(_replace_hostname(raw, alias))
    return out


def acceptable_mcp_resources(request: Request | None = None) -> set[str]:
    """Resource identifiers this deployment will accept for MCP OAuth tokens."""
    candidates: set[str] = set()
    if settings.public_base_url:
        candidates.add(settings.mcp_resource_url().rstrip("/"))
    if request is not None:
        candidates.add(resolve_mcp_resource_url(request).rstrip("/"))
    if not candidates:
        candidates.add(settings.mcp_resource_url().rstrip("/"))
    expanded: set[str] = set()
    for item in candidates:
        expanded.update(localhost_aliases(item))
    return expanded


def resource_acceptable(resource: str | None, *, request: Request | None = None) -> bool:
    if not resource:
        return False
    return resource.rstrip("/") in acceptable_mcp_resources(request)
