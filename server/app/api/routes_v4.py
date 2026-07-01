from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.auth_v4 import clear_session_cookie, set_session_cookie
from app.core.config import settings
from app.core.security import ResolvedPrincipal, current_principal, effective_libraries, require_authenticated
from app.models.auth import ApiKeyIssued, PrincipalBlock, WhoamiResponse
from app.models.library import Library, LibraryCreate
from app.models.v4_org import (
    IssueV4ApiKeyRequest,
    LibraryAccessGrantRequest,
    OrgCreateRequest,
    OrgMemberAddRequest,
    Organization,
    OrganizationMember,
)
from app.services.org_service import (
    add_org_member,
    create_dev_session,
    create_org_library,
    create_organization,
    grant_library_access_v4,
    require_org_role,
)
from app.services.v4_api_key_service import issue_v4_api_key, list_v4_api_keys, revoke_v4_api_key
from app.storage.repositories import LibraryRepository
from app.storage.v4_repositories import LibraryAccessRepository, OrganizationMemberRepository, OrganizationRepository


router = APIRouter(tags=["v4"])


def _whoami(principal: ResolvedPrincipal) -> WhoamiResponse:
    libs = effective_libraries(principal)
    from app.models.auth import EffectiveLibrary

    details = [
        EffectiveLibrary(library_id=lib_id, role=role, source="v4", name=None, is_public=None)
        for lib_id, role in sorted(libs.items())
    ]
    return WhoamiResponse(
        principal=PrincipalBlock(
            principal_id=principal.principal_id,
            kind=principal.kind,
            display_name=principal.display_name,
        ),
        via=principal.via,
        libraries=details,
        api_key=None,
        admin_bypass=principal.is_admin_bypass,
        roles=[],
    )


@router.get("/v4/auth/whoami", response_model=WhoamiResponse)
def v4_whoami(principal: ResolvedPrincipal = Depends(current_principal)) -> WhoamiResponse:
    return _whoami(principal)


@router.post("/v4/auth/dev/login")
def v4_dev_login(login_name: str, response: Response) -> dict[str, str]:
    if not settings.dev_auth_enabled:
        raise HTTPException(status_code=404, detail="dev_auth_disabled")
    session_id, principal_id = create_dev_session(login_name.strip())
    set_session_cookie(response, session_id)
    return {"principal_id": principal_id, "session_id": session_id}


@router.post("/v4/auth/logout")
def v4_logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}


@router.post("/v4/auth/keys", response_model=ApiKeyIssued)
def v4_issue_key(
    payload: IssueV4ApiKeyRequest,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> ApiKeyIssued:
    return issue_v4_api_key(principal.principal_id, payload, actor=principal)


@router.get("/v4/auth/keys")
def v4_list_keys(principal: ResolvedPrincipal = Depends(require_authenticated)) -> list[dict]:
    keys = list_v4_api_keys(principal.principal_id)
    return [k.model_dump() for k in keys]


@router.delete("/v4/auth/keys/{key_id}")
def v4_revoke_key(key_id: str, principal: ResolvedPrincipal = Depends(require_authenticated)) -> dict[str, str]:
    revoke_v4_api_key(key_id, principal)
    return {"status": "revoked"}


@router.post("/v4/orgs", response_model=Organization)
def v4_create_org(
    payload: OrgCreateRequest,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> Organization:
    return create_organization(payload, principal)


@router.get("/v4/orgs", response_model=list[Organization])
def v4_list_orgs(principal: ResolvedPrincipal = Depends(require_authenticated)) -> list[Organization]:
    return OrganizationRepository().list_for_principal(principal.principal_id)


@router.get("/v4/orgs/{org_id}", response_model=Organization)
def v4_get_org(
    org_id: str,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> Organization:
    require_org_role(principal, org_id, "member")
    org = OrganizationRepository().get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="org_not_found")
    return org


@router.get("/v4/orgs/{org_id}/members", response_model=list[OrganizationMember])
def v4_list_members(
    org_id: str,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> list[OrganizationMember]:
    require_org_role(principal, org_id, "member")
    return OrganizationMemberRepository().list_members(org_id)


@router.post("/v4/orgs/{org_id}/members", response_model=OrganizationMember)
def v4_add_member(
    org_id: str,
    payload: OrgMemberAddRequest,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> OrganizationMember:
    return add_org_member(org_id, payload, principal)


@router.post("/v4/orgs/{org_id}/libraries", response_model=Library)
def v4_create_library(
    org_id: str,
    payload: LibraryCreate,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> Library:
    return create_org_library(org_id, payload, principal)


@router.get("/v4/orgs/{org_id}/libraries", response_model=list[Library])
def v4_list_org_libraries(
    org_id: str,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> list[Library]:
    require_org_role(principal, org_id, "member")
    return [lib for lib in LibraryRepository().list_all() if lib.organization_id == org_id]


@router.put("/v4/libraries/{library_id}/access/{principal_id}")
def v4_grant_access(
    library_id: str,
    principal_id: str,
    payload: LibraryAccessGrantRequest,
    actor: ResolvedPrincipal = Depends(require_authenticated),
) -> dict:
    entry = grant_library_access_v4(library_id, principal_id, payload.role, actor)
    return entry.model_dump()


@router.get("/v4/libraries/{library_id}/access")
def v4_list_access(
    library_id: str,
    principal: ResolvedPrincipal = Depends(require_authenticated),
) -> list[dict]:
    from app.services.org_service import effective_libraries_v4

    role = effective_libraries_v4(principal, role_at_least="admin").get(library_id)
    if role != "admin" and not principal.is_admin_bypass:
        raise HTTPException(status_code=403, detail="library_admin_required")
    return [e.model_dump() for e in LibraryAccessRepository().list_by_library(library_id)]
