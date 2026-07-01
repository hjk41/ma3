from __future__ import annotations

import secrets

from fastapi import HTTPException

from app.core.auth import hash_token
from app.core.config import settings
from app.core.ids import new_id
from app.core.security import ResolvedPrincipal
from app.core.time import utc_now_iso
from app.models.auth import ApiKeyInfo, ApiKeyIssued
from app.models.v4_org import ApiKeyGrant, IssueV4ApiKeyRequest, ROLE_ORDER
from app.services.auth_service import audit_auth_event
from app.services.org_service import effective_libraries_v4
from app.storage.repositories import LibraryRepository
from app.storage.v4_repositories import ApiKeyGrantRepository, V4ApiKeyRepository

_KEY_PREFIX = "ma3v4_"


def issue_v4_api_key(
    principal_id: str,
    payload: IssueV4ApiKeyRequest,
    *,
    actor: ResolvedPrincipal,
) -> ApiKeyIssued:
    if not payload.library_grants:
        raise HTTPException(status_code=400, detail="library_grants_required")
    has_admin = any(g.role == "admin" for g in payload.library_grants)
    if has_admin and not payload.acknowledge_admin_risk:
        raise HTTPException(status_code=400, detail="acknowledge_admin_risk_required")

    actor_libs = effective_libraries_v4(actor)
    for spec in payload.library_grants:
        lib = LibraryRepository().get(spec.library_id)
        if lib is None:
            raise HTTPException(status_code=404, detail=f"library_not_found:{spec.library_id}")
        actor_role = actor_libs.get(spec.library_id)
        if actor_role is None:
            raise HTTPException(status_code=403, detail=f"library_forbidden:{spec.library_id}")
        if ROLE_ORDER[spec.role] > ROLE_ORDER[actor_role]:
            raise HTTPException(status_code=403, detail=f"grant_exceeds_actor_role:{spec.library_id}")

    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    key_id = new_id("key")
    now = utc_now_iso()
    info = ApiKeyInfo(
        key_id=key_id,
        principal_id=principal_id,
        label=payload.label.strip(),
        scope_libraries=None,
        created_at=now,
        created_by=actor.principal_id if not actor.is_admin_bypass else principal_id,
        expires_at=payload.expires_at,
    )
    V4ApiKeyRepository().upsert(info, hash_token(raw))
    grants = [
        ApiKeyGrant(key_id=key_id, library_id=g.library_id, role=g.role)
        for g in payload.library_grants
    ]
    ApiKeyGrantRepository().replace_for_key(key_id, grants)
    audit_auth_event(
        actor_principal_id=actor.principal_id,
        action="api_key.issue",
        target_principal_id=principal_id,
        payload={"key_id": key_id, "grants": [g.model_dump() for g in grants]},
    )
    return ApiKeyIssued(raw=raw, info=info)


def list_v4_api_keys(principal_id: str) -> list[ApiKeyInfo]:
    keys = V4ApiKeyRepository().list_by_principal(principal_id)
    grant_map = ApiKeyGrantRepository().list_by_keys([k.key_id for k in keys])
    out: list[ApiKeyInfo] = []
    for key in keys:
        grants = grant_map.get(key.key_id, [])
        key.scope_libraries = [g.library_id for g in grants] if grants else []
        out.append(key)
    return out


def revoke_v4_api_key(key_id: str, actor: ResolvedPrincipal) -> None:
    key = V4ApiKeyRepository().get(key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="key_not_found")
    if key.principal_id != actor.principal_id and not actor.is_admin_bypass:
        actor_libs = effective_libraries_v4(actor, role_at_least="admin")
        grant_libs = {g.library_id for g in ApiKeyGrantRepository().list_by_key(key_id)}
        if not grant_libs.intersection(actor_libs):
            raise HTTPException(status_code=403, detail="forbidden")
    V4ApiKeyRepository().revoke(key_id, utc_now_iso())
    audit_auth_event(
        actor_principal_id=actor.principal_id,
        action="api_key.revoke",
        target_principal_id=key.principal_id,
        payload={"key_id": key_id},
    )
