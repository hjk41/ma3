"""Library count quotas: plan limits (free/pro/team) and platform hard caps."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException

from app.core.config import settings
from app.services.onboarding_service import is_paid_principal
from app.storage import db

LibraryScope = Literal["personal", "team"]


def resolve_personal_plan_code(principal_id: str) -> str:
    return "pro" if is_paid_principal(principal_id) else "free"


def plan_max_libraries(*, plan_code: str, scope: LibraryScope) -> int:
    if scope == "personal":
        if plan_code == "pro":
            return settings.plan_max_libraries_pro
        return settings.plan_max_libraries_free
    if plan_code == "team":
        return settings.plan_max_libraries_team
    return settings.plan_max_libraries_free


def platform_max_libraries(scope: LibraryScope) -> int:
    if scope == "personal":
        return settings.platform_max_libraries_personal_org
    return settings.platform_max_libraries_team_org


def _quota_subject(*, library_id: str, kind: str, org_id: str | None) -> LibraryScope | None:
    """Return quota scope, or None when this library is exempt from count limits."""
    if library_id == settings.default_library_id:
        return None
    if kind == "personal":
        return "personal"
    oid = org_id or settings.default_org_id
    if oid == settings.default_org_id:
        return None
    return "team"


def library_quota_summary(
    *,
    scope: LibraryScope,
    used: int,
    plan_code: str,
) -> dict[str, Any]:
    plan_limit = plan_max_libraries(plan_code=plan_code, scope=scope)
    platform_limit = platform_max_libraries(scope)
    effective_limit = min(plan_limit, platform_limit)
    return {
        "scope": scope,
        "plan_code": plan_code,
        "used": used,
        "plan_limit": plan_limit,
        "platform_limit": platform_limit,
        "limit": effective_limit,
        "remaining": max(0, effective_limit - used),
    }


def assert_library_creation_allowed(
    *,
    library_id: str,
    kind: str,
    org_id: str | None,
    owner_principal_id: str | None,
    plan_code: str | None = None,
) -> None:
    """Raise HTTPException when creating this library would exceed quotas."""
    scope = _quota_subject(library_id=library_id, kind=kind, org_id=org_id)
    if scope is None:
        return

    if scope == "personal":
        if not owner_principal_id:
            return
        used = db.count_personal_libraries(owner_principal_id)
        code = plan_code or resolve_personal_plan_code(owner_principal_id)
    else:
        oid = org_id or settings.default_org_id
        used = db.count_org_libraries(oid)
        code = plan_code or "team"

    plan_limit = plan_max_libraries(plan_code=code, scope=scope)
    platform_limit = platform_max_libraries(scope)
    effective_limit = min(plan_limit, platform_limit)

    if used < effective_limit:
        return

    if used >= platform_limit:
        error = "platform_library_limit_exceeded"
        message = (
            f"platform library limit reached ({platform_limit} libraries per "
            f"{'personal account' if scope == 'personal' else 'organization'}). "
            "Contact the platform administrator."
        )
        limit = platform_limit
    else:
        error = "plan_library_limit_exceeded"
        if scope == "personal":
            message = (
                f"library limit reached for your {code} plan ({plan_limit} personal "
                f"{'library' if plan_limit == 1 else 'libraries'}). Upgrade to create more."
            )
        else:
            message = (
                f"library limit reached for this organization ({plan_limit} on {code} plan). "
                "Upgrade or delete an unused library."
            )
        limit = plan_limit

    raise HTTPException(
        status_code=403,
        detail={
            "error": error,
            "message": message,
            "scope": scope,
            "plan_code": code,
            "used": used,
            "limit": limit,
            "plan_limit": plan_limit,
            "platform_limit": platform_limit,
        },
    )
