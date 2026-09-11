"""MCP Authorization Spec AS helpers: auth codes, PKCE, redirect allowlist (ADR-016)."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.core.config import settings
from app.services import mcp_oauth_token_service
from app.storage import db

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})
_CUSTOM_SCHEMES = frozenset({"cursor", "vscode", "vscode-insiders"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def hash_code(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def pkce_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def normalize_resource(resource: str | None, *, fallback: str | None = None) -> str:
    if not resource:
        return (fallback or settings.mcp_resource_url()).rstrip("/")
    return resource.rstrip("/")


def validate_code_verifier(code_verifier: str) -> bool:
    """RFC 7636: 43–128 unreserved characters."""
    return bool(re.fullmatch(r"[A-Za-z0-9\-._~]{43,128}", code_verifier or ""))


def validate_code_challenge(code_challenge: str) -> bool:
    """S256 challenge is base64url(SHA-256) without padding → 43 chars."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", code_challenge or ""))


def resource_matches(resource: str | None, *, expected: str | None = None, request=None) -> bool:
    from app.core.public_url import localhost_aliases, resolve_mcp_resource_url

    target = normalize_resource(resource, fallback=expected)
    if expected:
        return target in localhost_aliases(expected.rstrip("/"))
    if request is not None:
        return target in localhost_aliases(resolve_mcp_resource_url(request))
    return target in localhost_aliases(settings.mcp_resource_url())


def redirect_uri_allowed(redirect_uri: str) -> bool:
    raw = (redirect_uri or "").strip()
    if not raw:
        return False
    for allowed in settings.mcp_oauth_redirect_uri_allowlist:
        if raw == allowed:
            return True
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in _CUSTOM_SCHEMES and parsed.path:
        return True
    if scheme in {"http", "https"}:
        host = (parsed.hostname or "").lower()
        if host in _LOCAL_HOSTS:
            return True
    return False


@dataclass(slots=True)
class IssuedAuthCode:
    code: str
    code_id: str
    expires_at: str


def issue_authorization_code(
    *,
    principal_id: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    resource: str,
    scope: str = "",
    code_challenge_method: str = "S256",
    ttl_sec: int | None = None,
) -> IssuedAuthCode:
    if code_challenge_method.upper() != "S256":
        raise ValueError("only S256 code_challenge_method is supported")
    if not validate_code_challenge(code_challenge):
        raise ValueError("invalid code_challenge")
    ttl = int(ttl_sec if ttl_sec is not None else settings.mcp_oauth_auth_code_ttl_sec)
    ttl = max(60, ttl)
    now = _utcnow()
    expires = now + timedelta(seconds=ttl)
    plaintext = secrets.token_urlsafe(32)
    code_id = db.new_id("moc")
    expires_at = expires.isoformat()
    db.insert_mcp_oauth_auth_code(
        code_id=code_id,
        code_hash=hash_code(plaintext),
        principal_id=principal_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        resource=resource,
        expires_at=expires_at,
        scope=scope,
        code_challenge_method="S256",
        created_at=now.isoformat(),
    )
    return IssuedAuthCode(code=plaintext, code_id=code_id, expires_at=expires_at)


def exchange_authorization_code(
    *,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    resource: str | None = None,
    expected_resource: str | None = None,
    request=None,
) -> mcp_oauth_token_service.IssuedMcpToken:
    from app.core.public_url import acceptable_mcp_resources, localhost_aliases, resolve_mcp_resource_url

    row = db.get_mcp_oauth_auth_code_by_hash(hash_code(code))
    if row is None:
        raise ValueError("invalid_grant")
    if row.get("consumed_at"):
        raise ValueError("invalid_grant")
    expires = _parse_iso(str(row.get("expires_at") or ""))
    if expires is None or expires <= _utcnow():
        raise ValueError("invalid_grant")
    if str(row.get("client_id") or "") != client_id:
        raise ValueError("invalid_grant")
    if str(row.get("redirect_uri") or "") != redirect_uri:
        raise ValueError("invalid_grant")
    if not validate_code_verifier(code_verifier):
        raise ValueError("invalid_grant")
    challenge = str(row.get("code_challenge") or "")
    if pkce_s256_challenge(code_verifier) != challenge:
        raise ValueError("invalid_grant")

    bound_resource = str(row.get("resource") or "").rstrip("/")
    canonical = (expected_resource or resolve_mcp_resource_url(request)).rstrip("/")
    acceptable = acceptable_mcp_resources(request)
    if expected_resource:
        acceptable = acceptable | localhost_aliases(expected_resource.rstrip("/"))

    # Bound resource (from authorize) must be acceptable for this token request.
    if bound_resource not in acceptable and bound_resource not in localhost_aliases(canonical):
        raise ValueError("invalid_target")

    # Client-supplied resource must match bound + this request's canonical resource.
    if not resource:
        raise ValueError("invalid_target")
    presented = resource.rstrip("/")
    if presented not in localhost_aliases(bound_resource):
        raise ValueError("invalid_target")
    if presented not in acceptable and presented not in localhost_aliases(canonical):
        raise ValueError("invalid_target")

    if not db.consume_mcp_oauth_auth_code(str(row["code_id"])):
        raise ValueError("invalid_grant")
    return mcp_oauth_token_service.issue_access_token(
        principal_id=str(row["principal_id"]),
        resource=bound_resource,
        client_id=client_id,
        scope=str(row.get("scope") or ""),
    )
