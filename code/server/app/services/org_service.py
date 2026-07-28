"""Organization membership: search, add/remove members, last-admin protection."""
from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import HTTPException

from app.services.org_quota_service import assert_team_org_creation_allowed, team_org_creation_summary
from app.storage import db

OrgMemberRole = Literal["admin", "member"]

# Ratified D3=B: new team org libraries default to private (confirm in UI before org/public).
DEFAULT_TEAM_LIBRARY_VISIBILITY = "private"

_ORG_NAME_RE = re.compile(r"^[^\x00-\x1f\x7f]+$", re.UNICODE)
_ALIAS_RE = re.compile(r"^[^\x00-\x1f\x7f]+$", re.UNICODE)


def normalize_org_name(raw: str) -> str:
    name = " ".join(str(raw or "").strip().split())
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="organization name must be at least 2 characters")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="organization name must be at most 80 characters")
    if not _ORG_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="organization name contains invalid characters")
    return name


def normalize_org_alias(raw: str | None, *, allow_empty: bool = False) -> str | None:
    """Normalize org-local alias. Empty clears when allow_empty=True; otherwise None means unset."""
    if raw is None:
        return None
    name = " ".join(str(raw).strip().split())
    if not name:
        if allow_empty:
            return None
        raise HTTPException(status_code=400, detail="alias must not be empty")
    if len(name) < 1 or len(name) > 32:
        raise HTTPException(status_code=400, detail="alias must be 1–32 characters")
    if not _ALIAS_RE.match(name):
        raise HTTPException(status_code=400, detail="alias contains invalid characters")
    return name


def assert_org_alias_available(
    org_id: str,
    alias: str,
    *,
    exclude_principal_id: str | None = None,
) -> None:
    clash = db.find_active_org_member_by_alias(
        org_id, alias, exclude_principal_id=exclude_principal_id
    )
    if clash:
        raise HTTPException(
            status_code=409,
            detail={"error": "alias_taken", "message": "that org alias is already in use"},
        )


def search_members_by_display_name(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Member picker search: display name prefix/substring; optional user:… principal prefix."""
    return db.search_users_by_display_name(query, limit=limit)


def resolve_member_principal_id(
    *,
    principal_id: str | None = None,
    display_name: str | None = None,
    username: str | None = None,
) -> str:
    """Resolve add-member target from principal_id, local username, or exact display name."""
    pid = str(principal_id or "").strip()
    if pid:
        if not db.get_user_principal(pid):
            raise HTTPException(status_code=404, detail="principal not found")
        return pid

    uname = str(username or "").strip().lower()
    if uname:
        account = db.get_local_account(uname)
        if account is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "member_not_found", "message": "no local account with that username"},
            )
        return str(account["principal_id"])

    name = " ".join(str(display_name or "").strip().split())
    if not name:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "member_target_required",
                "message": "principal_id, username, or display_name is required",
            },
        )
    row = db.find_user_by_display_name(name)
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"error": "member_not_found", "message": "no user with that display name"},
        )
    return str(row["principal_id"])


def assert_org_admin(org_id: str, actor_principal_id: str) -> None:
    member = db.get_org_member(org_id, actor_principal_id)
    if not member or member.get("seat_status") != "active" or member.get("role") != "admin":
        raise HTTPException(status_code=404, detail="organization not found")


def assert_active_org_member(org_id: str, principal_id: str) -> dict[str, Any]:
    member = db.get_org_member(org_id, principal_id)
    if not member or member.get("seat_status") != "active":
        raise HTTPException(status_code=404, detail="organization not found")
    return member


def _assert_not_last_admin(org_id: str, target_principal_id: str) -> None:
    target = db.get_org_member(org_id, target_principal_id)
    if not target or target.get("seat_status") != "active" or target.get("role") != "admin":
        return
    if db.count_active_org_admins(org_id) <= 1:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "last_org_admin",
                "message": "cannot remove or demote the only organization admin",
            },
        )


def add_org_member(
    *,
    org_id: str,
    actor_principal_id: str,
    principal_id: str | None = None,
    display_name: str | None = None,
    username: str | None = None,
    role: OrgMemberRole = "member",
    alias: str | None = None,
) -> dict[str, Any]:
    assert_org_admin(org_id, actor_principal_id)
    if not db.get_organization(org_id):
        raise HTTPException(status_code=404, detail="organization not found")
    target_id = resolve_member_principal_id(
        principal_id=principal_id,
        display_name=display_name,
        username=username,
    )
    normalized_alias = normalize_org_alias(alias) if alias is not None else None
    if normalized_alias:
        assert_org_alias_available(org_id, normalized_alias, exclude_principal_id=target_id)
    return db.add_org_member(
        org_id=org_id,
        principal_id=target_id,
        role=role,
        alias=normalized_alias,
    )


def update_org_member(
    *,
    org_id: str,
    actor_principal_id: str,
    target_principal_id: str,
    role: OrgMemberRole | None = None,
    alias: str | None = None,
    alias_provided: bool = False,
) -> dict[str, Any]:
    assert_org_admin(org_id, actor_principal_id)
    assert_active_org_member(org_id, target_principal_id)
    row: dict[str, Any] | None = None
    if role is not None:
        if role != "admin":
            _assert_not_last_admin(org_id, target_principal_id)
        row = db.set_org_member_role(org_id=org_id, principal_id=target_principal_id, role=role)
    if alias_provided:
        normalized = normalize_org_alias(alias, allow_empty=True)
        if normalized:
            assert_org_alias_available(
                org_id, normalized, exclude_principal_id=target_principal_id
            )
        row = db.set_org_member_alias(
            org_id=org_id, principal_id=target_principal_id, alias=normalized
        )
    if row is None:
        row = db.get_org_member(org_id, target_principal_id)
        if row is None:
            raise HTTPException(status_code=404, detail="organization not found")
    return row


def update_org_member_role(
    *,
    org_id: str,
    actor_principal_id: str,
    target_principal_id: str,
    role: OrgMemberRole,
) -> dict[str, Any]:
    return update_org_member(
        org_id=org_id,
        actor_principal_id=actor_principal_id,
        target_principal_id=target_principal_id,
        role=role,
    )


def remove_org_member(
    *,
    org_id: str,
    actor_principal_id: str,
    target_principal_id: str,
) -> None:
    assert_org_admin(org_id, actor_principal_id)
    assert_active_org_member(org_id, target_principal_id)
    _assert_not_last_admin(org_id, target_principal_id)
    db.mark_org_member_removed(org_id=org_id, principal_id=target_principal_id)


def seed_team_org(*, name: str, admin_principal_id: str) -> dict[str, Any]:
    """Test/dev helper: create team org bypassing plan gate."""
    return _create_team_org_record(name=normalize_org_name(name), owner_principal_id=admin_principal_id, plan_code="pro")


def create_team_org(
    *,
    name: str,
    owner_principal_id: str,
    is_product_admin: bool = False,
) -> dict[str, Any]:
    """Create a team org for an eligible owner (Phase O5)."""
    summary = assert_team_org_creation_allowed(owner_principal_id, is_product_admin=is_product_admin)
    org_name = normalize_org_name(name)
    plan_code = str(summary["plan_code"])
    billing_account_id = f"plan:{plan_code}"
    return _create_team_org_record(
        name=org_name,
        owner_principal_id=owner_principal_id,
        plan_code=plan_code,
        billing_account_id=billing_account_id,
    )


def _create_team_org_record(
    *,
    name: str,
    owner_principal_id: str,
    plan_code: str,
    billing_account_id: str | None = None,
) -> dict[str, Any]:
    org_id = db.new_id("org")
    org = db.create_organization(
        org_id,
        name=name,
        kind="team",
        owner_principal_id=owner_principal_id,
        billing_account_id=billing_account_id or f"plan:{plan_code}",
    )
    db.add_org_member(org_id=org_id, principal_id=owner_principal_id, role="admin")
    return org


def org_plan_label(org: dict[str, Any], *, locale: str) -> str:
    billing = str(org.get("billing_account_id") or "")
    if billing.startswith("plan:"):
        code = billing.removeprefix("plan:")
        if code == "pro":
            return "Pro" if locale == "en-US" else "Pro"
        if code == "free":
            return "Free" if locale == "en-US" else "免费"
        if code == "team":
            return "Team" if locale == "en-US" else "Team"
        return code
    if billing:
        return billing
    return "—"


def org_card_label(org: dict[str, Any], *, locale: str) -> str:
    kind = str(org.get("kind") or "custom")
    if kind == "personal":
        return "Personal account" if locale == "en-US" else "个人账户"
    return str(org.get("name") or org.get("id") or "")

