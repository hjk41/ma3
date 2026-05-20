from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.core.security import (
    ResolvedPrincipal,
    current_principal,
    effective_library_details,
    require_authenticated,
    require_global_admin,
    require_library_admin,
    require_library_read,
)
from app.models.auth import (
    AclEntry,
    AclGrantRequest,
    ApiKeyInfo,
    ApiKeyIssued,
    AuthAuditEntry,
    IssueApiKeyRequest,
    Principal,
    PrincipalBlock,
    PrincipalSummary,
    Role,
    RoleAssignment,
    ServicePrincipalCreateRequest,
    WhoamiResponse,
)
from app.models.library import Library, LibraryCreate
from app.services.auth_service import (
    bootstrap_library_admin,
    create_service_principal,
    create_user_principal,
    get_principal,
    issue_api_key,
    list_all_api_keys,
    list_api_keys,
    list_library_acl,
    list_principal_libraries,
    principal_summary,
    revoke_api_key,
    revoke_library_access,
    grant_library_access,
    search_principals,
)
from app.services.library_service import create_library
from app.storage.repositories import ApiKeyRepository, AuthAuditRepository, LibraryRepository, RoleRepository, RoleAssignmentRepository


router = APIRouter(tags=["v3-auth"])


def _whoami(principal: ResolvedPrincipal) -> WhoamiResponse:
    api_key = ApiKeyRepository().get(principal.api_key_id) if principal.api_key_id else None
    return WhoamiResponse(
        principal=PrincipalBlock(
            principal_id=principal.principal_id,
            kind=principal.kind,
            display_name=principal.display_name,
        ),
        via=principal.via,
        libraries=effective_library_details(principal),
        api_key=api_key,
        admin_bypass=principal.is_admin_bypass,
        roles=RoleAssignmentRepository().list_by_principal(principal.principal_id) if principal.kind not in {"anonymous", "admin"} else [],
    )


@router.get("/v3/auth/whoami", response_model=WhoamiResponse)
def whoami(principal: ResolvedPrincipal = Depends(current_principal)) -> WhoamiResponse:
    return _whoami(principal)


@router.get("/v3/roles", response_model=list[Role])
def get_roles(_: ResolvedPrincipal = Depends(require_authenticated)) -> list[Role]:
    return RoleRepository().list()


@router.get("/v3/auth/permissions/me", response_model=dict)
def get_my_permissions(principal: ResolvedPrincipal = Depends(current_principal)) -> dict:
    from app.core.auth import effective_permissions

    by_library = {lib.library_id: sorted(effective_permissions(principal, lib.library_id)) for lib in effective_library_details(principal)}
    return {"global": sorted(effective_permissions(principal)), "by_library": by_library}


@router.post("/v3/auth/keys", response_model=ApiKeyIssued)
def post_key(
    payload: IssueApiKeyRequest,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> ApiKeyIssued:
    if principal.kind == "admin":
        raise HTTPException(status_code=400, detail="admin_key_cannot_self_issue")
    return issue_api_key(
        principal.principal_id,
        payload.label,
        payload.scope_libraries,
        payload.expires_at,
        actor=principal,
    )


@router.get("/v3/auth/keys", response_model=list[ApiKeyInfo])
def get_keys(principal: ResolvedPrincipal = Depends(require_authenticated)) -> list[ApiKeyInfo]:
    if principal.kind == "admin":
        return []
    return list_api_keys(principal.principal_id)


@router.get("/v3/auth/keys/all", response_model=list[ApiKeyInfo])
def get_all_keys(_: ResolvedPrincipal = Depends(require_global_admin)) -> list[ApiKeyInfo]:
    return list_all_api_keys()


@router.delete("/v3/auth/keys/{key_id}", status_code=204)
def delete_key(
    key_id: str,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> Response:
    revoke_api_key(key_id, actor=principal)
    return Response(status_code=204)


@router.get("/v3/auth/principals", response_model=list[PrincipalSummary])
def get_principals(
    prefix: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _: ResolvedPrincipal = Depends(require_authenticated),
) -> list[PrincipalSummary]:
    return [principal_summary(item) for item in search_principals(prefix, kind, limit)]


@router.get("/v3/auth/principals/{principal_id:path}")
def get_principal_detail(
    principal_id: str,
    _: ResolvedPrincipal = Depends(require_authenticated),
) -> dict:
    p = get_principal(principal_id)
    if p is None:
        raise HTTPException(status_code=404, detail="principal_not_found")
    libs = list_principal_libraries(principal_id)
    keys = list_api_keys(principal_id)
    return {
        "principal": p.model_dump() if hasattr(p, "model_dump") else dict(p),
        "libraries": [{"library_id": lid, "role": role} for lid, role in libs.items()],
        "api_keys": [k.model_dump() if hasattr(k, "model_dump") else dict(k) for k in keys],
    }


@router.post("/v3/auth/principals/service", response_model=Principal)
def post_service_principal(
    payload: ServicePrincipalCreateRequest,
    actor: ResolvedPrincipal = Depends(require_global_admin),
) -> Principal:
    return create_service_principal(payload.name, display_name=payload.display_name, actor=actor)


@router.post("/v3/admin/issue_xyz_keys", response_model=dict)
def post_issue_xyz_keys(
    payload: dict,
    actor: ResolvedPrincipal = Depends(require_global_admin),
) -> dict:
    """Bulk-issue per-user xyz library keys. Admin only."""
    from app.core.config import settings as _settings
    xyz = (payload.get("xyz_library_id") or _settings.xyz_library_id or "").strip()
    if not xyz:
        raise HTTPException(status_code=400, detail="xyz_library_id_unset")
    usernames = payload.get("usernames") or []
    if not isinstance(usernames, list) or not usernames:
        raise HTTPException(status_code=400, detail="usernames_required")
    issued: list[dict] = []
    failed: list[dict] = []
    for raw_name in usernames:
        name = str(raw_name).strip()
        if not name:
            continue
        try:
            create_user_principal(name, name)
            result = issue_api_key(
                principal_id=f"user:{name}",
                label=f"xyz default for {name}",
                scope_libraries=[xyz],
                expires_at=None,
                actor=actor,
            )
            issued.append({"username": name, "raw": result.raw, "key_id": result.info.key_id})
        except Exception as exc:  # noqa: BLE001
            failed.append({"username": name, "error": str(exc)})
    return {"issued": issued, "failed": failed}


@router.get("/v3/auth/audit", response_model=list[AuthAuditEntry])
def get_audit(
    since: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: ResolvedPrincipal = Depends(require_global_admin),
) -> list[AuthAuditEntry]:
    return AuthAuditRepository().list(since=since, actor=actor, action=action, limit=limit)


@router.post("/v3/libraries", response_model=dict)
def post_v3_library(
    payload: LibraryCreate,
    actor: ResolvedPrincipal = Depends(require_authenticated),
) -> dict:
    if actor.kind == "admin":
        lib = create_library(payload.model_copy(update={"parent_library_id": None}))
        return {"library": lib.model_dump(), "grant": None}
    lib = create_library(payload.model_copy(update={"parent_library_id": None}))
    grant = bootstrap_library_admin(lib.library_id, actor.principal_id, actor=actor)
    return {"library": lib.model_dump(), "grant": grant.model_dump()}


@router.get("/v3/libraries/{library_id}/acl", response_model=list[AclEntry])
def get_library_acl(
    library_id: str,
    _: str = Depends(require_library_read),
) -> list[AclEntry]:
    if LibraryRepository().get(library_id) is None:
        raise HTTPException(status_code=404, detail="library_not_found")
    return list_library_acl(library_id)


@router.put("/v3/libraries/{library_id}/acl/{principal_id}", response_model=AclEntry)
def put_library_acl(
    library_id: str,
    principal_id: str,
    payload: AclGrantRequest,
    actor: ResolvedPrincipal = Depends(current_principal),
    _: str | None = Depends(require_library_admin),
) -> AclEntry:
    return grant_library_access(library_id, principal_id, payload.role, actor=actor)


@router.delete("/v3/libraries/{library_id}/acl/{principal_id}", status_code=204)
def delete_library_acl(
    library_id: str,
    principal_id: str,
    actor: ResolvedPrincipal = Depends(current_principal),
    _: str | None = Depends(require_library_admin),
) -> Response:
    revoke_library_access(library_id, principal_id, actor=actor)
    return Response(status_code=204)
