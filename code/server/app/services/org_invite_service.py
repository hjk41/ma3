"""One-time (or limited-use) organization invite tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from fastapi import HTTPException

from app.core.config import settings
from app.services.org_service import assert_org_admin, normalize_org_alias
from app.storage import db

OrgInviteRole = Literal["admin", "member"]
TOKEN_PREFIX = "ma3inv_"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z") if dt.tzinfo else dt.isoformat()


def hash_invite_token(plaintext: str) -> str:
    return hashlib.sha256(str(plaintext).encode("utf-8")).hexdigest()


def mint_invite_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(24)


def normalize_invite_token(raw: str | None) -> str | None:
    token = str(raw or "").strip()
    return token or None


def public_invite(row: dict[str, Any], *, org_name: str | None = None) -> dict[str, Any]:
    max_uses = int(row.get("max_uses") or 1)
    uses = int(row.get("uses_count") or 0)
    revoked = row.get("revoked_at") is not None
    expired = False
    expires_at = row.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            expired = exp <= _utcnow()
        except ValueError:
            expired = False
    remaining = 0 if revoked or expired else max(0, max_uses - uses)
    return {
        "invite_id": row.get("id"),
        "org_id": row.get("org_id"),
        "org_name": org_name,
        "role": row.get("role"),
        "member_alias": row.get("member_alias"),
        "max_uses": max_uses,
        "uses_count": uses,
        "remaining_uses": remaining,
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "expires_at": expires_at,
        "revoked_at": row.get("revoked_at"),
        "status": (
            "revoked"
            if revoked
            else "expired"
            if expired
            else "exhausted"
            if remaining == 0
            else "active"
        ),
    }


def build_invite_url(*, base_url: str, token: str) -> str:
    base = (base_url or settings.public_base_url or "").rstrip("/")
    if not base:
        base = ""
    return f"{base}/auth/register?invite={quote(token, safe='')}"


def create_org_invite(
    *,
    org_id: str,
    actor_principal_id: str,
    role: OrgInviteRole = "member",
    max_uses: int = 1,
    expires_in_hours: int | None = 168,
    base_url: str = "",
    member_alias: str | None = None,
) -> dict[str, Any]:
    assert_org_admin(org_id, actor_principal_id)
    org = db.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if str(org.get("kind") or "") == "personal":
        raise HTTPException(status_code=400, detail="cannot invite into a personal organization")
    if role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="invalid role")
    uses = int(max_uses)
    if uses < 1 or uses > 100:
        raise HTTPException(status_code=400, detail="max_uses must be between 1 and 100")

    alias = normalize_org_alias(member_alias) if member_alias else None

    expires_at = None
    if expires_in_hours is not None:
        hours = int(expires_in_hours)
        if hours < 1 or hours > 24 * 90:
            raise HTTPException(status_code=400, detail="expires_in_hours must be between 1 and 2160")
        expires_at = _iso(_utcnow() + timedelta(hours=hours))

    token = mint_invite_token()
    invite_id = db.new_id("inv")
    row = db.create_org_invite(
        invite_id=invite_id,
        org_id=org_id,
        token_hash=hash_invite_token(token),
        role=role,
        created_by=actor_principal_id,
        max_uses=uses,
        expires_at=expires_at,
        member_alias=alias,
    )
    payload = public_invite(row, org_name=str(org.get("name") or org_id))
    payload["token"] = token
    payload["invite_url"] = build_invite_url(base_url=base_url, token=token)
    return payload


def list_org_invites(*, org_id: str, actor_principal_id: str) -> list[dict[str, Any]]:
    assert_org_admin(org_id, actor_principal_id)
    org = db.get_organization(org_id)
    name = str(org.get("name") or org_id) if org else org_id
    return [public_invite(r, org_name=name) for r in db.list_org_invites(org_id, include_revoked=True)]


def revoke_org_invite(*, org_id: str, invite_id: str, actor_principal_id: str) -> dict[str, Any]:
    assert_org_admin(org_id, actor_principal_id)
    row = db.get_org_invite(invite_id)
    if row is None or str(row.get("org_id")) != org_id:
        raise HTTPException(status_code=404, detail="invite not found")
    updated = db.revoke_org_invite(invite_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="invite not found")
    org = db.get_organization(org_id)
    return public_invite(updated, org_name=str(org.get("name") or org_id) if org else org_id)


def _load_invite_for_token(token: str) -> dict[str, Any]:
    token = normalize_invite_token(token) or ""
    if not token.startswith(TOKEN_PREFIX):
        raise HTTPException(status_code=400, detail="invalid invite token")
    row = db.get_org_invite_by_token_hash(hash_invite_token(token))
    if row is None:
        raise HTTPException(status_code=404, detail="invite not found")
    return row


def preview_invite(token: str) -> dict[str, Any]:
    row = _load_invite_for_token(token)
    org = db.get_organization(str(row["org_id"]))
    payload = public_invite(row, org_name=str(org.get("name") or row["org_id"]) if org else None)
    if payload["status"] != "active":
        raise HTTPException(status_code=410, detail=f"invite is {payload['status']}")
    return {
        "org_id": payload["org_id"],
        "org_name": payload["org_name"],
        "role": payload["role"],
        "member_alias": payload.get("member_alias"),
        "expires_at": payload["expires_at"],
        "remaining_uses": payload["remaining_uses"],
        "status": payload["status"],
    }


def assert_invite_allows_registration(token: str | None) -> dict[str, Any] | None:
    """When registration is closed, a valid active invite still allows signup."""
    token = normalize_invite_token(token)
    if not token:
        return None
    return preview_invite(token)


def redeem_invite(*, token: str, principal_id: str) -> dict[str, Any]:
    """Join org for principal; consumes one use unless already redeemed by same principal."""
    from app.services.org_service import assert_org_alias_available, normalize_org_alias

    row = _load_invite_for_token(token)
    org_id = str(row["org_id"])
    role = str(row.get("role") or "member")
    if role not in ("admin", "member"):
        role = "member"
    alias = normalize_org_alias(row.get("member_alias")) if row.get("member_alias") else None

    existing = db.get_org_member(org_id, principal_id)
    if existing and existing.get("seat_status") == "active":
        # Idempotent: already a member. If they never consumed this invite, still consume.
        status = db.try_consume_org_invite(
            invite_id=str(row["id"]),
            principal_id=principal_id,
            now=_iso(_utcnow()),
        )
        if alias and not existing.get("alias"):
            try:
                assert_org_alias_available(org_id, alias, exclude_principal_id=principal_id)
                existing = db.set_org_member_alias(
                    org_id=org_id, principal_id=principal_id, alias=alias
                )
            except HTTPException:
                pass
        return {
            "org_id": org_id,
            "principal_id": principal_id,
            "role": existing.get("role") or role,
            "alias": existing.get("alias"),
            "already_member": True,
            "invite_id": row["id"],
            "consumed": status == "ok",
        }

    if alias:
        assert_org_alias_available(org_id, alias, exclude_principal_id=principal_id)

    status = db.try_consume_org_invite(
        invite_id=str(row["id"]),
        principal_id=principal_id,
        now=_iso(_utcnow()),
    )
    if status == "already":
        member = db.add_org_member(
            org_id=org_id, principal_id=principal_id, role=role, alias=alias
        )
        return {
            "org_id": org_id,
            "principal_id": principal_id,
            "role": member.get("role") or role,
            "alias": member.get("alias"),
            "already_member": False,
            "invite_id": row["id"],
            "consumed": False,
        }
    if status != "ok":
        raise HTTPException(status_code=410, detail=f"invite is {status}")

    member = db.add_org_member(org_id=org_id, principal_id=principal_id, role=role, alias=alias)
    org = db.get_organization(org_id)
    return {
        "org_id": org_id,
        "org_name": org.get("name") if org else None,
        "principal_id": principal_id,
        "role": member.get("role") or role,
        "alias": member.get("alias"),
        "already_member": False,
        "invite_id": row["id"],
        "consumed": True,
    }
