"""Issue and validate ma3-issued MCP OAuth access tokens (ADR-016)."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.storage import db

TOKEN_PREFIX = "ma3mcp_"


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


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


@dataclass(slots=True)
class IssuedMcpToken:
    access_token: str
    token_id: str
    principal_id: str
    resource: str
    expires_at: str
    expires_in: int
    scope: str
    client_id: str
    token_type: str = "Bearer"


@dataclass(slots=True)
class ResolvedMcpOAuthToken:
    token_id: str
    principal_id: str
    resource: str
    scope: str
    client_id: str
    expires_at: str


def issue_access_token(
    *,
    principal_id: str,
    resource: str,
    client_id: str = "",
    scope: str = "",
    ttl_sec: int | None = None,
) -> IssuedMcpToken:
    ttl = int(ttl_sec if ttl_sec is not None else settings.mcp_oauth_access_token_ttl_sec)
    ttl = max(60, ttl)
    now = _utcnow()
    expires = now + timedelta(seconds=ttl)
    plaintext = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    token_id = db.new_id("mot")
    expires_at = expires.isoformat()
    db.insert_mcp_oauth_token(
        token_id=token_id,
        token_hash=hash_token(plaintext),
        principal_id=principal_id,
        resource=resource,
        expires_at=expires_at,
        scope=scope,
        client_id=client_id,
        created_at=now.isoformat(),
    )
    return IssuedMcpToken(
        access_token=plaintext,
        token_id=token_id,
        principal_id=principal_id,
        resource=resource,
        expires_at=expires_at,
        expires_in=ttl,
        scope=scope,
        client_id=client_id,
    )


def resolve_mcp_oauth_token(
    plaintext: str,
    *,
    expected_resource: str | None = None,
    request=None,
) -> ResolvedMcpOAuthToken | None:
    if not plaintext or not plaintext.startswith(TOKEN_PREFIX):
        return None
    row = db.get_mcp_oauth_token_by_hash(hash_token(plaintext))
    if row is None:
        return None
    if row.get("revoked_at"):
        return None
    expires = _parse_iso(str(row.get("expires_at") or ""))
    if expires is None or expires <= _utcnow():
        return None
    resource = str(row.get("resource") or "")
    from app.core.public_url import localhost_aliases, resource_acceptable

    if expected_resource is not None:
        ok = resource.rstrip("/") in localhost_aliases(expected_resource.rstrip("/"))
    else:
        ok = resource_acceptable(resource, request=request)
    if not ok:
        return None
    return ResolvedMcpOAuthToken(
        token_id=str(row["token_id"]),
        principal_id=str(row["principal_id"]),
        resource=resource,
        scope=str(row.get("scope") or ""),
        client_id=str(row.get("client_id") or ""),
        expires_at=str(row["expires_at"]),
    )


def revoke_access_token(token_id: str) -> bool:
    return db.revoke_mcp_oauth_token(token_id)
