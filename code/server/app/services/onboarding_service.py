"""Self-service onboarding: personal library provisioning and API key issuance."""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any, Literal

from fastapi import HTTPException

from app.core.config import settings
from app.services import api_key_service
from app.services.api_key_encryption import encrypt_stored_key
from app.storage import db

logger = logging.getLogger(__name__)

PERSONAL_LIB_PREFIX = "lib_personal_"
PERSONAL_ORG_PREFIX = "org_personal_"
KEY_ROLES = frozenset({"reader", "writer"})
GrantRoleChoice = Literal["none", "reader", "writer"]


def personal_library_id(principal_id: str) -> str:
    return PERSONAL_LIB_PREFIX + hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:12]


def personal_org_id(principal_id: str) -> str:
    return PERSONAL_ORG_PREFIX + hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:12]


def is_paid_principal(principal_id: str) -> bool:
    """True if principal is Pro via env whitelist or billing projection."""
    if principal_id in settings.paid_principal_ids:
        return True
    try:
        return db.get_principal_plan_code(principal_id) == "pro"
    except Exception:
        logger.exception("failed to read principal plan_code for %s", principal_id)
        return False


def set_user_paid(*, principal_id: str, paid: bool) -> dict[str, Any]:
    """Ops helper: persist free/pro on the user principal (Observatory)."""
    code = "pro" if paid else "free"
    if not db.get_user_principal(principal_id):
        raise HTTPException(status_code=404, detail=f"principal not found: {principal_id}")
    org_id = personal_org_id(principal_id)
    org = db.get_organization(org_id)
    if org:
        from app.services import billing_service

        account = billing_service.ensure_org_billing_account(org_id, plan_code=code)
        billing_service.set_billing_account_plan(account["id"], plan_code=code)
        # Retain the legacy projection for older Observatory callers. The BA
        # remains authoritative and the bootstrap/backfill converts this label
        # back to its real id on the next initialization pass.
        db.set_organization_billing_account_id(org_id, f"plan:{code}")
    else:
        db.set_principal_plan_code(principal_id, code)
    return {
        "principal_id": principal_id,
        "plan_code": code,
        "paid": paid,
        "effective_paid": is_paid_principal(principal_id),
        "env_whitelist": principal_id in settings.paid_principal_ids,
    }


def ensure_personal_org(principal_id: str, display_name: str) -> dict[str, Any]:
    """Idempotent personal org + admin membership; links personal library to org."""
    org_id = personal_org_id(principal_id)
    org_name = f"{display_name} 的个人账户" if display_name else "Personal account"
    existing = db.get_organization(org_id)
    if not existing:
        db.create_organization(
            org_id,
            name=org_name,
            kind="personal",
            owner_principal_id=principal_id,
        )
        db.add_org_member(org_id=org_id, principal_id=principal_id, role="admin")
    from app.services import billing_service
    billing_service.ensure_org_billing_account(
        org_id, plan_code="pro" if is_paid_principal(principal_id) else "free"
    )
    lib = ensure_personal_library(principal_id, display_name, org_id=org_id)
    return {
        "org_id": org_id,
        "name": org_name,
        "kind": "personal",
        "personal_library_id": lib["library_id"],
    }


def ensure_personal_library(
    principal_id: str,
    display_name: str,
    *,
    org_id: str | None = None,
) -> dict[str, Any]:
    """Idempotent: find by (kind=personal, owner) first; create deterministically otherwise."""
    lib_name = f"{display_name} 的个人库"
    target_org = org_id or personal_org_id(principal_id)
    existing = db.find_personal_library(principal_id)
    if existing:
        if existing.get("name") != lib_name:
            db.set_library_name(str(existing["library_id"]), lib_name)
            existing = db.find_personal_library(principal_id) or existing
        if str(existing.get("org_id") or "") != target_org:
            db.set_library_org_id(str(existing["library_id"]), target_org)
            existing = db.find_personal_library(principal_id) or existing
        return existing
    target_id = personal_library_id(principal_id)
    try:
        created = db.ensure_library(
            target_id,
            name=lib_name,
            visibility="private",
            org_id=target_org,
            kind="personal",
            owner_principal_id=principal_id,
        )
    except Exception:
        found = db.find_personal_library(principal_id)
        if found:
            return found
        raise
    return _format_library(created)


def _format_library(row: dict[str, Any]) -> dict[str, Any]:
    if "library_id" in row:
        return row
    return {
        "library_id": row["id"],
        "name": row["name"],
        "visibility": row.get("visibility"),
        "kind": row.get("kind"),
        "owner_principal_id": row.get("owner_principal_id"),
    }


def normalize_key_label(label: str | None) -> str:
    text = (label or "").strip().replace("\n", " ").replace("\r", " ")
    if not text:
        return "agent-key"
    return text[:120]


def default_key_grants(personal_library_id: str) -> list[dict[str, str]]:
    return [
        {"library_id": personal_library_id, "role": "writer"},
        {"library_id": settings.default_library_id, "role": "writer"},
    ]


def resolve_key_grants(
    *,
    personal_library_id: str,
    personal_role: GrantRoleChoice,
    community_role: GrantRoleChoice,
    principal_id: str,
) -> list[dict[str, str]]:
    paid = is_paid_principal(principal_id)
    if not paid and community_role != "writer":
        raise HTTPException(
            status_code=400,
            detail="free tier requires Community Library writer grant; upgrade to customize",
        )
    grants: list[dict[str, str]] = []
    if personal_role != "none":
        if personal_role not in KEY_ROLES:
            raise HTTPException(status_code=400, detail="invalid personal library role")
        grants.append({"library_id": personal_library_id, "role": personal_role})
    if community_role != "none":
        if community_role not in KEY_ROLES:
            raise HTTPException(status_code=400, detail="invalid community library role")
        grants.append({"library_id": settings.default_library_id, "role": community_role})
    if not grants:
        raise HTTPException(status_code=400, detail="at least one library grant is required")
    return grants


def normalize_api_key_grants(
    grants: list[dict[str, str]] | None,
    *,
    personal_library_id: str,
    principal_id: str,
) -> list[dict[str, str]]:
    if grants is None:
        return default_key_grants(personal_library_id)
    personal_role: GrantRoleChoice = "none"
    community_role: GrantRoleChoice = "none"
    for grant in grants:
        library_id = grant.get("library_id", "")
        role = str(grant.get("role", "")).lower()
        if role not in KEY_ROLES:
            raise HTTPException(status_code=400, detail=f"invalid role for {library_id}")
        if library_id == personal_library_id:
            personal_role = role  # type: ignore[assignment]
        elif library_id == settings.default_library_id:
            community_role = role  # type: ignore[assignment]
        else:
            raise HTTPException(status_code=400, detail=f"unsupported library_id {library_id}")
    return resolve_key_grants(
        personal_library_id=personal_library_id,
        personal_role=personal_role,
        community_role=community_role,
        principal_id=principal_id,
    )


def create_personal_dev_key(
    principal_id: str,
    display_name: str,
    *,
    label: str,
    grants: list[dict[str, str]] | None = None,
    billing_account_id: str | None = None,
) -> dict[str, Any]:
    """Create a personal-dev API key with validated per-library grants."""
    lib = ensure_personal_library(principal_id, display_name)
    lib_id = lib["library_id"]
    resolved_grants = normalize_api_key_grants(grants, personal_library_id=lib_id, principal_id=principal_id)
    if db.count_active_api_keys(principal_id) >= settings.max_keys_per_principal:
        raise HTTPException(
            status_code=400,
            detail="active key limit reached; delete an old key first",
        )
    plaintext = f"ma3k_{secrets.token_hex(16)}"
    key_id = f"key_{secrets.token_hex(6)}"
    key_prefix = plaintext[:12]
    normalized_label = normalize_key_label(label)
    from app.services.billing_service import ensure_org_billing_account

    account = ensure_org_billing_account(
        personal_org_id(principal_id),
        plan_code="pro" if is_paid_principal(principal_id) else "free",
    )
    resolved_billing_account_id = billing_account_id or str(account["id"])
    db.insert_api_key(
        key_id=key_id,
        key_hash=api_key_service.hash_key(plaintext),
        key_prefix=key_prefix,
        key_ciphertext=encrypt_stored_key(plaintext),
        principal_id=principal_id,
        label=normalized_label,
        created_by=principal_id,
        billing_account_id=resolved_billing_account_id,
        grants=resolved_grants,
    )
    logger.info(
        "api_key_created principal_id=%s key_id=%s key_prefix=%s grants=%s",
        principal_id,
        key_id,
        key_prefix,
        ",".join(f"{g['library_id']}:{g['role']}" for g in resolved_grants),
    )
    return {
        "key_id": key_id,
        "plaintext_key": plaintext,
        "key_prefix": key_prefix,
        "label": normalized_label,
        "personal_library": lib,
        "grants": resolved_grants,
        "billing_account_id": resolved_billing_account_id,
    }
