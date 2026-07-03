from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings

CredentialSource = Literal["api_key_header", "bearer"]


@dataclass(slots=True)
class RawCredential:
    value: str
    source: CredentialSource


@dataclass(slots=True)
class ResolvedPrincipal:
    principal_id: str
    kind: str
    display_name: str
    via: str
    is_admin_bypass: bool = False
    library_id: str | None = None
    role: str | None = None
    key_id: str | None = None
    # Explicit per-library capability sets from DB api_key_grants. When present
    # they take precedence over the single library_id/role fields.
    grant_readable: frozenset[str] | None = None
    grant_writable: frozenset[str] | None = None
    grant_maintainer: frozenset[str] | None = None


def extract_credential(x_api_key: str | None, authorization: str | None) -> RawCredential | None:
    if x_api_key:
        return RawCredential(value=x_api_key, source="api_key_header")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return RawCredential(value=token, source="bearer")
    return None


def _resolve_authing_bearer(token: str) -> ResolvedPrincipal | None:
    if not settings.authing_configured:
        return None
    try:
        from app.auth.authing_client import resolve_user
        from app.services.principal_service import ensure_user_principal

        user = resolve_user(token)
        principal = ensure_user_principal(user)
        role = "library_maintainer" if user.is_admin else "library_writer"
        return ResolvedPrincipal(
            principal_id=principal["principal_id"],
            kind="user",
            display_name=user.display_name,
            via="authing_bearer",
            library_id=settings.default_library_id,
            role=role,
        )
    except Exception:
        return None


def _resolve_db_api_key(raw: str) -> ResolvedPrincipal | None:
    """Resolve an X-API-Key against the DB api_keys table (design/08 Phase 2)."""
    try:
        from app.services.api_key_service import resolve_api_key

        resolved = resolve_api_key(raw)
    except Exception:
        return None
    if resolved is None:
        return None
    return ResolvedPrincipal(
        principal_id=resolved.principal_id,
        kind="api_key",
        display_name=resolved.label or resolved.principal_id,
        via="db_api_key",
        library_id=next(iter(sorted(resolved.readable)), None),
        role=resolved.role_summary,
        key_id=resolved.key_id,
        grant_readable=resolved.readable,
        grant_writable=resolved.writable,
        grant_maintainer=resolved.maintainer,
    )


def resolve_from_credential(cred: RawCredential | None) -> ResolvedPrincipal:
    if cred is None:
        return ResolvedPrincipal(
            principal_id="anonymous",
            kind="anonymous",
            display_name="anonymous",
            via="anonymous",
        )
    raw = cred.value
    if settings.dev_auth and secrets.compare_digest(raw, settings.dev_api_key):
        return ResolvedPrincipal(
            principal_id="dev:admin",
            kind="dev",
            display_name="dev admin",
            via="dev_api_key",
            is_admin_bypass=True,
            library_id=settings.default_library_id,
            role="library_admin",
        )
    db_key = _resolve_db_api_key(raw)
    if db_key is not None:
        return db_key
    for idx, key in enumerate(settings.maintainer_api_keys):
        if secrets.compare_digest(raw, key):
            return ResolvedPrincipal(
                principal_id=f"maintainer:key:{idx}",
                kind="api_key",
                display_name="library maintainer",
                via="maintainer_api_key",
                library_id=settings.default_library_id,
                role="library_maintainer",
            )
    for idx, key in enumerate(settings.writer_api_keys):
        if secrets.compare_digest(raw, key):
            return ResolvedPrincipal(
                principal_id=f"writer:key:{idx}",
                kind="api_key",
                display_name="library writer",
                via="writer_api_key",
                library_id=settings.default_library_id,
                role="library_writer",
            )
    if cred.source == "bearer":
        authing = _resolve_authing_bearer(raw)
        if authing is not None:
            return authing
    return ResolvedPrincipal(
        principal_id="anonymous",
        kind="anonymous",
        display_name="anonymous",
        via="invalid_credentials",
    )


@dataclass(slots=True)
class McpAuthContext:
    raw_present: bool
    principal: ResolvedPrincipal
    invalid_credentials: bool = False
    api_key_id: str | None = None
    key_prefix: str | None = None

    @property
    def readable_library_ids(self) -> set[str]:
        if self.principal.is_admin_bypass:
            from app.storage.db import all_library_ids

            return all_library_ids()
        if self.principal.grant_readable is not None:
            return set(self.principal.grant_readable)
        if self.principal.library_id:
            return {self.principal.library_id}
        if self.principal.kind != "anonymous":
            return {settings.default_library_id}
        return {settings.default_library_id}

    @property
    def writable_library_ids(self) -> set[str]:
        if self.principal.is_admin_bypass:
            from app.storage.db import all_library_ids

            return all_library_ids()
        if self.principal.grant_writable is not None:
            return set(self.principal.grant_writable)
        if self.principal.role in {"library_writer", "library_maintainer", "library_admin"} and self.principal.library_id:
            return {self.principal.library_id}
        return set()

    @property
    def maintainer_library_ids(self) -> set[str]:
        if self.principal.is_admin_bypass:
            from app.storage.db import all_library_ids

            return all_library_ids()
        if self.principal.grant_maintainer is not None:
            return set(self.principal.grant_maintainer)
        if self.principal.role in {"library_maintainer", "library_admin"} and self.principal.library_id:
            return {self.principal.library_id}
        return set()

    @property
    def caller_summary(self) -> dict:
        p = self.principal
        if p.is_admin_bypass:
            return {"type": "admin", "principal_id": p.principal_id, "kind": p.kind, "via": p.via}
        if p.kind == "anonymous":
            if p.via == "invalid_credentials":
                return {"type": "invalid", "principal_id": p.principal_id, "kind": "anonymous", "via": p.via}
            return {"type": "anonymous", "principal_id": p.principal_id, "kind": "anonymous", "via": "anonymous"}
        return {"type": p.kind, "principal_id": p.principal_id, "via": p.via, "role": p.role}


def resolve_mcp_auth(cred: RawCredential | None) -> McpAuthContext:
    principal = resolve_from_credential(cred)
    invalid = cred is not None and principal.via == "invalid_credentials"
    key_prefix: str | None = None
    if principal.key_id is not None:
        api_key_id = principal.key_id
    elif principal.kind != "anonymous":
        api_key_id = principal.principal_id
    else:
        api_key_id = None
    if cred is not None and not invalid:
        raw = cred.value
        key_prefix = raw if len(raw) <= 8 else f"{raw[:4]}…"
    return McpAuthContext(
        raw_present=cred is not None,
        principal=principal,
        invalid_credentials=invalid,
        api_key_id=api_key_id,
        key_prefix=key_prefix,
    )
