"""P1 API-key billing picker scenarios (design/27 §2 P1 row 2, §8.2, §12
billing-context spoofing, §10 P1 acceptance bullet 7).

Contract encoded here:
- ``POST /api/keys`` gains a REQUIRED billing context: ``billing_org_id``
  (the caller's personal org id, or a team org id).
  Missing → 400 {"error": "billing_context_required"} (§8.5 error codes).
- Personal org chosen → ``api_keys.billing_account_id`` = personal-org BA.
- Team org chosen + caller is an ACTIVE member → org BA (org-billed key).
- Team org chosen + caller NOT a member → 403 (server-side membership
  check, §12 "billing-context spoofing").
- The registration bootstrap key keeps defaulting to the owner's personal
  BA (server-side path; P0 backfill rule — regression guard).
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.storage import db
from tests.helpers.billing_p0 import api_key_billing_account_id
from tests.helpers.billing_p1 import (
    auth_headers,
    create_team_org_via_api,
    enable_local_auth,
    error_code,
    org_ba_id,
    personal_ba_id,
    personal_org_row,
    register_user,
)

pytestmark = pytest.mark.billing_p1


@pytest.fixture()
def key_env(isolated_client, monkeypatch):
    enable_local_auth(monkeypatch)
    client = isolated_client
    register_user(client, "p1keyadmin")  # absorb the product-admin first slot
    creator = register_user(client, "p1keycreator")
    outsider = register_user(client, "p1keyoutsider")
    monkeypatch.setattr(settings, "paid_principal_ids", (creator["principal_id"],))
    org_id = create_team_org_via_api(client, creator["api_key"], name="P1 Key Team")
    return {"client": client, "creator": creator, "outsider": outsider, "org_id": org_id}


def _create_key(client, api_key: str, payload: dict):
    return client.post("/api/keys", headers=auth_headers(api_key), json=payload)


# --- BP1-K1: billing context is required for new keys ----------------------------

def test_new_key_without_billing_context_400(key_env):
    response = _create_key(
        key_env["client"], key_env["creator"]["api_key"], {"label": "no-context"}
    )
    assert response.status_code == 400, (
        "P1: new keys must require choosing a billing context "
        f"(got {response.status_code}: {response.text})"
    )
    assert error_code(response) == "billing_context_required", response.text


# --- BP1-K2: personal billing context ----------------------------------------------

def test_new_key_personal_context_binds_personal_ba(key_env):
    client = key_env["client"]
    creator = key_env["creator"]
    personal = personal_org_row(client, creator["api_key"])
    response = _create_key(
        client,
        creator["api_key"],
        {"label": "personal-billed", "billing_org_id": personal["id"]},
    )
    assert response.status_code in {200, 201}, response.text
    body = response.json()
    ba_id = personal_ba_id(client, creator["api_key"])
    # Contract: the create response echoes the resolved billing account so the
    # picker UI can confirm the choice (fails pre-P1: field absent today).
    assert body.get("billing_account_id") == ba_id, (
        f"POST /api/keys must echo the resolved billing_account_id (§8.2); got {body}"
    )
    assert api_key_billing_account_id(body["key_id"]) == ba_id


# --- BP1-K3: team billing context (active member) ------------------------------------

def test_new_key_team_context_binds_org_ba(key_env):
    client = key_env["client"]
    creator = key_env["creator"]
    response = _create_key(
        client,
        creator["api_key"],
        {"label": "org-billed", "billing_org_id": key_env["org_id"]},
    )
    assert response.status_code in {200, 201}, response.text
    key_id = response.json()["key_id"]
    assert api_key_billing_account_id(key_id) == org_ba_id(key_env["org_id"]), (
        "team billing context must bind the key to the org BA (§8.2)"
    )


def test_removed_member_key_cannot_pick_org(key_env):
    """Membership is checked server-side at creation time: an ex-member
    (removed after joining) must not mint org-billed keys (§12)."""
    client = key_env["client"]
    creator = key_env["creator"]
    joiner = register_user(client, "p1keyjoiner")
    add = client.post(
        f"/api/orgs/{key_env['org_id']}/members",
        headers=auth_headers(creator["api_key"]),
        json={"principal_id": joiner["principal_id"]},
    )
    assert add.status_code == 201, add.text
    removed = client.delete(
        f"/api/orgs/{key_env['org_id']}/members/{joiner['principal_id']}",
        headers=auth_headers(creator["api_key"]),
    )
    assert removed.status_code == 200, removed.text

    response = _create_key(
        client, joiner["api_key"], {"label": "stale-member", "billing_org_id": key_env["org_id"]}
    )
    assert response.status_code == 403, (
        f"ex-member must not create org-billed keys: {response.status_code} {response.text}"
    )


# --- BP1-K4: non-member picking a team org → 403 --------------------------------------

def test_non_member_picking_team_org_403(key_env):
    """§10 P1 bullet 7: non-member picking a team org → 403."""
    response = _create_key(
        key_env["client"],
        key_env["outsider"]["api_key"],
        {"label": "spoofed", "billing_org_id": key_env["org_id"]},
    )
    assert response.status_code == 403, (
        f"non-member org billing context must be rejected: "
        f"{response.status_code} {response.text}"
    )
    # No key row must exist billed to the org BA for this outsider.
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT COUNT(*) AS c FROM api_keys WHERE principal_id = ? "
            "AND billing_account_id = ?",
            (key_env["outsider"]["principal_id"], org_ba_id(key_env["org_id"])),
        )
    assert int(row["c"]) == 0


# --- BP1-K5: registration bootstrap key stays personal-billed (regression) -------------

def test_registration_key_defaults_to_personal_ba(key_env):
    """P0 rule regression guard: the key minted during registration is billed
    to the owner's personal BA without any picker involvement."""
    client = key_env["client"]
    fresh = register_user(client, "p1keyfresh")
    keys = client.get("/api/keys", headers=auth_headers(fresh["api_key"]))
    assert keys.status_code == 200, keys.text
    listed = keys.json()["keys"] if isinstance(keys.json(), dict) else keys.json()
    assert listed, "registration must mint a bootstrap key"
    key_id = listed[0]["key_id"]
    assert api_key_billing_account_id(key_id) == personal_ba_id(client, fresh["api_key"])
