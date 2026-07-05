from __future__ import annotations

from unittest.mock import patch

import pytest

from app.auth.session import SessionUser
from app.core.config import settings
from app.services.portal_service import validate_authing_admin_config
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import complete_display_name_setup, ensure_user_principal
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "user portal test"}]
_ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture()
def portal_user() -> SessionUser:
    return SessionUser(
        principal_id="user:portal-a",
        sub="portal-a",
        display_name="Portal A",
        email=None,
        phone=None,
        is_admin=False,
    )


@pytest.fixture()
def admin_user() -> SessionUser:
    return SessionUser(
        principal_id="user:portal-admin",
        sub="portal-admin",
        display_name="Portal Admin",
        email=None,
        phone=None,
        is_admin=True,
    )


def _enable_authing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ["portal-admin"])


def _patch_session(monkeypatch, user: SessionUser | None) -> None:
    import app.api.ui_session as ui_session
    import app.auth.session as session_mod

    resolver = lambda _req: user
    monkeypatch.setattr(session_mod, "resolve_session_user", resolver)
    monkeypatch.setattr(ui_session, "resolve_session_user", resolver)


@pytest.fixture()
def authing_portal_client(isolated_client, monkeypatch, portal_user):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_library(portal_user.principal_id, portal_user.display_name)
    return isolated_client


@pytest.fixture()
def authing_admin_client(isolated_client, monkeypatch, admin_user):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, admin_user)
    db.upsert_user_principal(sso_user=admin_user.sub, display_name=admin_user.sub)
    complete_display_name_setup(admin_user.principal_id, admin_user.display_name)
    ensure_personal_library(admin_user.principal_id, admin_user.display_name)
    return isolated_client


def test_root_redirects_to_me(isolated_client):
    for path in ("/", "/ui", "/ui/"):
        response = isolated_client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/ui/me/"


def test_me_requires_login_when_authing_enabled(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    response = isolated_client.get("/ui/me/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login")


def test_me_overview_is_dashboard_without_account_chrome(authing_portal_client, portal_user):
    response = authing_portal_client.get("/ui/me/")
    assert response.status_code == 200
    assert "我的贡献" in response.text
    assert portal_user.display_name in response.text
    assert "编辑显示名" not in response.text
    assert "Principal ID" not in response.text
    assert portal_user.principal_id not in response.text
    assert 'class="copy-row"' not in response.text


def test_me_settings_shows_readonly_display_name_and_principal_id(authing_portal_client, portal_user):
    response = authing_portal_client.get("/ui/me/settings/")
    assert response.status_code == 200
    assert portal_user.display_name in response.text
    assert portal_user.principal_id in response.text
    assert "Principal ID" in response.text
    assert "不可修改" in response.text
    assert 'name="display_name"' not in response.text
    assert 'class="copy-row"' not in response.text
    assert 'class="mono id-block"' in response.text


def test_observatory_non_admin_returns_403(authing_portal_client):
    response = authing_portal_client.get("/ui/observatory/", follow_redirects=False)
    assert response.status_code == 403
    assert "403" in response.text
    assert "返回我的主页" in response.text
    assert "/ui/me/" in response.text


def test_observatory_stats_json_non_admin_403(authing_portal_client):
    response = authing_portal_client.get("/ui/observatory/stats.json")
    assert response.status_code == 403


def test_observatory_admin_can_access(authing_admin_client):
    response = authing_admin_client.get("/ui/observatory/")
    assert response.status_code == 200
    assert "Organizations" in response.text


def test_anonymous_public_library_stats(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    lib_id = settings.default_library_id
    response = isolated_client.get(f"/ui/libraries/{lib_id}/")
    assert response.status_code == 200
    assert "分布" in response.text
    assert "登录" in response.text
    assert "layout-settings" not in response.text
    assert "Observatory" not in response.text


def test_private_library_requires_login(isolated_client, monkeypatch, portal_user):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    ensure_user_principal(
        type(
            "U",
            (),
            {
                "sub": portal_user.sub,
                "display_name": portal_user.display_name,
                "email": None,
                "phone": None,
                "username": None,
                "photo": None,
                "is_admin": False,
            },
        )()
    )
    ensure_personal_library(portal_user.principal_id, portal_user.display_name)
    personal = db.find_personal_library(portal_user.principal_id)
    assert personal is not None
    response = isolated_client.get(
        f"/ui/libraries/{personal['library_id']}/",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login")


def test_libraries_list_requires_login_when_anonymous(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    response = isolated_client.get("/ui/libraries/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login")


def test_observatory_record_redirects_to_portal(isolated_client):
    response = isolated_client.get(
        "/ui/observatory/records/vk_test123",
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "/ui/records/vk_test123/"


def test_record_detail_requires_login(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    response = isolated_client.get("/ui/records/vk_nope/", follow_redirects=False)
    assert response.status_code == 302


def test_record_detail_active_community_record(authing_portal_client, portal_user, monkeypatch):
    import app.api.routes_keys as routes_keys

    _patch_session(monkeypatch, portal_user)
    monkeypatch.setattr(routes_keys, "resolve_session_user", lambda _req: portal_user)
    client = authing_portal_client
    created = client.post("/api/keys", json={"label": "portal-read"}, headers=_ORIGIN)
    assert created.status_code == 200
    body = created.json()
    mcp = McpClient(client, api_key=body["plaintext_key"])
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "portal record read test",
            "outcome": "resolved",
            "result_summary": "read via portal UI",
            "evidence": _EVIDENCE,
        },
    )
    record_id = report["record_id"]
    page = client.get(f"/ui/records/{record_id}/")
    assert page.status_code == 200
    assert "portal record read test" in page.text
    assert "我的主页" in page.text


def test_validate_authing_admin_config_refuses_empty_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "auth_admin_users", [])
    with pytest.raises(RuntimeError, match="MA3_AUTH_ADMIN_USERS"):
        validate_authing_admin_config()


def test_validate_authing_admin_config_ok_with_admin(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "test-app")
    monkeypatch.setattr(settings, "authing_app_secret", "test-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ["someone"])
    validate_authing_admin_config()


def test_auth_login_default_next_is_me(authing_portal_client):
    with patch(
        "app.api.routes_auth.authing_client.build_authorize_url",
        return_value="https://id.example/authorize",
    ):
        response = authing_portal_client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302

