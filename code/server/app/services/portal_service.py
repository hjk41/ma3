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
    if settings.authing_configured and not settings.auth_admin_users:
        raise RuntimeError(
            "MA3_AUTH_ADMIN_USERS must list at least one product admin when MA3_AUTHING_ENABLED=1"
        )


__all__ = [
    "can_read_library",
    "entitled_library_ids",
    "is_library_owner",
    "list_entitled_libraries",
    "validate_authing_admin_config",
]
