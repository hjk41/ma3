"""P1 past_due grace/revoke job unit scenarios (design/27 §9 Decision 8-A,
§2 P1 past_due row, §10 P1 bullet 5).

Contract under test: app.services.billing_grace_service.run_past_due_grace_job —
grace clock starts when billing_accounts.status flips to 'past_due' (the P0
billing_events audit row is the durable timestamp source); the job takes an
injectable `now` so the 30-day window is testable without wall-clock waits.

Behavior encoded (Decision 8-A, locked):
- Private/org library RO key grants + RO library grants: revoked at T-0
  (past_due + 30 days). NEVER escalated RO->RW.
- Community lib_default: contribution-first FORCE_RW untouched, never revoked.
- Notifications at T-7 / T-1 / T-0 (banner+email; the job reports them).
- Paying (status back to 'active') before T-0 cancels the revoke.
- Idempotent: a second run revokes/notifies nothing new.

SKIPS until Composer lands `app.services.billing_grace_service`.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services.api_key_service import hash_key
from app.services.onboarding_service import ensure_personal_org, personal_org_id
from app.storage import db
from app.storage.db import initialize_database
from tests.helpers.billing_p1 import (
    GRACE_DAYS,
    fetch_billing_account_for_org,
    set_ba_status,
)

billing_grace_service = pytest.importorskip(
    "app.services.billing_grace_service",
    reason="P1 not implemented yet: app.services.billing_grace_service (design/27 §9 Decision 8)",
)

pytestmark = pytest.mark.billing_p1


@pytest.fixture(autouse=True)
def grace_db(tmp_path, monkeypatch):
    db_path = tmp_path / "billing-p1-grace.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    initialize_database()


@pytest.fixture()
def past_due_env():
    """User with a private library, an RO key grant, an RO library grant,
    an RW key grant (must survive untouched as RW-or-revoked, never created
    from RO), plus Community lib_default grants."""
    pid = "user:p1-grace"
    reader_pid = "user:p1-grace-reader"
    db.upsert_user_principal(sso_user="p1-grace", display_name="p1-grace")
    db.upsert_user_principal(sso_user="p1-grace-reader", display_name="p1-grace-reader")
    ensure_personal_org(pid, "p1-grace")
    ensure_personal_org(reader_pid, "p1-grace-reader")

    private_lib = db.new_id("lib")
    db.ensure_library(
        private_lib,
        name="Grace Private",
        visibility="private",
        kind="personal",
        owner_principal_id=pid,
    )

    ro_key_id = f"key_{secrets.token_hex(6)}"
    db.insert_api_key(
        key_id=ro_key_id,
        key_hash=hash_key(f"ma3k_{secrets.token_hex(16)}"),
        principal_id=pid,
        label="grace-ro-key",
        grants=[
            {"library_id": private_lib, "role": "reader"},
            {"library_id": settings.default_library_id, "role": "reader"},
        ],
    )
    rw_key_id = f"key_{secrets.token_hex(6)}"
    db.insert_api_key(
        key_id=rw_key_id,
        key_hash=hash_key(f"ma3k_{secrets.token_hex(16)}"),
        principal_id=pid,
        label="grace-rw-key",
        grants=[{"library_id": private_lib, "role": "writer"}],
    )
    db.upsert_library_grant(library_id=private_lib, principal_id=reader_pid, role="reader")

    ba = fetch_billing_account_for_org(personal_org_id(pid))
    flipped_at = datetime.now(timezone.utc)
    set_ba_status(str(ba["id"]), "past_due")
    return {
        "ba_id": str(ba["id"]),
        "pid": pid,
        "reader_pid": reader_pid,
        "private_lib": private_lib,
        "ro_key_id": ro_key_id,
        "rw_key_id": rw_key_id,
        "flipped_at": flipped_at,
    }


def _roles(key_id: str, library_id: str) -> set[str]:
    return {
        str(g["role"])
        for g in db.get_api_key_grants(key_id)
        if str(g["library_id"]) == library_id
    }


def _run(env, days: int) -> dict:
    return billing_grace_service.run_past_due_grace_job(
        now=env["flipped_at"] + timedelta(days=days)
    )


# --- BP1-G1: inside grace nothing is revoked -----------------------------------

def test_no_revoke_inside_grace_window(past_due_env):
    env = past_due_env
    result = _run(env, days=1)
    assert result["revoked"] == []
    assert _roles(env["ro_key_id"], env["private_lib"]) == {"reader"}
    assert db.get_library_grant(env["private_lib"], env["reader_pid"]) is not None


# --- BP1-G2: T-0 revokes private/org RO, never escalates, spares lib_default -----

def test_t0_revokes_private_ro_grants_only(past_due_env):
    env = past_due_env
    result = _run(env, days=GRACE_DAYS)
    assert result["revoked"], "T-0 (+30d) must revoke private-library RO grants (Decision 8-A)"
    revoked_libs = {str(r["library_id"]) for r in result["revoked"]}
    assert env["private_lib"] in revoked_libs

    # RO key grant on the private lib is gone — and NOT escalated to writer.
    roles_after = _roles(env["ro_key_id"], env["private_lib"])
    assert "writer" not in roles_after, "must NEVER escalate RO->RW on private libs (§0.1(5))"
    assert "reader" not in roles_after

    # RO library grant revoked too.
    grant = db.get_library_grant(env["private_lib"], env["reader_pid"])
    assert grant is None or str(grant.get("role")) != "reader"

    # Community lib_default grants are untouched (contribution-first invariant).
    assert env["private_lib"] != settings.default_library_id
    assert settings.default_library_id not in revoked_libs
    assert _roles(env["ro_key_id"], settings.default_library_id) == {"reader"}

    # Pre-existing RW grants on the private lib are not the job's business.
    assert _roles(env["rw_key_id"], env["private_lib"]) == {"writer"}


# --- BP1-G3: notifications at T-7 / T-1 / T-0 -----------------------------------

@pytest.mark.parametrize(
    ("days", "kind"),
    [(GRACE_DAYS - 7, "T-7"), (GRACE_DAYS - 1, "T-1"), (GRACE_DAYS, "T-0")],
)
def test_notification_schedule(past_due_env, days, kind):
    env = past_due_env
    result = _run(env, days=days)
    kinds = {
        str(n["kind"])
        for n in result["notifications"]
        if str(n["billing_account_id"]) == env["ba_id"]
    }
    assert kind in kinds, (
        f"grace job at day {days} must emit the {kind} banner/email notification "
        "(Decision 8-A: T-7 / T-1 / T-0)"
    )


def test_notifications_not_duplicated(past_due_env):
    env = past_due_env
    first = _run(env, days=GRACE_DAYS - 7)
    assert any(n["kind"] == "T-7" for n in first["notifications"])
    second = _run(env, days=GRACE_DAYS - 7)
    assert not any(
        n["kind"] == "T-7" and str(n["billing_account_id"]) == env["ba_id"]
        for n in second["notifications"]
    ), "re-running the job the same day must not re-send the T-7 email"


# --- BP1-G4: paying before T-0 cancels the revoke ---------------------------------

def test_reactivation_before_t0_cancels_revoke(past_due_env):
    env = past_due_env
    set_ba_status(env["ba_id"], "active")
    result = _run(env, days=GRACE_DAYS + 1)
    assert result["revoked"] == []
    assert _roles(env["ro_key_id"], env["private_lib"]) == {"reader"}


# --- BP1-G5: idempotency ------------------------------------------------------------

def test_second_run_revokes_nothing_new(past_due_env):
    env = past_due_env
    first = _run(env, days=GRACE_DAYS)
    assert first["revoked"]
    second = _run(env, days=GRACE_DAYS + 1)
    assert second["revoked"] == [], "revoke must be idempotent across runs"
