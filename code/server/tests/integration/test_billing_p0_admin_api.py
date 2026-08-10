"""P0 admin billing API scenarios (design/27 §2 P0, §8.1, §10 P0 bullet 2).

Contract encoded here (FAILS until Composer lands the routes):
- ``GET  /api/admin/billing-accounts/{ba_id}`` — detail (plan, status, owner).
- ``PATCH /api/admin/billing-accounts/{ba_id}`` — set plan_code and/or status;
  writes a billing_events audit row; write-through projection to
  principals.plan_code so is_paid_principal / quota services flip.
- ``PUT/DELETE /api/admin/billing-accounts/{ba_id}/overrides/{quota_key}`` —
  quota_overrides row management.
- Personal orgs get a real ba_* id at registration bootstrap (visible via
  the shipped /api/orgs listing).
- MA3_PAID_PRINCIPAL_IDS env allowlist still overrides (break-glass).
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.onboarding_service import is_paid_principal
from app.storage import db
from tests.helpers.billing_p0 import (
    auth_headers,
    count_billing_events,
    enable_local_auth,
    error_code,
    fetch_quota_override,
    personal_org_row,
    register_user,
)

pytestmark = pytest.mark.billing_p0


@pytest.fixture()
def billing_admin_env(isolated_client, monkeypatch):
    """Product admin + a plain user; ba_id is whatever bootstrap linked (may be
    empty pre-P0 — tests call _require_ba to fail with a clear reason)."""
    enable_local_auth(monkeypatch)
    client = isolated_client
    admin = register_user(client, "billingadmin")  # first local account = product admin
    user = register_user(client, "billinguser")
    personal = personal_org_row(client, user["api_key"])
    ba_id = str(personal.get("billing_account_id") or "")
    return {"client": client, "admin": admin, "user": user, "org_id": personal["id"], "ba_id": ba_id}


def _require_ba(env) -> str:
    """§10 P0 bullet 1: registration bootstrap links the personal org to a real
    billing_accounts row. Pre-P0 this is None → clean per-test failure."""
    ba_id = env["ba_id"]
    assert ba_id.startswith("ba_"), (
        "P0 bootstrap must link the personal org to a real billing_accounts row "
        f"(got billing_account_id={ba_id!r})"
    )
    return ba_id


def _patch_ba(env, payload: dict, *, api_key: str | None = None):
    _require_ba(env)
    return env["client"].patch(
        f"/api/admin/billing-accounts/{env['ba_id']}",
        headers=auth_headers(api_key or env["admin"]["api_key"]),
        json=payload,
    )


# --- BP0-A1: detail endpoint --------------------------------------------------

def test_admin_billing_account_detail(billing_admin_env):
    env = billing_admin_env
    _require_ba(env)
    response = env["client"].get(
        f"/api/admin/billing-accounts/{env['ba_id']}",
        headers=auth_headers(env["admin"]["api_key"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_code"] == "free"
    assert body["status"] == "active"
    assert body["owner_type"] == "org"
    assert body["owner_id"] == env["org_id"]


# --- BP0-A2: PATCH plan flips paid projection everywhere ----------------------

def test_patch_plan_flips_paid_projection_and_quotas(billing_admin_env):
    """§10 P0 bullet 2: setting the plan via the BA PATCH flips
    is_paid_principal, principals.plan_code projection, and downstream
    quota behavior (team-org creation gate used as the observable here)."""
    env = billing_admin_env
    pid = env["user"]["principal_id"]
    assert is_paid_principal(pid) is False

    response = _patch_ba(env, {"plan_code": "pro"})
    assert response.status_code == 200, response.text

    assert db.get_principal_plan_code(pid) == "pro", (
        "principals.plan_code must be kept as a write-through projection (§3.2)"
    )
    assert is_paid_principal(pid) is True
    quota = env["client"].get("/api/orgs/creation-quota", headers=auth_headers(env["user"]["api_key"]))
    assert quota.status_code == 200
    assert quota.json()["plan_code"] == "pro"
    assert quota.json()["allowed"] is True

    # And back down.
    response = _patch_ba(env, {"plan_code": "free"})
    assert response.status_code == 200, response.text
    assert db.get_principal_plan_code(pid) == "free"
    assert is_paid_principal(pid) is False
    quota = env["client"].get("/api/orgs/creation-quota", headers=auth_headers(env["user"]["api_key"]))
    assert quota.json()["allowed"] is False


# --- BP0-A3: PATCH status -----------------------------------------------------

def test_patch_status_past_due_roundtrip(billing_admin_env):
    env = billing_admin_env
    response = _patch_ba(env, {"status": "past_due"})
    assert response.status_code == 200, response.text
    detail = env["client"].get(
        f"/api/admin/billing-accounts/{env['ba_id']}",
        headers=auth_headers(env["admin"]["api_key"]),
    )
    assert detail.json()["status"] == "past_due"
    assert _patch_ba(env, {"status": "active"}).status_code == 200


def test_patch_rejects_unknown_plan_and_status(billing_admin_env):
    env = billing_admin_env
    assert _patch_ba(env, {"plan_code": "platinum"}).status_code in {400, 422}
    assert _patch_ba(env, {"status": "on_fire"}).status_code in {400, 422}


# --- BP0-A4: audit row --------------------------------------------------------

def test_patch_writes_billing_events_audit_row(billing_admin_env):
    """§8.1: every admin PATCH writes a billing_events audit row."""
    env = billing_admin_env
    before = count_billing_events(env["ba_id"])
    assert _patch_ba(env, {"plan_code": "pro"}).status_code == 200
    assert count_billing_events(env["ba_id"]) > before


# --- BP0-A5: quota overrides PUT/DELETE ----------------------------------------

def test_quota_override_put_and_delete(billing_admin_env):
    env = billing_admin_env
    _require_ba(env)
    put = env["client"].put(
        f"/api/admin/billing-accounts/{env['ba_id']}/overrides/max_libraries",
        headers=auth_headers(env["admin"]["api_key"]),
        json={"value": 9, "reason": "p0 acceptance test"},
    )
    assert put.status_code == 200, put.text
    row = fetch_quota_override(env["ba_id"], "max_libraries")
    assert row is not None and int(row["value"]) == 9

    delete = env["client"].delete(
        f"/api/admin/billing-accounts/{env['ba_id']}/overrides/max_libraries",
        headers=auth_headers(env["admin"]["api_key"]),
    )
    assert delete.status_code == 200, delete.text
    assert fetch_quota_override(env["ba_id"], "max_libraries") is None


# --- BP0-A6: actor gating -------------------------------------------------------

def test_non_admin_cannot_touch_billing_accounts(billing_admin_env):
    env = billing_admin_env
    response = _patch_ba(env, {"plan_code": "pro"}, api_key=env["user"]["api_key"])
    assert response.status_code == 403, (
        f"non-product-admin must get 403 on the billing PATCH, got {response.status_code}"
    )
    assert is_paid_principal(env["user"]["principal_id"]) is False


# --- BP0-A7: legacy alias kept -------------------------------------------------

def test_legacy_user_plan_patch_still_works(billing_admin_env):
    """§8.1: PATCH /api/admin/users/{pid}/plan stays as a thin alias that
    resolves the personal-org BA and writes through billing_service."""
    env = billing_admin_env
    _require_ba(env)
    pid = env["user"]["principal_id"]
    response = env["client"].patch(
        f"/api/admin/users/{pid}/plan",
        headers=auth_headers(env["admin"]["api_key"]),
        json={"paid": True},
    )
    assert response.status_code == 200, response.text
    assert is_paid_principal(pid) is True
    # After P0 the alias must keep the BA in sync, not just the projection.
    detail = env["client"].get(
        f"/api/admin/billing-accounts/{env['ba_id']}",
        headers=auth_headers(env["admin"]["api_key"]),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["plan_code"] == "pro", (
        "legacy plan alias must write through to the billing account (§8.1)"
    )


# --- BP0-A8: env allowlist break-glass (must already pass; regression guard) ----

def test_env_allowlist_still_overrides_to_pro(billing_admin_env, monkeypatch):
    """§10 P0 bullet 4: MA3_PAID_PRINCIPAL_IDS forces Pro regardless of BA plan."""
    env = billing_admin_env
    pid = env["user"]["principal_id"]
    monkeypatch.setattr(settings, "paid_principal_ids", (pid,))
    assert is_paid_principal(pid) is True
    quota = env["client"].get("/api/orgs/creation-quota", headers=auth_headers(env["user"]["api_key"]))
    assert quota.status_code == 200
    assert quota.json()["plan_code"] == "pro"


# --- BP0-A9: unknown BA --------------------------------------------------------

def test_patch_unknown_billing_account_404(billing_admin_env):
    env = billing_admin_env
    # Guard against a spurious pass pre-P0 (missing route also 404s).
    _require_ba(env)
    response = env["client"].patch(
        "/api/admin/billing-accounts/ba_does_not_exist",
        headers=auth_headers(env["admin"]["api_key"]),
        json={"plan_code": "pro"},
    )
    assert response.status_code == 404, response.text
    assert error_code(response) in {None, "billing_account_not_found", "not_found"}
