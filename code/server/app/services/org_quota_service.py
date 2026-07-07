"""Team org creation quotas (design/24 §12)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException

from app.core.config import settings
from app.services.onboarding_service import is_paid_principal
from app.storage import db

TeamCreationPlan = Literal["free", "pro", "admin"]


def resolve_team_creation_plan(principal_id: str) -> TeamCreationPlan:
    if is_paid_principal(principal_id):
        return "pro"
    return "free"


def plan_max_team_orgs_owned(plan_code: str) -> int:
    if plan_code == "pro":
        return settings.plan_max_team_orgs_owned_pro
    if plan_code == "admin":
        return settings.platform_max_team_orgs_owned
    return settings.plan_max_team_orgs_owned_free


def team_org_creation_summary(
    principal_id: str,
    *,
    is_product_admin: bool = False,
) -> dict[str, Any]:
    plan: TeamCreationPlan = "admin" if is_product_admin else resolve_team_creation_plan(principal_id)
    owned = db.count_team_orgs_owned(principal_id)
    plan_limit = plan_max_team_orgs_owned(plan)
    platform_limit = settings.platform_max_team_orgs_owned
    effective_limit = min(plan_limit, platform_limit)
    remaining = max(0, effective_limit - owned)
    allowed = owned < effective_limit
    reason = None
    if not allowed:
        reason = "upgrade_required" if plan_limit == 0 else "plan_limit_reached"
        if owned >= platform_limit:
            reason = "platform_limit_reached"
    return {
        "plan_code": plan,
        "owned": owned,
        "plan_limit": plan_limit,
        "platform_limit": platform_limit,
        "limit": effective_limit,
        "remaining": remaining,
        "allowed": allowed,
        "reason": reason,
    }


def assert_team_org_creation_allowed(
    principal_id: str,
    *,
    is_product_admin: bool = False,
) -> dict[str, Any]:
    summary = team_org_creation_summary(principal_id, is_product_admin=is_product_admin)
    if summary["allowed"]:
        return summary
    reason = summary.get("reason")
    if reason == "upgrade_required":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "team_org_upgrade_required",
                "message": "upgrade to Pro to create a team organization",
                "plan_code": summary["plan_code"],
            },
        )
    if reason == "platform_limit_reached":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "platform_team_org_limit_exceeded",
                "message": f"platform team org limit reached ({summary['platform_limit']})",
                "limit": summary["platform_limit"],
            },
        )
    raise HTTPException(
        status_code=403,
        detail={
            "error": "team_org_limit_reached",
            "message": (
                f"team organization limit reached for your {summary['plan_code']} plan "
                f"({summary['plan_limit']} allowed)"
            ),
            "plan_code": summary["plan_code"],
            "limit": summary["limit"],
            "owned": summary["owned"],
        },
    )
