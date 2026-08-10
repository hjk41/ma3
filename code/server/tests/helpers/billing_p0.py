"""Shared helpers for org+billing P0 acceptance tests.

Encodes the public contract Composer implements against
(design/27 `27-org-billing-implementation-fable.md` §0.1, §2 P0, §3, §10 P0):

Expected NEW symbols (P0):
- module ``app.services.billing_service`` with at least:
    run_billing_backfill() -> dict            # idempotent pass after initialize_database
    get_billing_account(ba_id) -> dict | None
    get_billing_account_for_org(org_id) -> dict | None
    effective_plan(billing_account_id) -> dict          # includes "code"
    effective_quota(billing_account_id, quota_key) -> int
    set_billing_account_plan(ba_id, *, plan_code=None, status=None,
                             actor_principal_id=None) -> dict
    set_quota_override(ba_id, quota_key, value, *, reason=None, expires_at=None)
    clear_quota_override(ba_id, quota_key)
    seat_usage(org_id) -> dict  # {used, active_members, pending_invite_uses, included_seats}
- tables ``plans`` (seeded free/pro/team_stub/team), ``billing_accounts``,
  ``quota_overrides``, ``billing_events`` created by ``initialize_database``
  (schema: docs/03-backend/billing-and-quotas.md §3 + design/27 §3.1 amendments).
- column ``api_keys.billing_account_id`` (nullable, backfilled in P0).
- routes: ``GET/PATCH /api/admin/billing-accounts/{ba_id}``,
  ``PUT/DELETE /api/admin/billing-accounts/{ba_id}/overrides/{quota_key}``.
- structured seat error: ``403 {"error": "seat_limit_exceeded", "used",
  "included_seats", "upgrade_url"}`` (design/27 §8.2; §10 P0 acceptance).
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.storage import db

JSON = {"Content-Type": "application/json"}

# Stub entitlements, locked Decision 5a=A (design/27 §9.1).
TEAM_STUB_SEATS = 3
PERSONAL_SEATS = 1


def enable_local_auth(monkeypatch) -> None:
    """Self-host local-auth profile (mirrors test_org_invites_api._enable_local)."""
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    monkeypatch.setattr(settings, "authing_app_id", "")
    monkeypatch.setattr(settings, "authing_app_secret", "")
    monkeypatch.setattr(settings, "local_auth", True)
    monkeypatch.setattr(settings, "local_auth_open_registration", True)
    monkeypatch.setattr(settings, "api_key_encryption_secret", "test-billing-p0-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ())
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_free", 0)
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_pro", 1)
    monkeypatch.setattr(settings, "paid_principal_ids", ())
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")


def register_user(client, username: str, *, display_name: str | None = None) -> dict[str, Any]:
    """Register a local account with an API key.

    NOTE: the FIRST registered local account is the product admin
    (local_auth_service.is_admin_username first_user=True).
    Returns {"api_key", "principal_id", "username"}.
    """
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "password123",
            "display_name": display_name or username,
            "api_key": {"label": f"{username}-key"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "api_key": body["api_key"]["plaintext_key"],
        "principal_id": body["account"]["principal_id"],
        "username": username,
    }


def auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key, **JSON}


def create_team_org_via_api(client, api_key: str, name: str = "Billing P0 Team") -> str:
    response = client.post("/api/orgs", headers=auth_headers(api_key), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def personal_org_row(client, api_key: str) -> dict[str, Any]:
    response = client.get("/api/orgs", headers={"X-API-Key": api_key})
    assert response.status_code == 200, response.text
    rows = [o for o in response.json()["orgs"] if o.get("kind") == "personal"]
    assert rows, "personal org missing after registration bootstrap"
    return rows[0]


def error_code(response) -> str | None:
    """Extract detail.error from a structured FastAPI error response."""
    try:
        detail = response.json().get("detail")
    except Exception:
        return None
    if isinstance(detail, dict):
        return detail.get("error")
    return None


# ---------------------------------------------------------------------------
# Raw table access for the NEW billing tables. Deliberately raw SQL: these
# fail loudly ("no such table: billing_accounts") until the P0 migration
# lands, which is the intended pre-implementation signal.
# ---------------------------------------------------------------------------

def fetch_billing_account(ba_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            """
            SELECT id, owner_type, owner_id, plan_code, status,
                   current_period_start, current_period_end
            FROM billing_accounts WHERE id = ?
            """,
            (ba_id,),
        )
    return dict(row) if row else None


def fetch_billing_account_for_org(org_id: str) -> dict[str, Any] | None:
    org = db.get_organization(org_id)
    assert org is not None, f"org not found: {org_id}"
    ba_id = str(org.get("billing_account_id") or "")
    assert ba_id.startswith("ba_"), (
        f"organizations.billing_account_id for {org_id} is {ba_id!r}; "
        "expected a real billing_accounts FK (ba_*) after the P0 migration"
    )
    return fetch_billing_account(ba_id)


def list_plan_rows() -> dict[str, dict[str, Any]]:
    with db.connect() as conn:
        rows = db._fetchall(
            conn,
            "SELECT code, scope, included_seats, max_libraries FROM plans",
        )
    return {str(r["code"]): dict(r) for r in rows}


def count_billing_events(ba_id: str | None = None, *, event_type: str | None = None) -> int:
    query = "SELECT COUNT(*) AS c FROM billing_events WHERE 1=1"
    params: list[Any] = []
    if ba_id is not None:
        query += " AND billing_account_id = ?"
        params.append(ba_id)
    if event_type is not None:
        query += " AND type = ?"
        params.append(event_type)
    with db.connect() as conn:
        row = db._fetchone(conn, query, tuple(params))
    return int(row["c"]) if row else 0


def fetch_quota_override(ba_id: str, quota_key: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT billing_account_id, quota_key, value FROM quota_overrides "
            "WHERE billing_account_id = ? AND quota_key = ?",
            (ba_id, quota_key),
        )
    return dict(row) if row else None


def api_key_billing_account_id(key_id: str) -> str | None:
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT billing_account_id FROM api_keys WHERE key_id = ?",
            (key_id,),
        )
    assert row is not None, f"api key not found: {key_id}"
    value = row["billing_account_id"]
    return str(value) if value else None


def billing_state_snapshot() -> dict[str, Any]:
    """Full billing-relevant state, for run-twice idempotency comparison."""
    with db.connect() as conn:
        orgs = db._fetchall(conn, "SELECT id, billing_account_id FROM organizations ORDER BY id")
        bas = db._fetchall(
            conn,
            """
            SELECT id, owner_type, owner_id, plan_code, status,
                   current_period_start, current_period_end
            FROM billing_accounts ORDER BY id
            """,
        )
        keys = db._fetchall(
            conn, "SELECT key_id, billing_account_id FROM api_keys ORDER BY key_id"
        )
        overrides = db._fetchall(
            conn,
            "SELECT billing_account_id, quota_key, value FROM quota_overrides "
            "ORDER BY billing_account_id, quota_key",
        )
        plan_codes = db._fetchall(
            conn,
            # principals table may use `id` or `principal_id` depending on dialect
            "SELECT plan_code, COUNT(*) AS c FROM principals GROUP BY plan_code ORDER BY plan_code",
        )
    return {
        "organizations": [dict(r) for r in orgs],
        "billing_accounts": [dict(r) for r in bas],
        "api_keys": [dict(r) for r in keys],
        "quota_overrides": [dict(r) for r in overrides],
        "principal_plan_codes": [dict(r) for r in plan_codes],
    }
