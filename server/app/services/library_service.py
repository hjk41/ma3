import secrets as _secrets

from app.core.ids import new_id
from app.core.security import ResolvedPrincipal, ResolvedToken, effective_libraries, hash_token
from app.core.time import utc_now_iso
from app.models.library import (
    InviteCode,
    InviteCodeCreated,
    Library,
    LibraryCreate,
    TokenCreate,
    TokenCreated,
    UseInviteRequest,
    UseInviteResponse,
)
from app.storage.repositories import InviteCodeRepository, LibraryRepository, TokenRepository


def effective_library_ids(principal: ResolvedPrincipal | ResolvedToken | None, is_admin: bool = False) -> set[str]:
    """Return readable library ids for a v3 principal.

    ``ResolvedToken`` is accepted as a compatibility bridge for old call sites.
    """
    if isinstance(principal, ResolvedPrincipal):
        return set(effective_libraries(principal).keys())
    return accessible_library_ids(principal, is_admin=is_admin)


def accessible_library_ids(token: ResolvedToken | None, is_admin: bool = False) -> set[str]:
    """Return the set of library_ids this request may read from.

    Admin callers get access to all libraries (public and private).
    Library tokens get access to public libraries plus their own.
    Anonymous callers get access to public libraries only.
    """
    if is_admin:
        return {lib.library_id for lib in LibraryRepository().list_all()}
    ids = {lib.library_id for lib in LibraryRepository().list_public()}
    if token is not None:
        ids.add(token.library_id)
    return ids


def create_library(payload: LibraryCreate) -> Library:
    library = Library(
        library_id=new_id("lib"),
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
        parent_library_id=payload.parent_library_id,
        is_personal=payload.is_personal,
        created_at=utc_now_iso(),
    )
    LibraryRepository().insert(library)
    return library


def create_token(library_id: str, payload: TokenCreate) -> TokenCreated:
    raw = _secrets.token_urlsafe(32)
    token_id = new_id("tok")
    now = utc_now_iso()
    TokenRepository().insert(
        token_id=token_id,
        token_hash=hash_token(raw),
        library_id=library_id,
        label=payload.label,
        role=payload.role,
        created_at=now,
    )
    from app.core.auth import ensure_legacy_principal_for_token
    from app.models.library import TokenInfo

    ensure_legacy_principal_for_token(
        TokenInfo(
            token_id=token_id,
            library_id=library_id,
            label=payload.label,
            role=payload.role,
            created_at=now,
        ),
        hash_token(raw),
    )
    return TokenCreated(
        token_id=token_id,
        library_id=library_id,
        label=payload.label,
        role=payload.role,
        created_at=now,
        token=raw,
    )


def create_invite_code() -> InviteCodeCreated:
    raw = "invite_" + _secrets.token_urlsafe(24)
    code_id = new_id("inv")
    now = utc_now_iso()
    invite = InviteCode(code_id=code_id, created_at=now)
    InviteCodeRepository().insert(invite, hash_token(raw))
    return InviteCodeCreated(**invite.model_dump(), code=raw)


def use_invite_code(payload: UseInviteRequest) -> UseInviteResponse:
    repo = InviteCodeRepository()
    invite = repo.get_by_hash(hash_token(payload.code))
    if invite is None:
        raise ValueError("invalid invite code")
    if invite.used_at is not None:
        raise ValueError("invite code already used")
    library = create_library(LibraryCreate(
        name=payload.name,
        description=payload.description,
        is_public=False,
        parent_library_id=None,
        is_personal=True,
    ))
    created = create_token(library.library_id, TokenCreate(label="owner", role="admin"))
    repo.mark_used(invite.code_id, utc_now_iso(), library.library_id)
    return UseInviteResponse(
        library=library,
        token_id=created.token_id,
        token=created.token,
    )
