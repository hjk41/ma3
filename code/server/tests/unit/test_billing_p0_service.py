"""P0 billing_service unit scenarios (design/27 §2 P0, §3, §10 P0; test plan §13).

Contract under test: app.services.billing_service — effective_plan /
effective_quota precedence (env > override > plan), write-through projection
to principals.plan_code, period math, seat usage including pending-invite
reservations (§0.1 amendment 2), team_stub seeding (Decision 5a=A).

This module SKIPS until Composer lands `app.services.billing_service`;
after that every test must pass.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.onboarding_service import (
    ensure_personal_org,
    is_paid_principal,
    personal_org_id,
)
from app.services.org_service import create_team_org
from app.storage import db
from app.storage.db import initialize_database
from tests.helpers.billing_p0 import (
    TEAM_STUB_SEATS,
    fetch_billing_account_for_org,
    list_plan_rows,
)

billing_service = pytest.importorskip(
    "app.services.billing_service",
    reason="P0 not implemented yet: app.services.billing_service (design/27 §2 P0)",
)

pytestmark = pytest.mark.billing_p0


@pytest.fixture(autouse=True)
def billing_unit_db(tmp_path, monkeypatch):
    db_path = tmp_path / "billing-p0-unit.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "paid_principal_ids", ())
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_free", 0)
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_pro", 1)
    initialize_database()
    db.set_library_write_buffer_hours(settings.default_library_id, 0)


def _bootstrap_user(name: str) -> tuple[str, str]:
    """Create principal + personal org (login bootstrap path). Returns (pid, org_id)."""
    pid = f"user:{name}"
    db.upsert_user_principal(sso_user=name, display_name=name)
    ensure_personal_org(pid, name)
    return pid, personal_org_id(pid)


# --- BP0-U1: plans seeded ---------------------------------------------------

def test_plans_seeded_with_team_stub():
    """§3.1(4): plans seeded free/pro/team_stub/team with locked seat/library caps."""
    plans = list_plan_rows()
    assert {"free", "pro", "team_stub", "team"} <= set(plans)
    assert plans["free"]["scope"] == "personal"
    assert plans["pro"]["scope"] == "personal"
    assert plans["team_stub"]["scope"] == "org"
    assert plans["team"]["scope"] == "org"
    seats = {code: int(plans[code]["included_seats"]) for code in ("free", "pro", "team_stub", "team")}
    assert seats == {"free": 1, "pro": 1, "team_stub": 3, "team": 5}
    libs = {code: int(plans[code]["max_libraries"]) for code in ("free", "pro", "team_stub", "team")}
    assert libs == {"free": 1, "pro": 5, "team_stub": 3, "team": 10}


# --- BP0-U2: login bootstrap creates the personal BA ------------------------

def test_login_bootstrap_creates_free_personal_billing_account():
    """§10 P0 bullet 1: first login → personal org + billing_accounts row plan=free."""
    pid, org_id = _bootstrap_user("bp0-fresh")
    ba = fetch_billing_account_for_org(org_id)
    assert ba is not None
    assert ba["plan_code"] == "free"
    assert ba["status"] == "active"
    # §3.1(3): BA owner is the org, uniformly.
    assert ba["owner_type"] == "org"
    assert ba["owner_id"] == org_id
    # §3.3: without Stripe, period = current UTC calendar month.
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    assert str(ba["current_period_start"]).startswith(month)
    assert ba["current_period_end"]


def test_login_bootstrap_is_idempotent():
    pid, org_id = _bootstrap_user("bp0-idem")
    first = fetch_billing_account_for_org(org_id)
    ensure_personal_org(pid, "bp0-idem")
    second = fetch_billing_account_for_org(org_id)
    assert first == second


# --- BP0-U3: effective_plan / effective_quota precedence --------------------

def test_effective_plan_and_quota_defaults():
    _, org_id = _bootstrap_user("bp0-quota")
    ba = fetch_billing_account_for_org(org_id)
    plan = billing_service.effective_plan(ba["id"])
    assert plan["code"] == "free"
    assert billing_service.effective_quota(ba["id"], "included_seats") == 1
    assert billing_service.effective_quota(ba["id"], "max_libraries") == 1


def test_quota_override_beats_plan_default():
    """§3.1(5): quota_overrides wins over plan defaults."""
    _, org_id = _bootstrap_user("bp0-override")
    ba = fetch_billing_account_for_org(org_id)
    billing_service.set_quota_override(ba["id"], "max_libraries", 7, reason="p0-test")
    assert billing_service.effective_quota(ba["id"], "max_libraries") == 7
    billing_service.clear_quota_override(ba["id"], "max_libraries")
    assert billing_service.effective_quota(ba["id"], "max_libraries") == 1


def test_env_allowlist_beats_db_plan(monkeypatch):
    """§3.1(5) + §10 P0 bullet 4: MA3_PAID_PRINCIPAL_IDS is the operator's last word."""
    pid, org_id = _bootstrap_user("bp0-env")
    ba = fetch_billing_account_for_org(org_id)
    assert ba["plan_code"] == "free"
    monkeypatch.setattr(settings, "paid_principal_ids", (pid,))
    assert is_paid_principal(pid) is True


# --- BP0-U4: projection write-through ---------------------------------------

def test_set_plan_writes_through_principal_projection():
    """§10 P0 bullet 2 (service half): plan change via billing_service flips
    is_paid_principal and keeps principals.plan_code as a derived projection."""
    pid, org_id = _bootstrap_user("bp0-project")
    ba = fetch_billing_account_for_org(org_id)
    assert is_paid_principal(pid) is False

    billing_service.set_billing_account_plan(ba["id"], plan_code="pro")
    assert db.get_principal_plan_code(pid) == "pro"
    assert is_paid_principal(pid) is True

    billing_service.set_billing_account_plan(ba["id"], plan_code="free")
    assert db.get_principal_plan_code(pid) == "free"
    assert is_paid_principal(pid) is False


# --- BP0-U5: Pro-created team org lands on team_stub ------------------------

def test_pro_creator_team_org_gets_team_stub(monkeypatch):
    """§0.1(1) / §9.1 (Decision 5a=A): no unpaid full Team — Pro-created team
    orgs get plan_code='team_stub', status='active'."""
    pid, _ = _bootstrap_user("bp0-pro-creator")
    monkeypatch.setattr(settings, "paid_principal_ids", (pid,))
    org = create_team_org(name="Stub Team", owner_principal_id=pid)
    ba = fetch_billing_account_for_org(str(org["id"]))
    assert ba is not None
    assert ba["plan_code"] == "team_stub"
    assert ba["status"] == "active"


# --- BP0-U6: seat usage math (active + pending invite reservations) ---------

def test_seat_usage_counts_pending_invite_reservations(monkeypatch):
    """§0.1(2): seats_used = active_members + sum(remaining_uses of
    non-expired invites)."""
    pid, _ = _bootstrap_user("bp0-seats")
    monkeypatch.setattr(settings, "paid_principal_ids", (pid,))
    org = create_team_org(name="Seat Math Team", owner_principal_id=pid)
    org_id = str(org["id"])

    usage = billing_service.seat_usage(org_id)
    assert usage["included_seats"] == TEAM_STUB_SEATS
    assert usage["active_members"] == 1
    assert usage["used"] == 1

    future = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    db.create_org_invite(
        invite_id=db.new_id("inv"),
        org_id=org_id,
        token_hash="a" * 64,
        role="member",
        created_by=pid,
        max_uses=2,
        expires_at=future,
        member_alias=None,
    )
    usage = billing_service.seat_usage(org_id)
    assert usage["pending_invite_uses"] == 2
    assert usage["used"] == 3

    # Expired invites reserve nothing.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    db.create_org_invite(
        invite_id=db.new_id("inv"),
        org_id=org_id,
        token_hash="b" * 64,
        role="member",
        created_by=pid,
        max_uses=5,
        expires_at=past,
        member_alias=None,
    )
    assert billing_service.seat_usage(org_id)["used"] == 3
