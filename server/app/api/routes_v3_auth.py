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
    ServicePrincipalCreateRequest,
    WhoamiResponse,
)
from app.models.library import Library, LibraryCreate
from app.services.auth_service import (
    bootstrap_library_admin,
    create_service_principal,
    issue_api_key,
    list_all_api_keys,
    list_api_keys,
    list_library_acl,
    principal_summary,
    revoke_api_key,
    revoke_library_access,
    grant_library_access,
    search_principals,
)
from app.services.library_service import create_library
from app.storage.repositories import ApiKeyRepository, AuthAuditRepository, LibraryRepository


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
    )


@router.get("/v3/auth/whoami", response_model=WhoamiResponse)
def whoami(principal: ResolvedPrincipal = Depends(current_principal)) -> WhoamiResponse:
    return _whoami(principal)


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


@router.post("/v3/auth/principals/service", response_model=Principal)
def post_service_principal(
    payload: ServicePrincipalCreateRequest,
    actor: ResolvedPrincipal = Depends(require_global_admin),
) -> Principal:
    return create_service_principal(payload.name, display_name=payload.display_name, actor=actor)


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
