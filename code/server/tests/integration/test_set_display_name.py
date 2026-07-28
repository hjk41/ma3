"""Integration tests for registration display name setup (/ui/me/setup/)."""
from __future__ import annotations

import secrets

import pytest

from app.auth.authing_client import AuthingUser
from app.auth.session import SessionUser
from app.core.config import settings
from app.services.api_key_service import hash_key
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import complete_display_name_setup, ensure_user_principal
from app.storage import db
from tests.helpers.mcp_client import McpClient

_ORIGIN = {
    "Origin": "http://testserver",
    "Referer": "http://testserver/ui/me/setup/",
}


@pytest.fixture()
def display_name_user() -> SessionUser:
    return SessionUser(
        principal_id="user:6a45abec4d2ef946d80649f6",
        sub="6a45abec4d2ef946d80649f6",
        display_name="6a45abec4d2ef946d80649f6",
        email=None,
        phone=None,
        is_admin=False,
    )


def _enable_authing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "auth_admin_users", [])


def _patch_session_from_db(monkeypatch, user: SessionUser) -> None:
    import app.api.ui_session as ui_session
    import app.auth.session as session_mod
    import app.services.portal_actor_service as portal_actor_service

    def _resolve(_req):
        row = db.get_user_principal(user.principal_id)
        assert row is not None
        return SessionUser(
            principal_id=user.principal_id,
            sub=user.sub,
            display_name=str(row["display_name"]),
            email=user.email,
            phone=user.phone,
            is_admin=user.is_admin,
        )

    monkeypatch.setattr(session_mod, "resolve_session_user", _resolve)
    monkeypatch.setattr(ui_session, "resolve_session_user", _resolve)
    monkeypatch.setattr(portal_actor_service, "resolve_session_user", _resolve)


def _seed_api_key(principal_id: str) -> str:
    plaintext = f"ma3v4_{secrets.token_hex(16)}"
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(6)}",
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label="display-name-test",
        grants=[{"library_id": settings.default_library_id, "role": "writer"}],
    )
    return plaintext


@pytest.fixture()
def authing_setup_client(isolated_client, monkeypatch, display_name_user):
    _enable_authing(monkeypatch)
    db.upsert_user_principal(
        sso_user=display_name_user.sub,
        display_name=display_name_user.sub,
    )
    ensure_personal_library(display_name_user.principal_id, display_name_user.sub)
    _patch_session_from_db(monkeypatch, display_name_user)
    return isolated_client


def test_setup_display_name_updates_db_mcp_and_personal_library(
    authing_setup_client,
    display_name_user,
):
    client = authing_setup_client
    mcp = McpClient(client)
    api_key = _seed_api_key(display_name_user.principal_id)

    before = mcp.structured("ma3_whoami", api_key=api_key)
    assert before["caller"]["display_name"] == display_name_user.sub

    response = client.post(
        "/ui/me/setup/",
        data={"display_name": "小明", "next": "/ui/me/"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/ui/me/"

    row = db.get_user_principal(display_name_user.principal_id)
    assert row["display_name"] == "小明"
    assert row["display_name_locked"]
    personal = db.find_personal_library(display_name_user.principal_id)
    assert personal["name"] == "小明 的个人库"

    after = mcp.structured("ma3_whoami", api_key=api_key)
    assert after["caller"]["display_name"] == "小明"


def test_setup_rejects_uuid_like_name(authing_setup_client, display_name_user):
    client = authing_setup_client
    response = client.post(
        "/ui/me/setup/",
        data={"display_name": "6a45abec4d2ef946d80649f6", "next": "/ui/me/"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    row = db.get_user_principal(display_name_user.principal_id)
    assert row["display_name"] == display_name_user.sub
    assert not row.get("display_name_locked")


def test_me_redirects_to_setup_until_display_name_locked(authing_setup_client):
    response = authing_setup_client.get("/ui/me/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/ui/me/setup/")


def test_display_name_cannot_be_changed_after_setup(authing_setup_client, display_name_user):
    complete_display_name_setup(display_name_user.principal_id, "锁定昵称")
    response = authing_setup_client.post(
        "/ui/me/setup/",
        data={"display_name": "新名字", "next": "/ui/me/"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert db.get_user_principal(display_name_user.principal_id)["display_name"] == "锁定昵称"


def test_settings_post_rejects_display_name_change(authing_setup_client, display_name_user):
    complete_display_name_setup(display_name_user.principal_id, "锁定昵称")
    response = authing_setup_client.post(
        "/ui/me/settings/",
        data={"display_name": "新名字"},
        headers={"Origin": "http://testserver", "Referer": "http://testserver/ui/me/settings/"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_authing_resync_preserves_user_chosen_display_name(isolated_client, display_name_user):
    ensure_user_principal(
        AuthingUser(
            sub=display_name_user.sub,
            display_name=display_name_user.sub,
            email=None,
            phone=None,
            username=None,
            photo=None,
            is_admin=False,
        )
    )
    ensure_personal_library(display_name_user.principal_id, display_name_user.sub)
    complete_display_name_setup(display_name_user.principal_id, "锁定昵称")

    ensure_user_principal(
        AuthingUser(
            sub=display_name_user.sub,
            display_name="6a45abec4d2ef946d80649f6",
            email=None,
            phone=None,
            username=None,
            photo=None,
            is_admin=False,
        )
    )
    row = db.get_user_principal(display_name_user.principal_id)
    assert row["display_name"] == "锁定昵称"
    personal = db.find_personal_library(display_name_user.principal_id)
    assert personal["name"] == "锁定昵称 的个人库"


def test_setup_rejects_duplicate_via_portal(isolated_client, monkeypatch):
    user_a = SessionUser(
        principal_id="user:dup-a",
        sub="dup-a",
        display_name="dup-a",
        email=None,
        phone=None,
        is_admin=False,
    )
    user_b = SessionUser(
        principal_id="user:dup-b",
        sub="dup-b",
        display_name="dup-b",
        email=None,
        phone=None,
        is_admin=False,
    )
    _enable_authing(monkeypatch)
    db.upsert_user_principal(sso_user=user_a.sub, display_name=user_a.sub)
    db.upsert_user_principal(sso_user=user_b.sub, display_name=user_b.sub)
    complete_display_name_setup(user_a.principal_id, "小明")
    _patch_session_from_db(monkeypatch, user_b)

    response = isolated_client.post(
        "/ui/me/setup/",
        data={"display_name": "小明", "next": "/ui/me/"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert db.get_user_principal(user_b.principal_id)["display_name"] == "dup-b"
