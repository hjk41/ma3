"""REST APIs for local auth, setup, and local-user management."""
from __future__ import annotations

from app.core.config import settings
from app.services import local_auth_service, setup_service
from app.storage import db

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


def test_agent_day0_setup_via_rest(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    status = isolated_client.get("/api/setup/status")
    assert status.status_code == 200
    body = status.json()
    assert body["state"] == "needs_owner"
    assert body["local_auth_enabled"] is True

    reg = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "adminapi",
            "password": "password123",
            "display_name": "Admin API",
            "api_key": {"label": "first-admin-agent"},
        },
    )
    assert reg.status_code == 201, reg.text
    payload = reg.json()
    assert payload["account"]["is_admin"] is True
    assert payload["account"]["username"] == "adminapi"
    key = payload["api_key"]["plaintext_key"]
    assert key.startswith("ma3k_")

    headers = {"X-API-Key": key, **_JSON}
    mid = isolated_client.get("/api/setup/status")
    assert mid.json()["state"] == "guided_ramp"
    assert mid.json()["has_admin_key"] is True

    closed = isolated_client.patch(
        "/api/setup/registration",
        headers=headers,
        json={"open": False},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["registration_open"] is False
    assert closed.json()["registration_handled"] is True

    done = isolated_client.post("/api/setup/complete", headers=headers)
    assert done.status_code == 200, done.text
    assert done.json()["setup_complete"] is True
    assert done.json()["state"] == "steady"

    users = isolated_client.get("/api/local-users", headers={"X-API-Key": key})
    assert users.status_code == 200
    assert any(u["username"] == "adminapi" for u in users.json()["users"])

    blocked = isolated_client.post(
        "/api/auth/register",
        json={"username": "blocked", "password": "password123"},
    )
    assert blocked.status_code == 403


def test_register_without_key_then_login_mints(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    reg = isolated_client.post(
        "/api/auth/register",
        json={"username": "nokey", "password": "password123"},
    )
    assert reg.status_code == 201
    assert "api_key" not in reg.json()

    login = isolated_client.post(
        "/api/auth/login",
        json={
            "username": "nokey",
            "password": "password123",
            "api_key": {"label": "later-agent"},
        },
    )
    assert login.status_code == 200, login.text
    assert login.json()["api_key"]["plaintext_key"].startswith("ma3k_")


def test_bootstrap_key_cannot_manage_users(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="owner", password="password123")
    # Bootstrap principal key id from bootstrap_selfhost may exist after app lifespan;
    # invent a key for bootstrap principal if present, else skip via forbidden on random.
    from app.services.onboarding_service import create_personal_dev_key

    # Create a non-local-account principal key: use bootstrap principal if configured
    bootstrap_pid = settings.bootstrap_principal_id
    db.upsert_user_principal(sso_user="selfhost-admin", display_name="Bootstrap")
    # Ensure principal id matches bootstrap setting
    created = create_personal_dev_key(bootstrap_pid, "Bootstrap", label="boot")
    r = isolated_client.get(
        "/api/local-users",
        headers={"X-API-Key": created["plaintext_key"]},
    )
    assert r.status_code == 403
    assert "bootstrap" in r.json()["detail"].lower() or "local" in r.json()["detail"].lower()


def test_cannot_remove_last_admin(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    reg = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "soloadmin",
            "password": "password123",
            "api_key": {"label": "k"},
        },
    )
    key = reg.json()["api_key"]["plaintext_key"]
    r = isolated_client.patch(
        "/api/local-users/soloadmin",
        headers={"X-API-Key": key, **_JSON},
        json={"is_admin": False},
    )
    assert r.status_code == 409
    assert "last" in r.json()["detail"].lower()


def test_second_user_promote(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    admin = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "boss",
            "password": "password123",
            "api_key": {"label": "boss-key"},
        },
    ).json()
    key = admin["api_key"]["plaintext_key"]
    local_auth_service.register_local_user(username="member", password="password123")
    promoted = isolated_client.patch(
        "/api/local-users/member",
        headers={"X-API-Key": key, **_JSON},
        json={"is_admin": True},
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True


def test_ack_keep_open_then_complete(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    reg = isolated_client.post(
        "/api/auth/register",
        json={
            "username": "ackadmin",
            "password": "password123",
            "api_key": {"label": "ack-key"},
        },
    ).json()
    key = reg["api_key"]["plaintext_key"]
    headers = {"X-API-Key": key}
    ack = isolated_client.post("/api/setup/registration/ack", headers=headers)
    assert ack.status_code == 200
    assert ack.json()["registration_ack"] == "keep_open"
    assert setup_service.checklist_ready_to_finish() is True
    done = isolated_client.post("/api/setup/complete", headers=headers)
    assert done.status_code == 200
