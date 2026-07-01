from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.config import settings
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.auth import ResolvedPrincipal
from app.models.library import Library, LibraryCreate
from app.models.v4_org import (
    LibraryAccessEntry,
    Organization,
    OrganizationMember,
    OrgCreateRequest,
    OrgMemberAddRequest,
    ROLE_ORDER,
    ORG_ROLE_ORDER,
)
from app.storage.repositories import LibraryRepository, PrincipalRepository
from app.storage.v4_repositories import (
    LibraryAccessRepository,
    OrganizationMemberRepository,
    OrganizationRepository,
    normalize_org_slug,
    new_org_id,
)
from app.services.auth_service import audit_auth_event


def _stronger(a: str | None, b: str) -> str:
    if a is None:
        return b
    return a if ROLE_ORDER[a] >= ROLE_ORDER[b] else b


def org_admin_role(principal_id: str, org_id: str) -> str | None:
    role = OrganizationMemberRepository().get_role(org_id, principal_id)
    if role in {"owner", "admin"}:
        return "admin"
    return None


def principal_library_roles_v4(principal_id: str) -> dict[str, str]:
    roles: dict[str, str] = {}
    libs = {lib.library_id: lib for lib in LibraryRepository().list_all()}
    for entry in LibraryAccessRepository().list_by_principal(principal_id):
        roles[entry.library_id] = _stronger(roles.get(entry.library_id), entry.role)
    for lib_id, lib in libs.items():
        if lib.is_public:
            roles[lib_id] = _stronger(roles.get(lib_id), "reader")
        if lib.organization_id:
            implicit = org_admin_role(principal_id, lib.organization_id)
            if implicit:
                roles[lib_id] = _stronger(roles.get(lib_id), implicit)
    return roles


def cap_grant_role(principal_role: str, grant_role: str) -> str:
    return grant_role if ROLE_ORDER[grant_role] <= ROLE_ORDER[principal_role] else principal_role


def effective_libraries_v4(
    principal: ResolvedPrincipal,
    *,
    role_at_least: str = "reader",
) -> dict[str, str]:
    if principal.is_admin_bypass:
        return {lib.library_id: "admin" for lib in LibraryRepository().list_all()}

    if principal.kind == "anonymous":
        roles = {
            lib.library_id: "reader"
            for lib in LibraryRepository().list_public()
        }
    else:
        roles = principal_library_roles_v4(principal.principal_id)

    if principal.api_key_grants:
        capped: dict[str, str] = {}
        for lib_id, grant_role in principal.api_key_grants.items():
            if lib_id not in roles:
                continue
            eff = cap_grant_role(roles[lib_id], grant_role)
            if ROLE_ORDER[eff] >= ROLE_ORDER[role_at_least]:
                capped[lib_id] = eff
        return capped

    return {
        lib_id: role
        for lib_id, role in roles.items()
        if ROLE_ORDER[role] >= ROLE_ORDER[role_at_least]
    }


def require_org_role(principal: ResolvedPrincipal, org_id: str, at_least: str) -> str:
    if principal.is_admin_bypass:
        return "owner"
    role = OrganizationMemberRepository().get_role(org_id, principal.principal_id)
    if role is None:
        raise HTTPException(status_code=404, detail="org_not_found")
    if ORG_ROLE_ORDER.get(role, 0) < ORG_ROLE_ORDER.get(at_least, 99):
        raise HTTPException(status_code=403, detail="org_forbidden")
    return role


def create_organization(payload: OrgCreateRequest, actor: ResolvedPrincipal) -> Organization:
    slug = normalize_org_slug(payload.slug)
    if OrganizationRepository().get_by_slug(slug):
        raise HTTPException(status_code=409, detail="org_slug_taken")
    org = Organization(
        org_id=new_org_id(),
        slug=slug,
        name=payload.name.strip(),
        description=payload.description or "",
        plan_tier="free",
        member_seat_limit=settings.free_member_seat_limit,
        created_at=utc_now_iso(),
        created_by=actor.principal_id,
    )
    OrganizationRepository().insert(org)
    OrganizationMemberRepository().insert(
        OrganizationMember(
            org_id=org.org_id,
            principal_id=actor.principal_id,
            org_role="owner",
            joined_at=org.created_at,
            invited_by=actor.principal_id,
        )
    )
    audit_auth_event(
        actor_principal_id=actor.principal_id,
        action="org.create",
        payload={"org_id": org.org_id, "slug": org.slug},
    )
    return org


def create_org_library(org_id: str, payload: LibraryCreate, actor: ResolvedPrincipal) -> Library:
    require_org_role(actor, org_id, "admin")
    org = OrganizationRepository().get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org_not_found")
    library = Library(
        library_id=new_id("lib"),
        organization_id=org_id,
        name=payload.name,
        description=payload.description,
        is_public=bool(payload.is_public),
        parent_library_id=None,
        is_personal=False,
        created_at=utc_now_iso(),
    )
    LibraryRepository().insert(library)
    audit_auth_event(
        actor_principal_id=actor.principal_id,
        action="library.create",
        library_id=library.library_id,
        payload={"org_id": org_id},
    )
    return library


def add_org_member(org_id: str, payload: OrgMemberAddRequest, actor: ResolvedPrincipal) -> OrganizationMember:
    require_org_role(actor, org_id, "admin")
    org = OrganizationRepository().get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org_not_found")
    count = OrganizationMemberRepository().count(org_id)
    if count >= org.member_seat_limit:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "seat_limit_reached",
                "member_seat_limit": org.member_seat_limit,
                "member_count": count,
            },
        )
    principal_id = payload.principal_id
    if not principal_id and payload.login_name:
        principal = PrincipalRepository().get(f"user:{payload.login_name}")
        if principal is None:
            principal = PrincipalRepository().upsert_user(payload.login_name, payload.login_name)
        principal_id = principal.principal_id
    if not principal_id:
        raise HTTPException(status_code=400, detail="principal_id_or_login_name_required")
    if OrganizationMemberRepository().get_role(org_id, principal_id):
        raise HTTPException(status_code=409, detail="already_member")
    member = OrganizationMember(
        org_id=org_id,
        principal_id=principal_id,
        org_role=payload.org_role,
        joined_at=utc_now_iso(),
        invited_by=actor.principal_id,
    )
    OrganizationMemberRepository().insert(member)
    audit_auth_event(
        actor_principal_id=actor.principal_id,
        action="org.member.add",
        target_principal_id=principal_id,
        payload={"org_id": org_id, "org_role": payload.org_role},
    )
    return member


def grant_library_access_v4(
    library_id: str,
    principal_id: str,
    role: str,
    actor: ResolvedPrincipal,
) -> LibraryAccessEntry:
    lib = LibraryRepository().get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library_not_found")
    if lib.organization_id:
        try:
            require_org_role(actor, lib.organization_id, "admin")
        except HTTPException:
            actor_role = effective_libraries_v4(actor).get(library_id)
            if actor_role != "admin":
                raise
    else:
        actor_role = effective_libraries_v4(actor).get(library_id)
        if actor_role != "admin" and not actor.is_admin_bypass:
            raise HTTPException(status_code=403, detail="library_admin_required")
    if PrincipalRepository().get(principal_id) is None:
        raise HTTPException(status_code=404, detail="principal_not_found")
    entry = LibraryAccessEntry(
        library_id=library_id,
        principal_id=principal_id,
        role=role,
        granted_at=utc_now_iso(),
        granted_by=actor.principal_id,
    )
    LibraryAccessRepository().upsert(entry)
    audit_auth_event(
        actor_principal_id=actor.principal_id,
        action="library_access.grant",
        target_principal_id=principal_id,
        library_id=library_id,
        payload={"role": role},
    )
    return entry


def create_dev_session(login_name: str) -> tuple[str, str]:
    principal = PrincipalRepository().upsert_user(login_name, login_name)
    session_id = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    from app.models.v4_org import SessionRecord
    from app.storage.v4_repositories import SessionRepository

    SessionRepository().insert(
        SessionRecord(
            session_id=session_id,
            principal_id=principal.principal_id,
            expires_at=expires,
            created_at=utc_now_iso(),
            idp_region="dev",
        )
    )
    return session_id, principal.principal_id
