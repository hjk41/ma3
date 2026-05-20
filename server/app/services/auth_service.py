from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException

from app.core.auth import effective_libraries
from app.core.ids import new_id
from app.core.security import ResolvedPrincipal, hash_token
from app.core.time import utc_now_iso
from app.models.auth import (
    AclEntry,
    ApiKeyInfo,
    ApiKeyIssued,
    AuthAuditEntry,
    Principal,
    PrincipalSummary,
    ROLE_ORDER,
    LIBRARY_ROLE_TO_ROLE,
)
from app.services.metrics_service import metrics
from app.storage.repositories import (
    ApiKeyRepository,
    AuthAuditRepository,
    LibraryAclRepository,
    RoleAssignmentRepository,
    LibraryRepository,
    PrincipalRepository,
)


def audit_auth_event(
    *,
    actor_principal_id: str,
    action: str,
    target_principal_id: str | None = None,
    library_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuthAuditEntry:
    entry = AuthAuditEntry(
        audit_id=new_id("aud"),
        actor_principal_id=actor_principal_id,
        action=action,
        target_principal_id=target_principal_id,
        library_id=library_id,
        payload_json=payload or {},
        created_at=utc_now_iso(),
    )
    AuthAuditRepository().insert(entry)
    metrics.record_auth_audit(action)
    return entry


def _actor_id(actor: ResolvedPrincipal) -> str:
    return actor.principal_id


def _fk_actor_id(actor: ResolvedPrincipal, fallback: str) -> str:
    # ``admin:root`` is intentionally synthetic and not persisted. Columns with
    # FK constraints therefore use a real principal involved in the mutation;
    # the audit row still records the true actor.
    return fallback if actor.is_admin_bypass else actor.principal_id


def _assert_admin(actor: ResolvedPrincipal) -> None:
    if not actor.is_admin_bypass:
        raise HTTPException(status_code=403, detail="admin_required")


def create_user_principal(sso_user: str, display_name: str) -> Principal:
    principal = PrincipalRepository().upsert_user(sso_user, display_name)
    audit_auth_event(
        actor_principal_id=principal.principal_id,
        action="principal.create",
        target_principal_id=principal.principal_id,
        payload={"kind": "user"},
    )
    return principal


def create_service_principal(name: str, *, actor: ResolvedPrincipal, display_name: str | None = None) -> Principal:
    _assert_admin(actor)
    principal = PrincipalRepository().upsert_service(name, display_name or name)
    audit_auth_event(
        actor_principal_id=_actor_id(actor),
        action="principal.create",
        target_principal_id=principal.principal_id,
        payload={"kind": "service"},
    )
    return principal


def _normalize_scope(scope_libraries: list[str] | None, actor: ResolvedPrincipal) -> list[str] | None:
    if scope_libraries is None:
        return None
    requested = set(scope_libraries)
    if actor.is_admin_bypass:
        allowed = {lib.library_id for lib in LibraryRepository().list_all()}
    else:
        allowed = set(effective_libraries(actor))
    narrowed = sorted(requested & allowed)
    if not narrowed:
        raise HTTPException(status_code=400, detail="scope_empty")
    return narrowed


def issue_api_key(
    principal_id: str,
    label: str,
    scope_libraries: list[str] | None,
    expires_at: str | None,
    *,
    actor: ResolvedPrincipal,
) -> ApiKeyIssued:
    if not actor.is_admin_bypass and principal_id != actor.principal_id:
        raise HTTPException(status_code=403, detail="cannot_issue_for_other_principal")
    principal = PrincipalRepository().get(principal_id)
    if principal is None:
        raise HTTPException(status_code=404, detail="principal_not_found")
    scope = _normalize_scope(scope_libraries, actor)
    raw = "ma3v3_" + secrets.token_urlsafe(24)
    info = ApiKeyInfo(
        key_id=new_id("akey"),
        principal_id=principal_id,
        label=label,
        scope_libraries=scope,
        created_at=utc_now_iso(),
        created_by=_fk_actor_id(actor, principal_id),
        expires_at=expires_at,
    )
    ApiKeyRepository().upsert(info, hash_token(raw))
    audit_auth_event(
        actor_principal_id=_actor_id(actor),
        action="key.issue",
        target_principal_id=principal_id,
        payload={"key_id": info.key_id, "scope_libraries": scope},
    )
    return ApiKeyIssued(raw=raw, info=info)


def revoke_api_key(key_id: str, *, actor: ResolvedPrincipal) -> None:
    info = ApiKeyRepository().get(key_id)
    if info is None:
        raise HTTPException(status_code=404, detail="key_not_found")
    if not actor.is_admin_bypass and info.principal_id != actor.principal_id:
        raise HTTPException(status_code=403, detail="cannot_revoke_other_principal_key")
    changed = ApiKeyRepository().revoke(key_id, utc_now_iso())
    if changed:
        audit_auth_event(
            actor_principal_id=_actor_id(actor),
            action="key.revoke",
            target_principal_id=info.principal_id,
            payload={"key_id": key_id},
        )


def list_api_keys(principal_id: str) -> list[ApiKeyInfo]:
    return ApiKeyRepository().list_by_principal(principal_id)


def list_all_api_keys() -> list[ApiKeyInfo]:
    return ApiKeyRepository().list_all()


def list_principal_libraries(principal_id: str) -> dict[str, str]:
    from app.core.auth import effective_libraries
    principal = PrincipalRepository().get(principal_id)
    if principal is None:
        return {}
    rp = ResolvedPrincipal(
        principal_id=principal.principal_id,
        kind=principal.kind,
        display_name=principal.display_name,
        via="api_key",
        is_admin_bypass=False,
    )
    return effective_libraries(rp)


def _can_grant(actor: ResolvedPrincipal, library_id: str, role: str) -> None:
    if actor.is_admin_bypass or actor.kind == "service":
        return
    if actor.kind == "legacy":
        raise HTTPException(status_code=403, detail="legacy_cannot_grant")
    actor_role = effective_libraries(actor).get(library_id)
    if actor_role is None or ROLE_ORDER[actor_role] < ROLE_ORDER[role]:
        raise HTTPException(status_code=403, detail="cannot_grant_role_not_held")


def grant_library_access(library_id: str, principal_id: str, role: str, *, actor: ResolvedPrincipal) -> AclEntry:
    if LibraryRepository().get(library_id) is None:
        raise HTTPException(status_code=404, detail="library_not_found")
    if PrincipalRepository().get(principal_id) is None:
        raise HTTPException(status_code=404, detail="principal_not_found")
    _can_grant(actor, library_id, role)
    entry = AclEntry(
        library_id=library_id,
        principal_id=principal_id,
        role=role,
        granted_at=utc_now_iso(),
        granted_by=_fk_actor_id(actor, principal_id),
    )
    from app.models.auth import RoleAssignment
    RoleAssignmentRepository().upsert(RoleAssignment(
        scope_type="library",
        scope_id=library_id,
        principal_id=principal_id,
        role_name=LIBRARY_ROLE_TO_ROLE[role],
        granted_at=entry.granted_at,
        granted_by=entry.granted_by,
    ))
    audit_auth_event(
        actor_principal_id=_actor_id(actor),
        action="acl.grant",
        target_principal_id=principal_id,
        library_id=library_id,
        payload={"role": role},
    )
    return entry


def bootstrap_library_admin(library_id: str, principal_id: str, *, actor: ResolvedPrincipal) -> AclEntry:
    """Grant the initial admin on a newly-created library.

    This bypasses the equal-or-higher role rule because no admin exists yet.
    """
    if PrincipalRepository().get(principal_id) is None:
        raise HTTPException(status_code=404, detail="principal_not_found")
    entry = AclEntry(
        library_id=library_id,
        principal_id=principal_id,
        role="admin",
        granted_at=utc_now_iso(),
        granted_by=_fk_actor_id(actor, principal_id),
    )
    from app.models.auth import RoleAssignment
    RoleAssignmentRepository().upsert(RoleAssignment(
        scope_type="library",
        scope_id=library_id,
        principal_id=principal_id,
        role_name="library_admin",
        granted_at=entry.granted_at,
        granted_by=entry.granted_by,
    ))
    audit_auth_event(
        actor_principal_id=_actor_id(actor),
        action="acl.grant",
        target_principal_id=principal_id,
        library_id=library_id,
        payload={"role": "admin", "initial": True},
    )
    return entry


def revoke_library_access(library_id: str, principal_id: str, *, actor: ResolvedPrincipal) -> None:
    _can_grant(actor, library_id, "admin")
    repo = RoleAssignmentRepository()
    existing = repo.get_library_role(library_id, principal_id) or LibraryAclRepository().get_role(library_id, principal_id)
    if existing == "admin" and repo.count_library_admins(library_id) <= 1:
        raise HTTPException(status_code=409, detail="cannot_remove_last_admin")
    changed = repo.delete("library", library_id, principal_id)
    if changed:
        audit_auth_event(
            actor_principal_id=_actor_id(actor),
            action="acl.revoke",
            target_principal_id=principal_id,
            library_id=library_id,
            payload={"previous_role": existing},
        )


def list_library_acl(library_id: str) -> list[AclEntry]:
    entries = RoleAssignmentRepository().list_library_acl(library_id)
    assigned = {entry.principal_id for entry in entries}
    entries.extend(entry for entry in LibraryAclRepository().list_by_library(library_id) if entry.principal_id not in assigned)
    return entries


def search_principals(prefix: str | None, kind: str | None = None, limit: int = 20) -> list[Principal]:
    return PrincipalRepository().search(prefix=prefix, kind=kind, limit=limit)


def get_principal(principal_id: str) -> Principal | None:
    return PrincipalRepository().get(principal_id)


def principal_summary(principal: Principal) -> PrincipalSummary:
    return PrincipalSummary(
        principal_id=principal.principal_id,
        kind=principal.kind,
        display_name=principal.display_name,
    )
