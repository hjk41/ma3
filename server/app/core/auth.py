from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import settings
from app.core.time import utc_now_iso
from app.models.auth import BUILTIN_ROLES, LIBRARY_ROLE_TO_ROLE, Permission, EffectiveLibrary, ROLE_ORDER, ROLE_TO_LIBRARY_ROLE, ResolvedPrincipal, RoleAssignment
from app.models.library import TokenInfo
from app.services.metrics_service import metrics
from app.storage.repositories import (
    ApiKeyRepository,
    LibraryAclRepository,
    LibraryRepository,
    PrincipalRepository,
    RoleAssignmentRepository,
    TokenRepository,
)


@dataclass(slots=True)
class ResolvedToken:
    token_id: str
    library_id: str
    label: str
    role: str = "writer"


_WRITE_ROLES = frozenset({"writer", "admin"})
_LIBRARY_ROLE_NAMES = {"library_reader", "library_writer", "library_admin"}
_ADMIN_PRINCIPAL = ResolvedPrincipal(
    principal_id="admin:root",
    kind="admin",
    display_name="ma3 root admin",
    via="admin_key",
    is_admin_bypass=True,
)
_ANONYMOUS_PRINCIPAL = ResolvedPrincipal(
    principal_id="anonymous",
    kind="anonymous",
    display_name="anonymous",
    via="anonymous",
    is_admin_bypass=False,
)


@dataclass(slots=True)
class VerifyResult:
    user: str
    display_name: str
    admin: bool = False
    exp: int | None = None


_verify_cache: OrderedDict[str, tuple[float, VerifyResult]] = OrderedDict()
_http_client: httpx.Client | None = None


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


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=settings.auth_verify_timeout_seconds)
    return _http_client


def _jwt_exp_unverified(jwt: str) -> int | None:
    try:
        parts = jwt.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def _cache_get(key: str) -> VerifyResult | None:
    now = time.time()
    item = _verify_cache.get(key)
    if not item:
        return None
    expires_at, result = item
    if expires_at <= now:
        _verify_cache.pop(key, None)
        return None
    _verify_cache.move_to_end(key)
    metrics.record_auth_verify("cache_hit")
    return result


def _cache_put(key: str, result: VerifyResult, jwt_exp: int | None) -> None:
    ttl = max(0, settings.auth_verify_cache_ttl_seconds)
    expires_at = time.time() + ttl
    if jwt_exp is not None:
        expires_at = min(expires_at, float(jwt_exp))
    if expires_at <= time.time():
        return
    _verify_cache[key] = (expires_at, result)
    _verify_cache.move_to_end(key)
    while len(_verify_cache) > settings.auth_verify_cache_max_entries:
        _verify_cache.popitem(last=False)


def clear_sso_verify_cache() -> None:
    _verify_cache.clear()


def _cookie_domain_for_host(host: str) -> str | None:
    hostname = (host or "").split(":", 1)[0].strip().lower()
    if hostname.endswith(".zhilicon.com"):
        return ".zhilicon.com"
    return None


def verify_sso_cookie(jwt: str) -> VerifyResult | None:
    if not settings.auth_verify_url:
        return None
    cache_key = hash_token(jwt)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    jwt_exp = _jwt_exp_unverified(jwt)
    started = time.perf_counter()
    try:
        resp = _http().get(settings.auth_verify_url, params={"token": jwt})
    except httpx.TimeoutException:
        metrics.record_auth_verify("timeout", time.perf_counter() - started)
        return None
    except httpx.HTTPError:
        metrics.record_auth_verify("network_error", time.perf_counter() - started)
        return None

    latency = time.perf_counter() - started
    if resp.status_code < 200 or resp.status_code >= 300:
        metrics.record_auth_verify("cache_miss_fail", latency)
        return None
    try:
        data = resp.json()
    except ValueError:
        metrics.record_auth_verify("cache_miss_fail", latency)
        return None
    if not data.get("valid") or not data.get("user"):
        metrics.record_auth_verify("cache_miss_fail", latency)
        return None
    result = VerifyResult(
        user=str(data["user"]),
        display_name=str(data.get("display_name") or data.get("name") or data["user"]),
        admin=bool(data.get("admin")),
        exp=int(data["exp"]) if data.get("exp") is not None else jwt_exp,
    )
    _cache_put(cache_key, result, result.exp)
    metrics.record_auth_verify("cache_miss_ok", latency)
    return result


def _principal_from_user_verify(result: VerifyResult) -> ResolvedPrincipal:
    principal = PrincipalRepository().upsert_user(
        result.user,
        result.display_name,
        is_admin=result.admin,
    )
    admin_bypass = bool(result.admin and result.user in settings.auth_admin_users)
    resolved = ResolvedPrincipal(
        principal_id=principal.principal_id,
        kind=principal.kind,
        display_name=principal.display_name,
        via="sso_cookie",
        is_admin_bypass=admin_bypass,
    )
    if admin_bypass:
        from app.services.auth_service import audit_auth_event

        audit_auth_event(
            actor_principal_id=principal.principal_id,
            action="principal.assume_admin",
            payload={"via": "sso_cookie"},
        )
    return resolved


def _expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    return expires_at <= utc_now_iso()


def _maybe_update_last_used(key_id: str, last_used_at: str | None) -> None:
    now = utc_now_iso()
    if last_used_at:
        try:
            previous = datetime.fromisoformat(last_used_at)
            current = datetime.fromisoformat(now)
            if (current - previous).total_seconds() < 60:
                return
        except ValueError:
            pass
    ApiKeyRepository().update_last_used_at(key_id, now)


def _legacy_lib_principal_id(library_id: str) -> str:
    return f"legacy:lib:{library_id}"


def ensure_legacy_principal_for_token(info: TokenInfo, token_hash: str | None = None) -> None:
    principals = PrincipalRepository()
    principals.upsert_legacy(
        _legacy_lib_principal_id(info.library_id),
        f"legacy library {info.library_id}",
        {"library_id": info.library_id},
    )
    principal_id = f"legacy:{info.token_id}"
    principals.upsert_legacy(
        principal_id,
        info.label or info.token_id,
        {"token_id": info.token_id, "library_id": info.library_id},
    )
    LibraryAclRepository().upsert(
        __import__("app.models.auth", fromlist=["AclEntry"]).AclEntry(
            library_id=info.library_id,
            principal_id=principal_id,
            role=info.role,
            granted_at=utc_now_iso(),
            granted_by=_legacy_lib_principal_id(info.library_id),
        )
    )
    if token_hash is not None and ApiKeyRepository().get_by_hash(token_hash) is None:
        from app.models.auth import ApiKeyInfo

        ApiKeyRepository().upsert(
            ApiKeyInfo(
                key_id=f"akey_legacy_{info.token_id}",
                principal_id=principal_id,
                label=f"v2 token: {info.label}",
                scope_libraries=[info.library_id],
                created_at=info.created_at,
                created_by=_legacy_lib_principal_id(info.library_id),
            ),
            token_hash,
        )


def _resolved_from_legacy_token(info: TokenInfo) -> ResolvedPrincipal:
    return ResolvedPrincipal(
        principal_id=f"legacy:{info.token_id}",
        kind="legacy",
        display_name=info.label,
        via="api_key",
        is_admin_bypass=False,
        token_id=info.token_id,
        library_id=info.library_id,
        label=info.label,
        role=info.role,
        api_key_scope=frozenset({info.library_id}),
    )


def _resolve_from_raw_only(raw: str | None) -> ResolvedPrincipal:
    if not raw:
        principal = _ANONYMOUS_PRINCIPAL
        metrics.record_auth_resolve(principal.via, principal.kind)
        return principal
    if _is_admin_key(raw):
        metrics.record_auth_resolve(_ADMIN_PRINCIPAL.via, _ADMIN_PRINCIPAL.kind)
        return _ADMIN_PRINCIPAL

    hashed = hash_token(raw)
    api_key_hit = ApiKeyRepository().get_by_hash(hashed)
    if api_key_hit is not None:
        info, principal = api_key_hit
        if info.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_revoked")
        if _expired(info.expires_at):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_expired")
        _maybe_update_last_used(info.key_id, info.last_used_at)
        resolved = ResolvedPrincipal(
            principal_id=principal.principal_id,
            kind=principal.kind,
            display_name=principal.display_name,
            via="api_key",
            is_admin_bypass=False,
            api_key_id=info.key_id,
            api_key_scope=frozenset(info.scope_libraries) if info.scope_libraries is not None else None,
        )
        # Preserve v2 compatibility fields for migrated tokens.
        if principal.kind == "legacy":
            acl = LibraryAclRepository().list_by_principal(principal.principal_id)
            if len(acl) == 1:
                object.__setattr__(resolved, "token_id", principal.principal_id.removeprefix("legacy:"))
                object.__setattr__(resolved, "library_id", acl[0].library_id)
                object.__setattr__(resolved, "label", info.label.removeprefix("v2 token: "))
                object.__setattr__(resolved, "role", acl[0].role)
        metrics.record_auth_resolve(resolved.via, resolved.kind)
        return resolved

    token_info = TokenRepository().get_by_hash(hashed)
    if token_info is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="auth_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ensure_legacy_principal_for_token(token_info, hashed)
    resolved = _resolved_from_legacy_token(token_info)
    metrics.record_auth_resolve(resolved.via, resolved.kind)
    return resolved


def _cookie_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.cookies.get(settings.auth_jwt_cookie)


def resolve_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> ResolvedPrincipal:
    raw = _extract_raw(x_api_key, authorization)
    cookie_token = _cookie_from_request(request)
    if raw:
        principal = _resolve_from_raw_only(raw)
        if principal.kind != "admin" and cookie_token:
            verified = verify_sso_cookie(cookie_token)
            if verified and principal.kind == "user" and principal.principal_id != f"user:{verified.user}":
                raise HTTPException(status_code=400, detail="auth_conflict")
        return principal

    if cookie_token:
        verified = verify_sso_cookie(cookie_token)
        if verified is not None:
            principal = _principal_from_user_verify(verified)
            metrics.record_auth_resolve(principal.via, principal.kind)
            return principal

    principal = _ANONYMOUS_PRINCIPAL
    metrics.record_auth_resolve(principal.via, principal.kind)
    return principal


def current_principal(principal: ResolvedPrincipal = Depends(resolve_principal)) -> ResolvedPrincipal:
    return principal


def require_authenticated(principal: ResolvedPrincipal = Depends(resolve_principal)) -> ResolvedPrincipal:
    if principal.kind == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_global_admin(principal: ResolvedPrincipal = Depends(resolve_principal)) -> ResolvedPrincipal:
    if not principal.is_admin_bypass:
        metrics.record_auth_403("admin_required")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return principal


def _stronger_role(existing: str | None, new: str) -> str:
    if existing is None or ROLE_ORDER[new] > ROLE_ORDER[existing]:
        return new
    return existing


def _assignment_library_role(assignment: RoleAssignment) -> str | None:
    if assignment.scope_type != "library" or not assignment.scope_id:
        return None
    return ROLE_TO_LIBRARY_ROLE.get(assignment.role_name)


def role_assignments_for(principal_id: str) -> list[RoleAssignment]:
    if principal_id in {"anonymous", "admin:root"}:
        return []
    return RoleAssignmentRepository().list_by_principal(principal_id)


def effective_permissions(principal: ResolvedPrincipal, library_id: str | None = None) -> set[str]:
    if principal.is_admin_bypass:
        return {"*"}
    perms: set[str] = set()
    if principal.kind == "anonymous":
        return perms
    assigned_for_library = False
    for assignment in role_assignments_for(principal.principal_id):
        role_perms = BUILTIN_ROLES.get(assignment.role_name, [])
        if assignment.scope_type == "system":
            perms.update(role_perms)
        elif assignment.scope_type == "library" and assignment.scope_id == library_id:
            perms.update(role_perms)
            assigned_for_library = True
    if library_id is not None and not assigned_for_library and principal.kind != "anonymous":
        # Transitional fallback for v2/v3 legacy credentials before RBAC migration.
        for entry in LibraryAclRepository().list_by_principal(principal.principal_id):
            if entry.library_id == library_id:
                perms.update(BUILTIN_ROLES.get(LIBRARY_ROLE_TO_ROLE.get(entry.role, ""), []))
                break
    return perms


def has_permission(principal: ResolvedPrincipal, perm: Permission | str, *, library_id: str | None = None) -> bool:
    wanted = perm.value if isinstance(perm, Permission) else str(perm)
    perms = effective_permissions(principal, library_id)
    return "*" in perms or wanted in perms


def require_permission(principal: ResolvedPrincipal, perm: Permission | str, *, library_id: str | None = None) -> None:
    wanted = perm.value if isinstance(perm, Permission) else str(perm)
    if not has_permission(principal, wanted, library_id=library_id):
        metrics.record_auth_403("permission_denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "permission_denied", "missing": wanted, "library": library_id},
        )


def effective_libraries(principal: ResolvedPrincipal, role_at_least: str = "reader") -> dict[str, str]:
    if principal.is_admin_bypass:
        return {
            lib.library_id: "admin"
            for lib in LibraryRepository().list_all()
            if ROLE_ORDER["admin"] >= ROLE_ORDER[role_at_least]
        }

    roles: dict[str, str] = {}
    for lib in LibraryRepository().list_public():
        roles[lib.library_id] = _stronger_role(roles.get(lib.library_id), "reader")

    if principal.kind != "anonymous":
        assignments = RoleAssignmentRepository().list_by_principal(principal.principal_id)
        assigned_libs: set[str] = set()
        for assignment in assignments:
            role = _assignment_library_role(assignment)
            if role and assignment.scope_id:
                roles[assignment.scope_id] = _stronger_role(roles.get(assignment.scope_id), role)
                assigned_libs.add(assignment.scope_id)
        # Transitional fallback: legacy library_acl rows still count when no
        # v3.1 assignment exists for that principal/library.
        for entry in LibraryAclRepository().list_by_principal(principal.principal_id):
            if entry.library_id not in assigned_libs:
                roles[entry.library_id] = _stronger_role(roles.get(entry.library_id), entry.role)

    if principal.api_key_scope is not None:
        roles = {lib_id: role for lib_id, role in roles.items() if lib_id in principal.api_key_scope}

    return {
        lib_id: role
        for lib_id, role in roles.items()
        if ROLE_ORDER[role] >= ROLE_ORDER[role_at_least]
    }

def effective_library_details(principal: ResolvedPrincipal) -> list[EffectiveLibrary]:
    roles = effective_libraries(principal)
    explicit: dict[str, str] = {}
    if principal.kind not in {"anonymous", "admin"}:
        for assignment in RoleAssignmentRepository().list_by_principal(principal.principal_id):
            role = _assignment_library_role(assignment)
            if role and assignment.scope_id:
                explicit[assignment.scope_id] = role
        for entry in LibraryAclRepository().list_by_principal(principal.principal_id):
            explicit.setdefault(entry.library_id, entry.role)
    libs = {lib.library_id: lib for lib in LibraryRepository().list_all()}
    out: list[EffectiveLibrary] = []
    for lib_id, role in sorted(roles.items()):
        lib = libs.get(lib_id)
        if principal.is_admin_bypass:
            source = "admin"
        elif principal.api_key_scope is not None and lib_id in principal.api_key_scope:
            source = "scope"
        elif lib_id in explicit:
            source = "acl"
        else:
            source = "public"
        out.append(
            EffectiveLibrary(
                library_id=lib_id,
                role=role,
                source=source,
                name=lib.name if lib else None,
                is_public=lib.is_public if lib else None,
            )
        )
    return out


def primary_write_library_id(principal: ResolvedPrincipal) -> str | None:
    if principal.is_admin_bypass:
        return None
    if principal.kind == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="library token or admin key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    writable = effective_libraries(principal, role_at_least="writer")
    if not writable:
        metrics.record_auth_403("write_missing")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="writer role required")
    if len(writable) == 1:
        return next(iter(writable))
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "auth_ambiguous_target_library",
            "writable_libraries": sorted(writable),
        },
    )


def v3_write_library(principal: ResolvedPrincipal = Depends(resolve_principal)) -> str | None:
    return primary_write_library_id(principal)


def require_write_library_id(principal: ResolvedPrincipal = Depends(resolve_principal)) -> str | None:
    return primary_write_library_id(principal)


def primary_admin_library_id(principal: ResolvedPrincipal) -> str | None:
    if principal.is_admin_bypass:
        return None
    if principal.kind == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    admin_libs = effective_libraries(principal, role_at_least="admin")
    if not admin_libs:
        metrics.record_auth_403("admin_missing")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin-role token required")
    if len(admin_libs) == 1:
        return next(iter(admin_libs))
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "auth_ambiguous_admin_library", "admin_libraries": sorted(admin_libs)},
    )


def require_admin_role(principal: ResolvedPrincipal = Depends(resolve_principal)) -> str | None:
    return primary_admin_library_id(principal)


def require_library_read(
    library_id: str,
    principal: ResolvedPrincipal = Depends(resolve_principal),
) -> str:
    roles = effective_libraries(principal)
    role = roles.get(library_id)
    if role is None:
        lib = LibraryRepository().get(library_id)
        if principal.kind == "anonymous" and (lib is None or not lib.is_public):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        metrics.record_auth_403("acl_missing")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="reader role required")
    return role


def require_library_write(
    library_id: str,
    principal: ResolvedPrincipal = Depends(resolve_principal),
) -> str:
    role = require_library_read(library_id, principal)
    if not has_permission(principal, Permission.RECORD_WRITE, library_id=library_id):
        metrics.record_auth_403("write_missing")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="writer role required")
    return role


def require_library_admin(
    library_id: str,
    principal: ResolvedPrincipal = Depends(resolve_principal),
) -> str | None:
    if principal.is_admin_bypass:
        return None
    require_library_read(library_id, principal)
    if not has_permission(principal, Permission.LIBRARY_MANAGE_ACL, library_id=library_id):
        metrics.record_auth_403("admin_missing")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin-role token for this library required")
    return library_id


def require_admin_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
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
    principal: ResolvedPrincipal = Depends(resolve_principal),
) -> ResolvedToken | None:
    if principal.kind == "legacy" and principal.token_id and principal.library_id:
        return ResolvedToken(
            token_id=principal.token_id,
            library_id=principal.library_id,
            label=principal.label or principal.token_id,
            role=principal.role or "writer",
        )
    return None


def legacy_token_from_principal(principal: ResolvedPrincipal) -> ResolvedToken | None:
    if principal.kind == "legacy" and principal.token_id and principal.library_id:
        return ResolvedToken(
            token_id=principal.token_id,
            library_id=principal.library_id,
            label=principal.label or principal.token_id,
            role=principal.role or "writer",
        )
    return None
