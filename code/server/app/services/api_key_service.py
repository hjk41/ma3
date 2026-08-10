"""DB-backed API key resolution (design/08 §3.3/§5.4, ADR-011 Phase 2).

MCP data access is gated on an API key that exists in the `api_keys` table.
A key carries per-library grants (`api_key_grants.role`) that expand into
read / write / maintain capability sets:

    role=reader  -> read
    role=writer  -> read + write
    role=admin   -> read + write + maintain

Revoked or expired keys resolve to ``None`` so the caller falls through to
``invalid_credentials`` (HTTP 401 / JSON-RPC -32001).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.storage import db

_ROLE_READ = {"reader", "writer", "admin"}
_ROLE_WRITE = {"writer", "admin"}
_ROLE_MAINTAIN = {"admin"}


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class ResolvedApiKey:
    key_id: str
    principal_id: str
    label: str
    billing_account_id: str | None = None
    readable: frozenset[str] = field(default_factory=frozenset)
    writable: frozenset[str] = field(default_factory=frozenset)
    maintainer: frozenset[str] = field(default_factory=frozenset)

    @property
    def role_summary(self) -> str:
        if self.maintainer:
            return "library_maintainer"
        if self.writable:
            return "library_writer"
        return "library_reader"


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= datetime.now(timezone.utc)


def resolve_api_key(plaintext: str) -> ResolvedApiKey | None:
    key = db.get_api_key_by_hash(hash_key(plaintext))
    if key is None:
        return None
    if key.get("revoked_at"):
        return None
    if _is_expired(key.get("expires_at")):
        return None

    key_id = str(key["key_id"])
    readable: set[str] = set()
    writable: set[str] = set()
    maintainer: set[str] = set()
    for grant in db.get_api_key_grants(key_id):
        library_id = str(grant["library_id"])
        role = str(grant["role"]).lower()
        if role in _ROLE_READ:
            readable.add(library_id)
        if role in _ROLE_WRITE:
            writable.add(library_id)
        if role in _ROLE_MAINTAIN:
            maintainer.add(library_id)

    db.touch_api_key_last_used(key_id)
    ba_raw = key.get("billing_account_id")
    return ResolvedApiKey(
        key_id=key_id,
        principal_id=str(key["principal_id"]),
        label=str(key.get("label") or ""),
        billing_account_id=str(ba_raw) if ba_raw else None,
        readable=frozenset(readable),
        writable=frozenset(writable),
        maintainer=frozenset(maintainer),
    )
