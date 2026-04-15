from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.security import (
    _extract_raw,
    _is_admin_key,
    hash_token,
    require_admin_key,
    require_library_admin,
    require_write_library_id,
    resolve_optional_token,
    ResolvedToken,
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
from app.services.library_service import (
    create_invite_code,
    create_library,
    create_token,
    use_invite_code,
)
from app.storage.repositories import (
    InviteCodeRepository,
    LibraryRepository,
    RecordRepository,
    TokenRepository,
)


router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("/whoami", response_model=dict)
def whoami(
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Return identity info for the current credential."""
    raw = _extract_raw(x_api_key, authorization)
    if raw and _is_admin_key(raw):
        return {"type": "admin"}
    if token is not None:
        lib = LibraryRepository().get(token.library_id)
        return {
            "type": "library_token",
            "token_id": token.token_id,
            "label": token.label,
            "role": token.role,
            "library": lib.model_dump() if lib else {"library_id": token.library_id},
        }
    return {"type": "anonymous"}


@router.post("", response_model=Library)
def post_library(
    payload: LibraryCreate,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> Library:
    """Create a library.

    - Global admin: can set any parent_library_id or none.
    - Admin-role token: creates a child library under the token's own library.
      The payload's parent_library_id is ignored; parent is always the token's library.
    """
    raw = _extract_raw(x_api_key, authorization)
    if not raw:
        raise HTTPException(status_code=401, detail="authentication required")
    if _is_admin_key(raw):
        return create_library(payload)
    from app.storage.repositories import TokenRepository
    info = TokenRepository().get_by_hash(hash_token(raw))
    if info is None:
        raise HTTPException(status_code=401, detail="invalid token")
    if info.role != "admin":
        raise HTTPException(status_code=403, detail="admin-role token required to create libraries")
    child_payload = payload.model_copy(update={"parent_library_id": info.library_id})
    return create_library(child_payload)


@router.delete("/{library_id}", status_code=204)
def delete_library(
    library_id: str,
    _: str | None = Depends(require_library_admin),
) -> None:
    """Delete a library, its tokens, and its records.

    Requires admin-role token for this library (or an ancestor) or global admin key.
    Returns 409 if the library still has child libraries — delete children first.
    """
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
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> list[Library]:
    """Public: returns only public libraries. Admin key: returns all."""
    raw = _extract_raw(x_api_key, authorization)
    if raw and _is_admin_key(raw):
        return LibraryRepository().list_all()
    return LibraryRepository().list_public()


@router.get("/{library_id}", response_model=Library)
def get_library(library_id: str) -> Library:
    lib = LibraryRepository().get(library_id)
    if lib is None or not lib.is_public:
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
    library_id_from_token: str | None = Depends(require_write_library_id),
) -> list[Record]:
    """List all draft records in this library (pending human review)."""
    lib = LibraryRepository().get(library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail="library not found")
    if library_id_from_token is not None and library_id_from_token != library_id:
        raise HTTPException(status_code=403, detail="token does not belong to this library")
    all_records = RecordRepository().list_by_library(library_id)
    return [r for r in all_records if r.status == RecordStatus.draft]


# ── Invite codes ────────────────────────────────────────────────────────────

invites_router = APIRouter(prefix="/invites", tags=["invites"])


@invites_router.post("", response_model=InviteCodeCreated)
def create_invite(
    _: None = Depends(require_admin_key),
) -> InviteCodeCreated:
    """Create a one-time invite code (global admin only).
    The raw code is shown once and never stored — save it immediately.
    """
    return create_invite_code()


@router.post("/from-invite", response_model=UseInviteResponse)
def post_library_from_invite(payload: UseInviteRequest) -> UseInviteResponse:
    """Create a personal private library using an invite code.

    No auth required — the invite code IS the credential.
    Returns the library and its owner admin token (shown once — save it).
    """
    try:
        return use_invite_code(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
