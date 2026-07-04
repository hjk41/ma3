"""Integration tests for user display name (设定用户名 / /ui/me/settings/)."""
from __future__ import annotations

import secrets

import pytest

from app.auth.authing_client import AuthingUser
from app.auth.session import SessionUser
from app.core.config import settings
from app.services.api_key_service import hash_key
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import ensure_user_principal, update_user_display_name
from app.storage import db
from tests.helpers.mcp_client import McpClient

_ORIGIN = {
    "Origin": "http://testserver",
    "Referer": "http://testserver/ui/me/settings/",
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
def authing_settings_client(isolated_client, monkeypatch, display_name_user):
    _enable_authing(monkeypatch)
    db.upsert_user_principal(
        sso_user=display_name_user.sub,
        display_name=display_name_user.display_name,
    )
    ensure_personal_library(display_name_user.principal_id, display_name_user.display_name)
    _patch_session_from_db(monkeypatch, display_name_user)
    return isolated_client


def test_set_display_name_via_portal_updates_db_mcp_and_personal_library(
    authing_settings_client,
    display_name_user,
):
    """设定用户名：门户保存后 DB、个人库、MCP whoami、设置页一致。"""
    client = authing_settings_client
    mcp = McpClient(client)
    api_key = _seed_api_key(display_name_user.principal_id)

    before = mcp.structured("ma3_whoami", api_key=api_key)
    assert before["caller"]["display_name"] == display_name_user.sub
    personal_before = db.find_personal_library(display_name_user.principal_id)
    assert personal_before["name"] == f"{display_name_user.sub} 的个人库"

    response = client.post(
        "/ui/me/settings/",
        data={"display_name": "小明"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/me/settings/?saved=1")

    row = db.get_user_principal(display_name_user.principal_id)
    assert row["display_name"] == "小明"
    personal = db.find_personal_library(display_name_user.principal_id)
    assert personal["name"] == "小明 的个人库"

    after = mcp.structured("ma3_whoami", api_key=api_key)
    assert after["caller"]["display_name"] == "小明"
    personal_after = db.find_personal_library(display_name_user.principal_id)
    assert personal_after["name"] == "小明 的个人库"

    page = client.get("/ui/me/settings/")
    assert "小明" in page.text
    assert "显示名已保存" not in page.text


def test_set_display_name_rejects_uuid_like_name(authing_settings_client, display_name_user):
    client = authing_settings_client
    response = client.post(
        "/ui/me/settings/",
        data={"display_name": "6a45abec4d2ef946d80649f6"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "internal id" in response.json()["detail"]
    row = db.get_user_principal(display_name_user.principal_id)
    assert row["display_name"] == display_name_user.sub


def test_authing_resync_preserves_user_chosen_display_name(isolated_client, display_name_user):
    """Authing 再次登录不应覆盖用户已锁定的显示名。"""
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
    update_user_display_name(display_name_user.principal_id, "锁定昵称")

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
