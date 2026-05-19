from fastapi import APIRouter, Depends, HTTPException

from app.core.security import (
    ResolvedPrincipal,
    current_principal,
    legacy_token_from_principal,
    require_admin_key,
    require_library_admin,
    require_library_write,
)
from app.models.library import (
    InviteCodeCreated,
    Library,
    LibraryCreate,
    TokenCreate,
    TokenCreated,
    TokenInfo,
    UseInviteRequest,
    UseInviteResponse,
)
from app.models.record import Record
from app.models.enums import RecordStatus
from app.services.auth_service import bootstrap_library_admin
from app.services.library_service import (
    create_invite_code,
    create_library,
    create_token,
    use_invite_code,
)
from app.storage.repositories import (
    LibraryRepository,
    RecordRepository,
    TokenRepository,
)


router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("/whoami", response_model=dict)
def whoami(
    principal: ResolvedPrincipal = Depends(current_principal),
) -> dict:
    """Return identity info for the current credential."""
    if principal.is_admin_bypass:
        return {"type": "admin", "principal_id": principal.principal_id}
    token = legacy_token_from_principal(principal)
    if token is not None:
        lib = LibraryRepository().get(token.library_id)
        return {
            "type": "library_token",
            "token_id": token.token_id,
            "label": token.label,
            "role": token.role,
            "library": lib.model_dump() if lib else {"library_id": token.library_id},
            "principal_id": principal.principal_id,
        }
    if principal.kind != "anonymous":
        return {
            "type": principal.kind,
            "principal_id": principal.principal_id,
            "label": principal.display_name,
        }
    return {"type": "anonymous", "principal_id": principal.principal_id}


@router.post("", response_model=Library)
def post_library(
    payload: LibraryCreate,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> Library:
    """Create a library.

    - Global admin: can set any parent_library_id or none.
    - Legacy admin-role token: creates a child library under the token's own library.
    - v3 SSO/API key principal: creates a flat library and receives admin ACL.
    """
    if principal.kind == "anonymous":
        raise HTTPException(status_code=401, detail="authentication required")
    token = legacy_token_from_principal(principal)
    if principal.is_admin_bypass:
        return create_library(payload)
    if token is not None:
        if token.role != "admin":
            raise HTTPException(status_code=403, detail="admin-role token required to create libraries")
        child_payload = payload.model_copy(update={"parent_library_id": token.library_id})
        return create_library(child_payload)
    flat_payload = payload.model_copy(update={"parent_library_id": None})
    lib = create_library(flat_payload)
    bootstrap_library_admin(lib.library_id, principal.principal_id, actor=principal)
    return lib


@router.delete("/{library_id}", status_code=204)
def delete_library(
    library_id: str,
    _: str | None = Depends(require_library_admin),
) -> None:
    """Delete a library, its tokens, and its records."""
    children = LibraryRepository().list_children(library_id)
    if children:
        raise HTTPException(
            status_code=409,
            detail=f"library has {len(children)} child library/libraries; delete them first",
        )
    RecordRepository().delete_by_library(library_id)
    TokenRepository().delete_by_library(library_id)
    deleted = LibraryRepository().delete(library_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="library not found")


@router.get("", response_model=list[Library])
def list_libraries(
    principal: ResolvedPrincipal = Depends(current_principal),
) -> list[Library]:
    """Return libraries visible to the caller."""
    if principal.is_admin_bypass:
        return LibraryRepository().list_all()
    from app.core.security import effective_libraries

    allowed = set(effective_libraries(principal))
    return [lib for lib in LibraryRepository().list_all() if lib.library_id in allowed]


@router.get("/{library_id}", response_model=Library)
def get_library(
    library_id: str,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> Library:
    lib = LibraryRepository().get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library not found")
    if principal.is_admin_bypass or lib.is_public:
        return lib
    from app.core.security import effective_libraries

    if library_id not in effective_libraries(principal):
        raise HTTPException(status_code=404, detail="library not found")
    return lib


@router.post("/{library_id}/tokens", response_model=TokenCreated)
def post_token(
    library_id: str,
    payload: TokenCreate,
    _: str | None = Depends(require_library_admin),
) -> TokenCreated:
    lib = LibraryRepository().get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library not found")
    return create_token(library_id, payload)


@router.get("/{library_id}/tokens", response_model=list[TokenInfo])
def list_tokens(
    library_id: str,
    _: str | None = Depends(require_library_admin),
) -> list[TokenInfo]:
    lib = LibraryRepository().get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library not found")
    return TokenRepository().list_by_library(library_id)


@router.delete("/{library_id}/tokens/{token_id}", status_code=204)
def delete_token(
    library_id: str,
    token_id: str,
    _: str | None = Depends(require_library_admin),
) -> None:
    deleted = TokenRepository().delete(token_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="token not found")


@router.get("/{library_id}/drafts", response_model=list[Record])
def list_drafts(
    library_id: str,
    _: str = Depends(require_library_write),
) -> list[Record]:
    """List all draft records in this library (pending human review)."""
    lib = LibraryRepository().get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library not found")
    all_records = RecordRepository().list_by_library(library_id)
    return [r for r in all_records if r.status == RecordStatus.draft]


# ── Invite codes ────────────────────────────────────────────────────────────

invites_router = APIRouter(prefix="/invites", tags=["invites"])


@invites_router.post("", response_model=InviteCodeCreated)
def create_invite(
    _: None = Depends(require_admin_key),
) -> InviteCodeCreated:
    """Create a one-time invite code (global admin only)."""
    return create_invite_code()


@router.post("/from-invite", response_model=UseInviteResponse)
def post_library_from_invite(payload: UseInviteRequest) -> UseInviteResponse:
    """Create a personal private library using an invite code."""
    try:
        return use_invite_code(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
