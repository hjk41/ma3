"""REST APIs for orgs, libraries, keys (X-API-Key), and admin."""
from __future__ import annotations

from app.core.config import settings
from app.services import local_auth_service

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


def _register_admin(client, *, username: str = "orgadmin", label: str = "org-admin-key") -> str:
    reg = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "password123",
            "display_name": f"User {username}",
            "api_key": {"label": label},
        },
    )
    assert reg.status_code == 201, reg.text
    return reg.json()["api_key"]["plaintext_key"]


def test_agent_org_member_library_and_keys_flow(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    admin_key = _register_admin(isolated_client)
    headers = {"X-API-Key": admin_key, **_JSON}

    me = isolated_client.get("/api/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["is_admin"] is True
    assert me.json()["username"] == "orgadmin"

    keys = isolated_client.get("/api/keys", headers=headers)
    assert keys.status_code == 200, keys.text
    assert len(keys.json()["keys"]) >= 1

    created_key = isolated_client.post(
        "/api/keys",
        headers=headers,
        json={"label": "second-agent"},
    )
    assert created_key.status_code == 200, created_key.text
    assert created_key.json()["plaintext_key"].startswith("ma3k_")

    org = isolated_client.post("/api/orgs", headers=headers, json={"name": "Acme Team"})
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    assert org.json()["kind"] == "team"

    # Open registration and create a second user
    isolated_client.patch(
        "/api/setup/registration",
        headers=headers,
        json={"open": True},
    )
    member_reg = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "teammate",
            "password": "password123",
            "display_name": "Teammate One",
            "api_key": {"label": "member-key"},
        },
    )
    assert member_reg.status_code == 201, member_reg.text
    member_key = member_reg.json()["api_key"]["plaintext_key"]
    member_pid = member_reg.json()["account"]["principal_id"]

    added = isolated_client.post(
        f"/api/orgs/{org_id}/members",
        headers=headers,
        json={"username": "teammate", "role": "member"},
    )
    assert added.status_code == 201, added.text
    assert added.json()["principal_id"] == member_pid

    members = isolated_client.get(f"/api/orgs/{org_id}/members", headers=headers)
    assert members.status_code == 200
    assert len(members.json()["members"]) == 2

    lib = isolated_client.post(
        f"/api/orgs/{org_id}/libraries",
        headers=headers,
        json={"name": "Eng Notes", "visibility": "private"},
    )
    assert lib.status_code == 201, lib.text
    library_id = lib.json()["library_id"]

    grant = isolated_client.post(
        f"/api/libraries/{library_id}/grants",
        headers=headers,
        json={"username": "teammate", "role": "writer"},
    )
    assert grant.status_code == 201, grant.text

    member_headers = {"X-API-Key": member_key}
    member_libs = isolated_client.get("/api/libraries", headers=member_headers)
    assert member_libs.status_code == 200, member_libs.text
    lib_ids = {row["library_id"] for row in member_libs.json()["libraries"]}
    assert library_id in lib_ids

    storage = isolated_client.get(f"/api/libraries/{library_id}/storage", headers=headers)
    assert storage.status_code == 200

    settings_get = isolated_client.get(f"/api/libraries/{library_id}/settings", headers=headers)
    assert settings_get.status_code == 200
    patched = isolated_client.patch(
        f"/api/libraries/{library_id}/settings",
        headers=headers,
        json={"write_buffer_hours": 12},
    )
    assert patched.status_code == 200
    assert patched.json()["write_buffer_hours"] == 12

    stats = isolated_client.get("/api/admin/observatory/stats", headers=headers)
    assert stats.status_code == 200
    assert "libraries" in stats.json()


def test_bootstrap_key_cannot_manage_orgs(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="owner", password="password123")
    from app.services.onboarding_service import create_personal_dev_key
    from app.storage import db

    bootstrap_pid = settings.bootstrap_principal_id
    db.upsert_user_principal(sso_user="selfhost-admin", display_name="Bootstrap")
    created = create_personal_dev_key(bootstrap_pid, "Bootstrap", label="boot-org")
    resp = isolated_client.get(
        "/api/orgs",
        headers={"X-API-Key": created["plaintext_key"]},
    )
    assert resp.status_code == 403, resp.text
    assert "bootstrap" in resp.json()["detail"].lower()
