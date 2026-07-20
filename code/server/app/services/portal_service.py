"""User portal entitlement and library presentation helpers."""
from __future__ import annotations

from app.core.config import settings
from app.services.entitlement_service import (
    can_read_library,
    entitled_library_ids,
    is_library_owner,
    list_entitled_libraries,
)


def validate_authing_admin_config() -> None:
    """Require admin allowlist when OIDC (including Authing) is enabled."""
    if settings.oidc_configured and not settings.auth_admin_users:
        raise RuntimeError(
            "MA3_AUTH_ADMIN_USERS must list at least one product admin when OIDC is enabled "
            "(MA3_OIDC_* or MA3_AUTHING_*)"
        )


# Back-compat alias
validate_oidc_admin_config = validate_authing_admin_config


__all__ = [
    "can_read_library",
    "entitled_library_ids",
    "is_library_owner",
    "list_entitled_libraries",
    "validate_authing_admin_config",
    "validate_oidc_admin_config",
]
