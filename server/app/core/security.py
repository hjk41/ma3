import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings


@dataclass(slots=True)
class ResolvedToken:
    token_id: str
    library_id: str
    label: str
    role: str = "writer"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _extract_raw(
    x_api_key: str | None,
    authorization: str | None,
) -> str | None:
    if x_api_key:
        return x_api_key
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return None


def _is_admin_key(raw: str) -> bool:
    if not settings.api_key:
        return False
    return secrets.compare_digest(raw, settings.api_key)


def require_admin_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Require the global admin key. Used for library and token management."""
    if not settings.api_key:
        return
    raw = _extract_raw(x_api_key, authorization)
    if not raw or not _is_admin_key(raw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin key required",
            headers={"WWW-Authenticate": "Bearer"},
        )


def resolve_optional_token(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> ResolvedToken | None:
    """Resolve a library token if present. Returns None for unauthenticated or admin-key requests."""
    raw = _extract_raw(x_api_key, authorization)
    if not raw or _is_admin_key(raw):
        return None
    from app.storage.repositories import TokenRepository
    info = TokenRepository().get_by_hash(hash_token(raw))
    if info is None:
        return None
    return ResolvedToken(token_id=info.token_id, library_id=info.library_id, label=info.label, role=info.role)


_WRITE_ROLES = frozenset({"writer", "admin"})


def require_write_library_id(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> str | None:
    """
    Returns the library_id to write into.
    - Library token (writer or admin role) → its library_id
    - Admin key      → None  (writes to the legacy/unassigned namespace)
    - Reader token   → 403
    - No valid auth  → 401
    """
    raw = _extract_raw(x_api_key, authorization)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="library token or admin key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _is_admin_key(raw):
        return None
    from app.storage.repositories import TokenRepository
    info = TokenRepository().get_by_hash(hash_token(raw))
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if info.role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="reader tokens cannot write; use a writer or admin token",
        )
    return info.library_id


def require_admin_role(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> str | None:
    """Require global admin key OR an admin-role library token.

    Unlike ``require_library_admin``, this does not take a library_id path
    parameter — it is used on routes where the target library is determined
    from the record being acted on, not from the URL.

    Returns None for global admin, the token's library_id for an admin-role
    token.  Raises 401 if unauthenticated, 403 if role is insufficient.
    """
    raw = _extract_raw(x_api_key, authorization)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _is_admin_key(raw):
        return None
    from app.storage.repositories import TokenRepository
    info = TokenRepository().get_by_hash(hash_token(raw))
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if info.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin-role token required to manage records",
        )
    return info.library_id


def require_library_admin(
    library_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> str | None:
    """Allow global admin key OR an admin-role token for the specified library.

    Returns None for global admin, the token's library_id for an admin-role token.
    Raises 403 if the token has role='writer' or belongs to a different library.
    """
    raw = _extract_raw(x_api_key, authorization)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="library admin token or global admin key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _is_admin_key(raw):
        return None  # global admin — full access
    from app.storage.repositories import TokenRepository
    info = TokenRepository().get_by_hash(hash_token(raw))
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if info.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin-role token for this library required",
        )
    from app.storage.repositories import is_ancestor_or_self
    if not is_ancestor_or_self(info.library_id, library_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin-role token for this library required",
        )
    return info.library_id
