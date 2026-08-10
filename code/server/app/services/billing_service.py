"""Billing-account source of truth and P0 seat admission helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.storage import db


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _period() -> tuple[str, str]:
    now = _now()
    start = now.replace(day=1, hour=0, minute=0, second=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.isoformat(), end.isoformat()


def _dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def get_billing_account(ba_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        return _dict(db._fetchone(conn, "SELECT * FROM billing_accounts WHERE id = ?", (ba_id,)))


def get_billing_account_for_org(org_id: str) -> dict[str, Any] | None:
    org = db.get_organization(org_id)
    if not org:
        return None
    ba_id = str(org.get("billing_account_id") or "")
    return get_billing_account(ba_id) if ba_id.startswith("ba_") else None


def effective_plan(billing_account_id: str) -> dict[str, Any]:
    account = get_billing_account(billing_account_id)
    if not account:
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    with db.connect() as conn:
        plan = db._fetchone(conn, "SELECT * FROM plans WHERE code = ?", (account["plan_code"],))
    if not plan:
        raise HTTPException(status_code=400, detail={"error": "unknown_plan"})
    result = dict(plan)
    result["code"] = str(result["code"])
    return result


def effective_quota(billing_account_id: str, quota_key: str) -> int:
    account = get_billing_account(billing_account_id)
    if not account:
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    # The environment allowlist is a break-glass Pro override for personal orgs.
    if account["owner_type"] == "org":
        org = db.get_organization(str(account["owner_id"]))
        if org and org.get("kind") == "personal" and str(org.get("owner_principal_id")) in settings.paid_principal_ids:
            with db.connect() as conn:
                row = db._fetchone(conn, f"SELECT {quota_key} AS value FROM plans WHERE code = 'pro'")
            if row:
                return int(row["value"])
    now = _now().isoformat()
    with db.connect() as conn:
        override = db._fetchone(
            conn,
            """
            SELECT value FROM quota_overrides
            WHERE billing_account_id = ? AND quota_key = ?
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (billing_account_id, quota_key, now),
        )
    if override:
        return int(override["value"])
    plan = effective_plan(billing_account_id)
    if quota_key not in plan:
        raise HTTPException(status_code=400, detail={"error": "unknown_quota"})
    return int(plan[quota_key])


def ensure_org_billing_account(org_id: str, *, plan_code: str, status: str = "active") -> dict[str, Any]:
    existing = get_billing_account_for_org(org_id)
    if existing:
        return existing
    start, end = _period()
    ba_id = db.new_id("ba")
    now = _now().isoformat()
    with db.connect() as conn:
        row = db._fetchone(conn, "SELECT code FROM plans WHERE code = ?", (plan_code,))
        if not row:
            raise HTTPException(status_code=400, detail={"error": "unknown_plan"})
        db._execute(
            conn,
            """
            INSERT INTO billing_accounts (
              id, owner_type, owner_id, plan_code, status,
              current_period_start, current_period_end, created_at
            ) VALUES (?, 'org', ?, ?, ?, ?, ?, ?)
            ON CONFLICT (owner_type, owner_id) DO NOTHING
            """,
            (ba_id, org_id, plan_code, status, start, end, now),
        )
        account = db._fetchone(
            conn, "SELECT * FROM billing_accounts WHERE owner_type = 'org' AND owner_id = ?", (org_id,)
        )
        db._execute(conn, "UPDATE organizations SET billing_account_id = ? WHERE id = ?", (account["id"], org_id))
    return dict(account)


def set_billing_account_plan(
    ba_id: str, *, plan_code: str | None = None, status: str | None = None,
    actor_principal_id: str | None = None,
) -> dict[str, Any]:
    account = get_billing_account(ba_id)
    if not account:
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    if plan_code is not None:
        with db.connect() as conn:
            if not db._fetchone(conn, "SELECT 1 FROM plans WHERE code = ?", (plan_code,)):
                raise HTTPException(status_code=400, detail={"error": "unknown_plan"})
    if status is not None and status not in {"active", "past_due", "cancelled"}:
        raise HTTPException(status_code=400, detail={"error": "unknown_status"})
    with db.connect() as conn:
        db._execute(
            conn, "UPDATE billing_accounts SET plan_code = COALESCE(?, plan_code), status = COALESCE(?, status) WHERE id = ?",
            (plan_code, status, ba_id),
        )
        current = db._fetchone(conn, "SELECT * FROM billing_accounts WHERE id = ?", (ba_id,))
        if current["owner_type"] == "org":
            org = db._fetchone(conn, "SELECT kind, owner_principal_id FROM organizations WHERE id = ?", (current["owner_id"],))
            if org and org["kind"] == "personal" and org["owner_principal_id"]:
                db._execute(conn, "UPDATE principals SET plan_code = ? WHERE id = ?", (current["plan_code"], org["owner_principal_id"]))
        db._execute(
            conn,
            "INSERT INTO billing_events (id, provider, type, billing_account_id, payload_json, processed_at, created_at) VALUES (?, NULL, ?, ?, ?, ?, ?)",
            (db.new_id("be"), "admin_plan_change", ba_id, json.dumps({"actor_principal_id": actor_principal_id}), _now().isoformat(), _now().isoformat()),
        )
    return dict(current)


def set_quota_override(ba_id: str, quota_key: str, value: int, *, reason: str | None = None, expires_at: str | None = None) -> dict[str, Any]:
    if not get_billing_account(ba_id):
        raise HTTPException(status_code=404, detail={"error": "billing_account_not_found"})
    with db.connect() as conn:
        db._execute(
            conn,
            """
            INSERT INTO quota_overrides (billing_account_id, quota_key, value, reason, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (billing_account_id, quota_key) DO UPDATE SET
              value = excluded.value, reason = excluded.reason, expires_at = excluded.expires_at
            """,
            (ba_id, quota_key, int(value), reason, expires_at),
        )
    return {"billing_account_id": ba_id, "quota_key": quota_key, "value": int(value)}


def clear_quota_override(ba_id: str, quota_key: str) -> None:
    with db.connect() as conn:
        db._execute(conn, "DELETE FROM quota_overrides WHERE billing_account_id = ? AND quota_key = ?", (ba_id, quota_key))


def _seat_usage_conn(conn: Any, org_id: str) -> dict[str, int]:
    org = db._fetchone(conn, "SELECT billing_account_id FROM organizations WHERE id = ?", (org_id,))
    ba_id = str(org["billing_account_id"] or "") if org else ""
    plan = db._fetchone(
        conn,
        "SELECT p.included_seats FROM billing_accounts b JOIN plans p ON p.code = b.plan_code WHERE b.id = ?",
        (ba_id,),
    )
    active = db._fetchone(conn, "SELECT COUNT(*) AS c FROM org_members WHERE org_id = ? AND seat_status = 'active'", (org_id,))
    now = _now().isoformat()
    pending = db._fetchone(
        conn,
        """
        SELECT COALESCE(SUM(max_uses - uses_count), 0) AS c FROM org_invites
        WHERE org_id = ? AND revoked_at IS NULL AND uses_count < max_uses
          AND (expires_at IS NULL OR expires_at > ?)
        """,
        (org_id, now),
    )
    active_count, pending_count = int(active["c"]), int(pending["c"])
    return {"active_members": active_count, "pending_invite_uses": pending_count, "used": active_count + pending_count, "included_seats": int(plan["included_seats"]) if plan else 1}


def seat_usage(org_id: str) -> dict[str, int]:
    with db.connect() as conn:
        return _seat_usage_conn(conn, org_id)


def _seat_error(usage: dict[str, int]) -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "seat_limit_exceeded", "used": usage["used"], "included_seats": usage["included_seats"], "upgrade_url": None})


def admit_org_member(*, org_id: str, principal_id: str, role: str = "member", alias: str | None = None, invite_id: str | None = None) -> dict[str, Any]:
    """Atomically check capacity, consume an optional invite, and activate membership."""
    now = _now().isoformat()
    with db.connect() as conn:
        if db.is_postgres():
            db._execute(conn, "SELECT pg_advisory_xact_lock(hashtext(?))", (org_id,))
        else:
            conn.execute("BEGIN IMMEDIATE")
        org = db._fetchone(conn, "SELECT kind FROM organizations WHERE id = ?", (org_id,))
        if not org:
            raise HTTPException(status_code=404, detail="organization not found")
        existing = db._fetchone(conn, "SELECT seat_status FROM org_members WHERE org_id = ? AND principal_id = ?", (org_id, principal_id))
        if (not existing or existing["seat_status"] != "active") and not invite_id:
            usage = _seat_usage_conn(conn, org_id)
            if org["kind"] == "personal" or usage["used"] >= usage["included_seats"]:
                raise _seat_error(usage)
        if invite_id:
            invite = db._fetchone(conn, "SELECT * FROM org_invites WHERE id = ?", (invite_id,))
            if not invite or invite["revoked_at"] is not None or int(invite["uses_count"]) >= int(invite["max_uses"]) or (invite["expires_at"] and str(invite["expires_at"]) <= now):
                raise HTTPException(status_code=410, detail="invite is exhausted")
            # A reservation already occupies capacity; if grandfathered additions
            # filled the org after minting, redemption must still be denied.
            usage = _seat_usage_conn(conn, org_id)
            if (not existing or existing["seat_status"] != "active") and usage["used"] > usage["included_seats"]:
                raise _seat_error(usage)
            db._execute(conn, "UPDATE org_invites SET uses_count = uses_count + 1, last_redeemed_at = ?, last_redeemed_by = ? WHERE id = ?", (now, principal_id, invite_id))
            db._execute(conn, "INSERT INTO org_invite_redemptions (invite_id, principal_id, redeemed_at) VALUES (?, ?, ?) ON CONFLICT (invite_id, principal_id) DO NOTHING", (invite_id, principal_id, now))
        if db.is_postgres():
            upsert = """INSERT INTO org_members (org_id, principal_id, role, seat_status, joined_at, alias) VALUES (?, ?, ?, 'active', ?, ?) ON CONFLICT (org_id, principal_id) DO UPDATE SET role = EXCLUDED.role, seat_status = 'active', alias = COALESCE(EXCLUDED.alias, org_members.alias)"""
        else:
            upsert = """INSERT INTO org_members (org_id, principal_id, role, seat_status, joined_at, alias) VALUES (?, ?, ?, 'active', ?, ?) ON CONFLICT(org_id, principal_id) DO UPDATE SET role = excluded.role, seat_status = 'active', alias = COALESCE(excluded.alias, org_members.alias)"""
        db._execute(conn, upsert, (org_id, principal_id, role, now, alias))
    member = db.get_org_member(org_id, principal_id)
    assert member is not None
    return member


def run_billing_backfill() -> dict[str, int]:
    """Create org-owned BAs, replace legacy labels, and attach legacy API keys."""
    created = 0
    with db.connect() as conn:
        orgs = [dict(row) for row in db._fetchall(conn, "SELECT * FROM organizations")]
    for org in orgs:
        org_id, kind = str(org["id"]), str(org["kind"])
        existing = get_billing_account_for_org(org_id)
        if existing and kind == "personal":
            owner = str(org.get("owner_principal_id") or "")
            if owner and (
                owner in settings.paid_principal_ids or db.get_principal_plan_code(owner) == "pro"
            ) and existing["plan_code"] != "pro":
                set_billing_account_plan(existing["id"], plan_code="pro")
            continue
        if not existing:
            if kind == "team":
                plan = "team_stub"
            else:
                owner = str(org.get("owner_principal_id") or "")
                legacy_label = str(org.get("billing_account_id") or "")
                plan = "pro" if (
                    legacy_label == "plan:pro"
                    or owner in settings.paid_principal_ids
                    or (owner and db.get_principal_plan_code(owner) == "pro")
                ) else "free"
            account = ensure_org_billing_account(org_id, plan_code=plan)
            # A rollout can have created the unique owner BA before a legacy
            # plan: label was restored/observed; migration labels still win.
            if account["plan_code"] != plan:
                account = set_billing_account_plan(account["id"], plan_code=plan)
            created += 1
            with db.connect() as conn:
                db._execute(
                    conn, "INSERT INTO billing_events (id, type, billing_account_id, payload_json, created_at) VALUES (?, 'migration_backfill', ?, ?, ?)",
                    (db.new_id("be"), account["id"], json.dumps({"legacy_billing_account_id": org.get("billing_account_id"), "plan_code": plan}), _now().isoformat()),
                )
    with db.connect() as conn:
        keys = db._fetchall(conn, "SELECT key_id, principal_id FROM api_keys WHERE billing_account_id IS NULL")
        for key in keys:
            owner_org = "org_personal_" + __import__("hashlib").sha256(str(key["principal_id"]).encode()).hexdigest()[:12]
            account = get_billing_account_for_org(owner_org)
            if account:
                db._execute(conn, "UPDATE api_keys SET billing_account_id = ? WHERE key_id = ?", (account["id"], key["key_id"]))
    return {"created": created}
