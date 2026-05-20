"""Compatibility shim for v2 imports.

v3 auth lives in :mod:`app.core.auth`; this module re-exports the old helper
names so existing clients and route imports keep working during the transition.
"""

from app.core.auth import (  # noqa: F401
    ResolvedPrincipal,
    ResolvedToken,
    clear_sso_verify_cache,
    current_principal,
    effective_libraries,
    effective_permissions,
    effective_library_details,
    hash_token,
    has_permission,
    legacy_token_from_principal,
    primary_admin_library_id,
    primary_write_library_id,
    require_admin_key,
    require_permission,
    require_admin_role,
    require_authenticated,
    require_global_admin,
    require_library_admin,
    require_library_read,
    require_library_write,
    require_write_library_id,
    resolve_optional_token,
    resolve_principal,
    v3_write_library,
    verify_sso_cookie,
    role_assignments_for,
    _cookie_domain_for_host,
    _extract_raw,
    _is_admin_key,
    _resolve_from_raw_only,
)
