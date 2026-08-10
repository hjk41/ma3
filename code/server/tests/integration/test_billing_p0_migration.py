"""P0 backfill migration scenarios (design/27 §3.3, §0.1(3), §10 P0; test plan §13).

Synthetic legacy snapshot containing `plan:pro` / `plan:admin` / NULL labels,
env-allowlisted users and pre-existing API keys; run the backfill twice and
assert identical state, zero `plan:` labels, team orgs on `team_stub`
(never full `team` — §0.1(1)), and api_keys.billing_account_id backfilled
to the owner's personal BA (§0.1(3): moved to P0).

Contract: ``app.services.billing_service.run_billing_backfill()`` is the
idempotent pass invoked after ``initialize_database`` (§3.3 mechanics).
This module SKIPS until that module exists; then every test must pass.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import api_key_service
from app.services.onboarding_service import (
    ensure_personal_org,
    is_paid_principal,
    personal_org_id,
)
from app.storage import db
from tests.helpers.billing_p0 import (
    api_key_billing_account_id,
    billing_state_snapshot,
    count_billing_events,
    fetch_billing_account_for_org,
)

billing_service = pytest.importorskip(
    "app.services.billing_service",
    reason="P0 not implemented yet: app.services.billing_service (design/27 §2 P0)",
)

pytestmark = pytest.mark.billing_p0


def _seed_legacy_snapshot(monkeypatch) -> dict[str, str]:
    """Reproduce the pre-P0 production shape.

    Labels actually written by shipped code (design/27 §0 ground truth):
    personal orgs `plan:free|plan:pro` via set_user_paid, team orgs
    `plan:pro`/`plan:admin` via create_team_org; `plan:team` never occurs.
    """
    # Personal Pro user (label plan:pro, principals.plan_code=pro).
    db.upsert_user_principal(sso_user="legacy-pro", display_name="Legacy Pro")
    ensure_personal_org("user:legacy-pro", "Legacy Pro")
    db.set_principal_plan_code("user:legacy-pro", "pro")
    db.set_organization_billing_account_id(personal_org_id("user:legacy-pro"), "plan:pro")

    # Personal free user (NULL label — ensure_personal_org never wrote one).
    db.upsert_user_principal(sso_user="legacy-free", display_name="Legacy Free")
    ensure_personal_org("user:legacy-free", "Legacy Free")

    # Env-allowlisted user, plan_code=free in DB (break-glass Pro).
    db.upsert_user_principal(sso_user="env-vip", display_name="Env Vip")
    ensure_personal_org("user:env-vip", "Env Vip")
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:env-vip",))

    # Team orgs with the two legacy labels.
    team_pro = db.new_id("org")
    db.create_organization(
        team_pro,
        name="Legacy Pro Team",
        kind="team",
        owner_principal_id="user:legacy-pro",
        billing_account_id="plan:pro",
    )
    db.add_org_member(org_id=team_pro, principal_id="user:legacy-pro", role="admin")

    team_admin = db.new_id("org")
    db.create_organization(
        team_admin,
        name="Legacy Admin Team",
        kind="team",
        owner_principal_id="user:legacy-free",
        billing_account_id="plan:admin",
    )
    db.add_org_member(org_id=team_admin, principal_id="user:legacy-free", role="admin")

    # Pre-existing API key without billing context (§0.1(3) backfill target).
    key_id = db.new_id("key")
    db.insert_api_key(
        key_id=key_id,
        key_hash=api_key_service.hash_key("ma3k_legacy_billing_p0"),
        key_prefix="ma3k_legacy_",
        principal_id="user:legacy-free",
        label="legacy-key",
        created_by="user:legacy-free",
        grants=[{"library_id": settings.default_library_id, "role": "writer"}],
    )
    return {"team_pro": team_pro, "team_admin": team_admin, "key_id": key_id}


def _all_org_labels() -> list[str]:
    with db.connect() as conn:
        rows = db._fetchall(conn, "SELECT id, billing_account_id FROM organizations")
    return [str(r["billing_account_id"] or "") for r in rows]


def test_backfill_run_twice_same_state(isolated_client, monkeypatch):
    """§10 P0 bullet 1: migration on an existing snapshot is repeatable."""
    _seed_legacy_snapshot(monkeypatch)
    billing_service.run_billing_backfill()
    first = billing_state_snapshot()
    billing_service.run_billing_backfill()
    second = billing_state_snapshot()
    assert first == second


def test_backfill_removes_all_plan_labels_and_links_real_fks(isolated_client, monkeypatch):
    _seed_legacy_snapshot(monkeypatch)
    billing_service.run_billing_backfill()
    labels = _all_org_labels()
    assert labels, "expected seeded organizations"
    assert not [x for x in labels if x.startswith("plan:")], f"plan: labels remain: {labels}"
    assert all(x.startswith("ba_") for x in labels), (
        f"every org's billing_account_id must be a real ba_* FK, got: {labels}"
    )


def test_backfill_personal_plan_mapping(isolated_client, monkeypatch):
    """§3.3(2): personal BA plan = pro if plan_code==pro or env allowlist, else free."""
    _seed_legacy_snapshot(monkeypatch)
    billing_service.run_billing_backfill()

    pro_ba = fetch_billing_account_for_org(personal_org_id("user:legacy-pro"))
    free_ba = fetch_billing_account_for_org(personal_org_id("user:legacy-free"))
    vip_ba = fetch_billing_account_for_org(personal_org_id("user:env-vip"))
    assert pro_ba["plan_code"] == "pro"
    assert free_ba["plan_code"] == "free"
    assert vip_ba["plan_code"] == "pro"

    # Paid resolution unchanged after the rewire (§10: quota tests pass unmodified).
    assert is_paid_principal("user:legacy-pro") is True
    assert is_paid_principal("user:legacy-free") is False
    assert is_paid_principal("user:env-vip") is True


def test_backfill_team_orgs_land_on_team_stub_never_full_team(isolated_client, monkeypatch):
    """§0.1(1) amendment: plan:pro AND plan:admin team orgs → team_stub;
    no org lands on full `team` without a subscription or explicit admin set."""
    ids = _seed_legacy_snapshot(monkeypatch)
    billing_service.run_billing_backfill()
    for org_key in ("team_pro", "team_admin"):
        ba = fetch_billing_account_for_org(ids[org_key])
        assert ba["plan_code"] == "team_stub", (org_key, ba)
        assert ba["status"] == "active"


def test_backfill_populates_api_key_billing_account(isolated_client, monkeypatch):
    """§0.1(3): api_keys.billing_account_id backfilled deterministically to the
    owner's personal BA (metering must never start on unverified keys)."""
    ids = _seed_legacy_snapshot(monkeypatch)
    billing_service.run_billing_backfill()
    owner_ba = fetch_billing_account_for_org(personal_org_id("user:legacy-free"))
    assert api_key_billing_account_id(ids["key_id"]) == owner_ba["id"]


def test_backfill_writes_audit_billing_events(isolated_client, monkeypatch):
    """§3.3(2): raw label + mapping kept in billing_events type='migration_backfill'."""
    _seed_legacy_snapshot(monkeypatch)
    billing_service.run_billing_backfill()
    assert count_billing_events(event_type="migration_backfill") > 0
