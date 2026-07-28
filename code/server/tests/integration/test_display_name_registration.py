"""Integration tests — display name registration constraints.

1. 注册时提示设定显示名（Authing 回调 → /ui/me/setup/）
2. 只能设定一次（display_name_locked 后不可改）
3. 显示名全局唯一（不区分大小写）
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.auth.session import SessionUser
from app.core.config import settings
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import complete_display_name_setup, ensure_user_principal
from app.storage import db

_ORIGIN_SETUP = {
    "Origin": "http://testserver",
    "Referer": "http://testserver/ui/me/setup/",
}
_ORIGIN_SETTINGS = {
    "Origin": "http://testserver",
    "Referer": "http://testserver/ui/me/settings/",
}


@pytest.fixture()
def new_user() -> SessionUser:
    return SessionUser(
        principal_id="user:reg-newbie",
        sub="reg-newbie",
        display_name="reg-newbie",
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
    import app.api.routes_keys as routes_keys
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
    monkeypatch.setattr(routes_keys, "resolve_session_user", _resolve)
    monkeypatch.setattr(portal_actor_service, "resolve_session_user", _resolve)


@pytest.fixture()
def unlocked_client(isolated_client, monkeypatch, new_user):
    _enable_authing(monkeypatch)
    ensure_user_principal(
        type(
            "U",
            (),
            {
                "sub": new_user.sub,
                "display_name": new_user.sub,
                "email": None,
                "phone": None,
                "username": None,
                "photo": None,
                "is_admin": False,
            },
        )()
    )
    ensure_personal_library(new_user.principal_id, new_user.sub)
    _patch_session_from_db(monkeypatch, new_user)
    return isolated_client


# --- Constraint 1: registration prompts display name setup ---


def test_registration_callback_redirects_new_user_to_setup(unlocked_client):
    """Authing 首次登录/注册回调应重定向到 /ui/me/setup/。"""
    unlocked_client.cookies.set(settings.auth_oauth_state_cookie, "state-reg")
    unlocked_client.cookies.set("ma3_oauth_next", "/ui/me/")

    fake_user = type(
        "U",
        (),
        {
            "sub": "reg-newbie",
            "display_name": "Authing昵称",
            "email": None,
            "phone": None,
            "username": None,
            "photo": None,
            "is_admin": False,
        },
    )()

    with (
        patch("app.api.routes_auth.validate_oauth_state", return_value=True),
        patch("app.api.routes_auth.authing_client.exchange_code", return_value={"access_token": "atk_reg"}),
        patch("app.api.routes_auth.authing_client.resolve_user", return_value=fake_user),
    ):
        response = unlocked_client.get(
            "/auth/callback?code=abc&state=state-reg",
            follow_redirects=False,
        )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/ui/me/setup/?next=")
    assert settings.auth_session_cookie in response.cookies


def test_registration_setup_page_prompts_display_name(unlocked_client):
    """设定页应展示欢迎文案与约束说明。"""
    response = unlocked_client.get("/ui/me/setup/?next=/ui/me/", follow_redirects=False)
    assert response.status_code == 200
    text = response.text
    assert "设定显示名" in text
    assert "欢迎加入 ma3" in text
    assert "全局唯一" in text
    assert "不可修改" in text
    assert 'name="display_name"' in text


def test_portal_blocks_other_pages_until_display_name_set(unlocked_client):
    """未完成设定前，门户与 API Keys 应重定向到 setup。"""
    for path in ("/ui/me/", "/ui/keys/"):
        response = unlocked_client.get(path, follow_redirects=False)
        assert response.status_code == 302, path
        assert response.headers["location"].startswith("/ui/me/setup/")


def test_api_keys_json_blocked_until_display_name_set(unlocked_client):
    response = unlocked_client.get("/api/keys")
    assert response.status_code == 403
    assert "setup" in response.json()["detail"].lower()


# --- Constraint 2: one-time only ---


def test_display_name_can_only_be_set_once(unlocked_client, new_user):
    """显示名只能设定一次；之后 setup/settings 均不可再改。"""
    first = unlocked_client.post(
        "/ui/me/setup/",
        data={"display_name": "一次性昵称", "next": "/ui/me/"},
        headers=_ORIGIN_SETUP,
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert first.headers["location"] == "/ui/me/"
    row = db.get_user_principal(new_user.principal_id)
    assert row["display_name"] == "一次性昵称"
    assert row["display_name_locked"]

    setup_retry = unlocked_client.post(
        "/ui/me/setup/",
        data={"display_name": "试图改名", "next": "/ui/me/"},
        headers=_ORIGIN_SETUP,
        follow_redirects=False,
    )
    assert setup_retry.status_code == 400
    assert db.get_user_principal(new_user.principal_id)["display_name"] == "一次性昵称"

    settings_retry = unlocked_client.post(
        "/ui/me/settings/",
        data={"display_name": "试图改名"},
        headers=_ORIGIN_SETTINGS,
        follow_redirects=False,
    )
    assert settings_retry.status_code == 400

    setup_get = unlocked_client.get("/ui/me/setup/", follow_redirects=False)
    assert setup_get.status_code == 302
    assert setup_get.headers["location"] == "/ui/me/"

    settings_page = unlocked_client.get("/ui/me/settings/")
    assert "不可修改" in settings_page.text
    assert 'name="display_name"' not in settings_page.text


# --- Constraint 3: globally unique ---


def test_display_name_rejects_duplicate(unlocked_client, new_user, monkeypatch):
    """显示名已被占用时拒绝设定，且不锁定当前用户。"""
    _enable_authing(monkeypatch)
    db.upsert_user_principal(sso_user="existing-user", display_name="existing-user")
    complete_display_name_setup("user:existing-user", "已被占用")

    response = unlocked_client.post(
        "/ui/me/setup/",
        data={"display_name": "已被占用", "next": "/ui/me/"},
        headers=_ORIGIN_SETUP,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    page = unlocked_client.get(response.headers["location"])
    assert "已被使用" in page.text
    row = db.get_user_principal(new_user.principal_id)
    assert row["display_name"] == new_user.sub
    assert not row.get("display_name_locked")


def test_display_name_uniqueness_is_case_insensitive(unlocked_client, monkeypatch):
    """Alice 与 alice 视为同名。"""
    _enable_authing(monkeypatch)
    db.upsert_user_principal(sso_user="alice-owner", display_name="alice-owner")
    complete_display_name_setup("user:alice-owner", "Alice")

    response = unlocked_client.post(
        "/ui/me/setup/",
        data={"display_name": "alice", "next": "/ui/me/"},
        headers=_ORIGIN_SETUP,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
