"""P0 seat enforcement scenarios (design/27 §0.1(2), §4, §6 seat row, §10 P0).

These run against the shipped HTTP surface and FAIL until Composer lands
seat enforcement (they currently observe the pre-P0 behavior where invites,
redeems and direct adds ignore seat caps entirely).

Contract encoded here:
- team_stub included_seats = 3 (Decision 5a=A, §9.1);
  seats_used = active members + remaining_uses of non-expired invites.
- invite create at cap → 403 {"error": "seat_limit_exceeded", used,
  included_seats, upgrade_url} (§8.2; §10 P0 acceptance wording).
- invite create below cap clamps max_uses to remaining seats (§0.1(2)).
- invite redeem of a pre-existing token at cap → 403 seat_limit_exceeded.
- direct member add at cap (incl. cap consumed by reservations) → 403.
- personal org direct add → 403 (security fix, ships in P0 per Decision 7).
- grandfathered over-cap orgs: existing members keep seats, new adds blocked
  (Decision 4-A); member removal + last-admin protection unaffected.
- admission is one atomic transaction (§0.1(2) admit_org_member): the
  concurrency test below must never oversell on SQLite (BEGIN IMMEDIATE)
  or Postgres (pg_advisory_xact_lock).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.storage import db
from tests.helpers.billing_p0 import (
    TEAM_STUB_SEATS,
    auth_headers,
    create_team_org_via_api,
    enable_local_auth,
    error_code,
    personal_org_row,
    register_user,
)

pytestmark = pytest.mark.billing_p0


@pytest.fixture()
def team_env(isolated_client, monkeypatch):
    """Product admin + Pro (env-allowlisted) creator + a team_stub org."""
    enable_local_auth(monkeypatch)
    client = isolated_client
    # First registered local account is the product admin; keep it out of the org.
    admin = register_user(client, "seatprodadmin")
    creator = register_user(client, "seatcreator")
    monkeypatch.setattr(settings, "paid_principal_ids", (creator["principal_id"],))
    org_id = create_team_org_via_api(client, creator["api_key"], name="Seat Cap Team")
    return {"client": client, "admin": admin, "creator": creator, "org_id": org_id}


def _add_member(client, api_key: str, org_id: str, principal_id: str):
    return client.post(
        f"/api/orgs/{org_id}/members",
        headers=auth_headers(api_key),
        json={"principal_id": principal_id},
    )


def _fill_to_cap(team_env, *, count: int = TEAM_STUB_SEATS - 1) -> list[dict]:
    """Bring the org to `1 + count` active seats via the normal add path."""
    client = team_env["client"]
    members = []
    for i in range(count):
        user = register_user(client, f"seatmember{i}")
        response = _add_member(
            client, team_env["creator"]["api_key"], team_env["org_id"], user["principal_id"]
        )
        assert response.status_code == 201, (
            f"adding member {i + 1} of {count} below the cap must succeed: {response.text}"
        )
        members.append(user)
    return members


def _assert_seat_limit_error(response, *, context: str) -> None:
    assert response.status_code == 403, f"{context}: expected 403, got {response.status_code}: {response.text}"
    assert error_code(response) == "seat_limit_exceeded", f"{context}: {response.text}"
    detail = response.json()["detail"]
    # §8.2 structured payload; upgrade_url may be None/absent pre-Checkout (Decision 7).
    assert "used" in detail and "included_seats" in detail, detail
    assert int(detail["included_seats"]) == TEAM_STUB_SEATS


# --- BP0-S1: invite create at cap -------------------------------------------

def test_invite_create_at_cap_403(team_env):
    _fill_to_cap(team_env)
    response = team_env["client"].post(
        f"/api/orgs/{team_env['org_id']}/invites",
        headers=auth_headers(team_env["creator"]["api_key"]),
        json={"role": "member", "max_uses": 1},
    )
    _assert_seat_limit_error(response, context="invite create at 3 active seats")


# --- BP0-S2: invite create clamps max_uses to remaining seats ----------------

def test_invite_create_clamps_max_uses_to_remaining_seats(team_env):
    # 1 active seat (creator) of 3 → 2 remaining.
    response = team_env["client"].post(
        f"/api/orgs/{team_env['org_id']}/invites",
        headers=auth_headers(team_env["creator"]["api_key"]),
        json={"role": "member", "max_uses": 5},
    )
    assert response.status_code == 201, response.text
    assert response.json()["max_uses"] == TEAM_STUB_SEATS - 1, (
        "invite creation must reserve capacity and clamp max_uses to remaining seats (§0.1(2))"
    )


# --- BP0-S3: pending invite reservations block direct add --------------------

def test_pending_invite_reservation_blocks_direct_add(team_env):
    client = team_env["client"]
    created = client.post(
        f"/api/orgs/{team_env['org_id']}/invites",
        headers=auth_headers(team_env["creator"]["api_key"]),
        json={"role": "member", "max_uses": 2, "expires_in_hours": 24},
    )
    assert created.status_code == 201, created.text
    # 1 active + 2 reserved = 3 = cap → direct add must be refused.
    outsider = register_user(client, "seatoutsider1")
    response = _add_member(
        client, team_env["creator"]["api_key"], team_env["org_id"], outsider["principal_id"]
    )
    _assert_seat_limit_error(response, context="direct add with cap consumed by reservations")


# --- BP0-S4: redeem of a pre-existing token at cap ---------------------------

def test_redeem_preexisting_invite_at_cap_403(team_env):
    client = team_env["client"]
    org_id = team_env["org_id"]
    created = client.post(
        f"/api/orgs/{org_id}/invites",
        headers=auth_headers(team_env["creator"]["api_key"]),
        json={"role": "member", "max_uses": 1, "expires_in_hours": 24},
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]

    # Simulate a grandfathered org that reached the cap after the invite was
    # minted (db-level seeding bypasses enforcement on purpose, Decision 4-A).
    for i in range(2):
        user = register_user(client, f"seatgrandfather{i}")
        db.add_org_member(org_id=org_id, principal_id=user["principal_id"], role="member")
    assert db.count_active_org_members(org_id) == TEAM_STUB_SEATS

    outsider = register_user(client, "seatoutsider2")
    redeemed = client.post(
        "/api/invites/redeem",
        headers=auth_headers(outsider["api_key"]),
        json={"token": token},
    )
    _assert_seat_limit_error(redeemed, context="redeem pre-existing token at cap")
    member = db.get_org_member(org_id, outsider["principal_id"])
    assert not member or member.get("seat_status") != "active"


# --- BP0-S5: direct add at cap -----------------------------------------------

def test_direct_add_at_cap_403(team_env):
    _fill_to_cap(team_env)
    outsider = register_user(team_env["client"], "seatoutsider3")
    response = _add_member(
        team_env["client"], team_env["creator"]["api_key"], team_env["org_id"],
        outsider["principal_id"],
    )
    _assert_seat_limit_error(response, context="direct add at 3 active seats")
    assert db.count_active_org_members(team_env["org_id"]) == TEAM_STUB_SEATS


# --- BP0-S6: personal org direct add blocked (security fix) ------------------

def test_personal_org_direct_add_blocked(isolated_client, monkeypatch):
    """§0 ground truth: today direct add into a personal org SUCCEEDS; P0
    closes it (Decision 7: security fix, not a monetization gate).
    Personal orgs stay hard-1 (§6 seat row)."""
    enable_local_auth(monkeypatch)
    client = isolated_client
    register_user(client, "personaladmin")  # absorb product-admin slot
    owner = register_user(client, "personalowner")
    other = register_user(client, "personalother")
    personal = personal_org_row(client, owner["api_key"])
    response = _add_member(client, owner["api_key"], personal["id"], other["principal_id"])
    assert response.status_code == 403, (
        f"direct add into a personal org must be blocked in P0: {response.status_code} {response.text}"
    )
    assert error_code(response) == "seat_limit_exceeded", response.text
    assert db.count_active_org_members(personal["id"]) == 1

    # Invite creation into personal orgs was already blocked — regression guard.
    invite = client.post(
        f"/api/orgs/{personal['id']}/invites",
        headers=auth_headers(owner["api_key"]),
        json={"role": "member"},
    )
    assert invite.status_code == 400


# --- BP0-S7: grandfathered over-cap org (Decision 4-A) ------------------------

def test_grandfathered_over_cap_org_keeps_members_blocks_new_adds(team_env):
    client = team_env["client"]
    org_id = team_env["org_id"]
    creator = team_env["creator"]
    # Seed straight past the cap at db level (pre-P0 state being migrated).
    seeded = []
    for i in range(4):
        user = register_user(client, f"seatlegacy{i}")
        db.add_org_member(org_id=org_id, principal_id=user["principal_id"], role="member")
        seeded.append(user)
    assert db.count_active_org_members(org_id) == 5  # over the stub cap of 3

    # Existing members keep their seats and stay listed.
    members = client.get(f"/api/orgs/{org_id}/members", headers=auth_headers(creator["api_key"]))
    assert members.status_code == 200
    active = [m for m in members.json()["members"] if m["seat_status"] == "active"]
    assert len(active) == 5

    # Net-new admission is blocked...
    newcomer = register_user(client, "seatnewcomer")
    blocked = _add_member(client, creator["api_key"], org_id, newcomer["principal_id"])
    _assert_seat_limit_error(blocked, context="add to grandfathered over-cap org")

    # ...but removal always works (never auto-remove, but manual remove is fine).
    removed = client.delete(
        f"/api/orgs/{org_id}/members/{seeded[0]['principal_id']}",
        headers=auth_headers(creator["api_key"]),
    )
    assert removed.status_code == 200, removed.text

    # Last-admin protection untouched (§10 P0 bullet 3).
    last_admin = client.delete(
        f"/api/orgs/{org_id}/members/{creator['principal_id']}",
        headers=auth_headers(creator["api_key"]),
    )
    assert last_admin.status_code == 403
    assert error_code(last_admin) == "last_org_admin"


# --- BP0-S8: concurrent admission never oversells (§0.1(2), §12 seat race) ---

def test_concurrent_direct_adds_never_oversell(team_env):
    """TOCTOU race: 2 active seats, 5 concurrent adds → exactly 1 winner.

    SQLite note (§0.1(2)): admission must run as one transaction under
    BEGIN IMMEDIATE (single writer), so even under threads the cap holds.
    On Postgres the same test exercises pg_advisory_xact_lock. If this
    flakes with `database is locked` errors the implementation must retry
    inside admit_org_member, not the caller.
    """
    client = team_env["client"]
    org_id = team_env["org_id"]
    creator_key = team_env["creator"]["api_key"]
    member = register_user(client, "seatracemember")
    assert _add_member(client, creator_key, org_id, member["principal_id"]).status_code == 201
    assert db.count_active_org_members(org_id) == 2

    candidates = [register_user(client, f"seatracer{i}") for i in range(5)]

    def _try_add(user):
        return _add_member(client, creator_key, org_id, user["principal_id"])

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(_try_add, candidates))

    winners = [r for r in responses if r.status_code == 201]
    losers = [r for r in responses if r.status_code == 403]
    assert db.count_active_org_members(org_id) == TEAM_STUB_SEATS, (
        f"seat oversell: {[r.status_code for r in responses]}"
    )
    assert len(winners) == 1
    assert len(losers) == len(candidates) - 1
    for loser in losers:
        assert error_code(loser) == "seat_limit_exceeded"


# --- BP0-S9: expired reservations release capacity ---------------------------

def test_expired_invite_releases_reserved_seats(team_env):
    """Only NON-expired invites reserve seats (§0.1(2))."""
    client = team_env["client"]
    org_id = team_env["org_id"]
    # Expired invite for 2 uses seeded at db level (can't create expired via API).
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db.create_org_invite(
        invite_id=db.new_id("inv"),
        org_id=org_id,
        token_hash="c" * 64,
        role="member",
        created_by=team_env["creator"]["principal_id"],
        max_uses=2,
        expires_at=past,
        member_alias=None,
    )
    fresh = register_user(client, "seatfresh")
    response = _add_member(client, team_env["creator"]["api_key"], org_id, fresh["principal_id"])
    assert response.status_code == 201, (
        f"expired invites must not reserve seats: {response.status_code} {response.text}"
    )
