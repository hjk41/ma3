from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass(slots=True)
class ResolvedPrincipal:
    principal_id: str
    kind: str
    display_name: str
    via: str
    is_admin_bypass: bool = False
    library_id: str | None = None
    role: str | None = None


def _extract_raw(x_api_key: str | None, authorization: str | None) -> str | None:
    if x_api_key:
        return x_api_key
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return None


def resolve_from_raw(raw: str | None) -> ResolvedPrincipal:
    if raw and settings.dev_auth and secrets.compare_digest(raw, settings.dev_api_key):
        return ResolvedPrincipal(
            principal_id="dev:admin",
            kind="dev",
            display_name="dev admin",
            via="dev_api_key",
            is_admin_bypass=True,
            library_id=settings.default_library_id,
            role="library_admin",
        )
    return ResolvedPrincipal(
        principal_id="anonymous",
        kind="anonymous",
        display_name="anonymous",
        via="anonymous",
    )


@dataclass(slots=True)
class McpAuthContext:
    raw_present: bool
    principal: ResolvedPrincipal

    @property
    def readable_library_ids(self) -> set[str]:
        if self.principal.is_admin_bypass:
            from app.storage.db import all_library_ids

            return all_library_ids()
        if self.principal.kind != "anonymous":
            return {settings.default_library_id}
        return {settings.default_library_id}

    @property
    def writable_library_ids(self) -> set[str]:
        if self.principal.is_admin_bypass:
            from app.storage.db import all_library_ids

            return all_library_ids()
        return set()

    @property
    def maintainer_library_ids(self) -> set[str]:
        if self.principal.is_admin_bypass:
            from app.storage.db import all_library_ids

            return all_library_ids()
        return set()

    @property
    def caller_summary(self) -> dict:
        p = self.principal
        if p.is_admin_bypass:
            return {"type": "admin", "principal_id": p.principal_id, "kind": p.kind, "via": p.via}
        if p.kind == "anonymous":
            return {"type": "anonymous", "principal_id": p.principal_id, "kind": "anonymous", "via": "anonymous"}
        return {"type": p.kind, "principal_id": p.principal_id, "via": p.via}


def resolve_mcp_auth(raw: str | None) -> McpAuthContext:
    return McpAuthContext(raw_present=bool(raw), principal=resolve_from_raw(raw))
