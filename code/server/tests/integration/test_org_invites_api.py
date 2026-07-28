"""Org invite links: create, register-with-invite, one-time consume."""
from __future__ import annotations

from app.core.config import settings

_JSON = {"Content-Type": "application/json"}


def _enable_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    monkeypatch.setattr(settings, "authing_app_id", "")
    monkeypatch.setattr(settings, "authing_app_secret", "")
    monkeypatch.setattr(settings, "local_auth", True)
    monkeypatch.setattr(settings, "local_auth_open_registration", True)
    monkeypatch.setattr(settings, "api_key_encryption_secret", "test-local-api-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ())
    monkeypatch.setattr(settings, "plan_max_team_orgs_owned_free", 0)
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")


def _admin(client) -> tuple[str, str]:
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "invadmin",
            "password": "password123",
            "display_name": "Invite Admin",
            "api_key": {"label": "admin-key"},
        },
    )
    assert reg.status_code == 201, reg.text
    key = reg.json()["api_key"]["plaintext_key"]
    org = client.post(
        "/api/orgs",
        headers={"X-API-Key": key, **_JSON},
        json={"name": "Invite Team"},
    )
    assert org.status_code == 201, org.text
    return key, org.json()["id"]


def test_invite_register_joins_org_even_when_registration_closed(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    admin_key, org_id = _admin(isolated_client)
    headers = {"X-API-Key": admin_key, **_JSON}

    created = isolated_client.post(
        f"/api/orgs/{org_id}/invites",
        headers=headers,
        json={
            "role": "member",
            "max_uses": 1,
            "expires_in_hours": 24,
            "member_alias": "小张",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["token"].startswith("ma3inv_")
    assert body["member_alias"] == "小张"
    assert "/auth/register?invite=" in body["invite_url"]
    token = body["token"]

    # Close open registration — invite should still work
    closed = isolated_client.patch(
        "/api/setup/registration",
        headers=headers,
        json={"open": False},
    )
    assert closed.status_code == 200

    blocked = isolated_client.post(
        "/api/auth/register",
        json={"username": "noinvite", "password": "password123"},
    )
    assert blocked.status_code == 403

    preview = isolated_client.get("/api/invites/preview", params={"token": token})
    assert preview.status_code == 200
    assert preview.json()["org_id"] == org_id
    assert preview.json()["member_alias"] == "小张"

    joined = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "newbie",
            "password": "password123",
            "display_name": "New Friend",
            "invite": token,
            "api_key": {"label": "newbie-key"},
        },
    )
    assert joined.status_code == 201, joined.text
    membership = joined.json()["org_membership"]
    assert membership["org_id"] == org_id
    assert membership["role"] == "member"
    assert membership["alias"] == "小张"
    assert membership["consumed"] is True

    # One-time: second redeem fails
    second = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "newbie2",
            "password": "password123",
            "invite": token,
        },
    )
    assert second.status_code in {400, 410}

    members = isolated_client.get(f"/api/orgs/{org_id}/members", headers={"X-API-Key": admin_key})
    assert members.status_code == 200
    by_pid = {m["principal_id"]: m for m in members.json()["members"]}
    newbie_pid = joined.json()["account"]["principal_id"]
    assert newbie_pid in by_pid
    assert by_pid[newbie_pid]["alias"] == "小张"


def test_existing_user_redeems_invite(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    admin_key, org_id = _admin(isolated_client)
    # Keep registration open for second account
    member = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "existing",
            "password": "password123",
            "api_key": {"label": "ex-key"},
        },
    )
    assert member.status_code == 201
    member_key = member.json()["api_key"]["plaintext_key"]

    inv = isolated_client.post(
        f"/api/orgs/{org_id}/invites",
        headers={"X-API-Key": admin_key, **_JSON},
        json={"max_uses": 5},
    )
    token = inv.json()["token"]
    redeemed = isolated_client.post(
        "/api/invites/redeem",
        headers={"X-API-Key": member_key, **_JSON},
        json={"token": token},
    )
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["org_id"] == org_id


def test_patch_member_alias(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    admin_key, org_id = _admin(isolated_client)
    member = isolated_client.post(
        "/api/auth/register",
        json={"username": "aliastarget", "password": "password123", "api_key": {"label": "k"}},
    )
    pid = member.json()["account"]["principal_id"]
    headers = {"X-API-Key": admin_key, **_JSON}
    isolated_client.post(
        f"/api/orgs/{org_id}/members",
        headers=headers,
        json={"principal_id": pid, "alias": "阿狸"},
    )
    patched = isolated_client.patch(
        f"/api/orgs/{org_id}/members/{pid}",
        headers=headers,
        json={"alias": "小狸"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["alias"] == "小狸"
