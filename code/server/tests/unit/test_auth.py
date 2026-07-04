from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def authing_client(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn/oidc")
    monkeypatch.setattr(settings, "authing_app_id", "test_app_id")
    monkeypatch.setattr(settings, "authing_app_secret", "test_secret")
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    return TestClient(app, raise_server_exceptions=True)


def test_auth_login_redirects_to_authing(authing_client: TestClient):
    with patch("app.api.routes_auth.authing_client.build_authorize_url", return_value="https://id.example/authorize"):
        response = authing_client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://id.example/authorize"
    assert settings.auth_oauth_state_cookie in response.cookies


def test_auth_login_start_redirects_when_configured(authing_client: TestClient):
    with patch("app.api.routes_auth.authing_client.build_authorize_url", return_value="https://id.example/authorize"):
        response = authing_client.get("/auth/login/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://id.example/authorize"
    assert settings.auth_oauth_state_cookie in response.cookies


def test_auth_login_503_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    client = TestClient(app, raise_server_exceptions=True)
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 503


def test_auth_callback_sets_session_and_principal(authing_client: TestClient):
    authing_client.cookies.set(settings.auth_oauth_state_cookie, "state123")
    authing_client.cookies.set("ma3_oauth_next", "/ui/observatory/")

    fake_user = type(
        "U",
        (),
        {
            "sub": "authing_test_user",
            "display_name": "测试用户",
            "email": "test@example.com",
            "phone": "13800138000",
            "username": None,
            "photo": None,
            "is_admin": False,
        },
    )()

    with (
        patch("app.api.routes_auth.validate_oauth_state", return_value=True),
        patch("app.api.routes_auth.authing_client.exchange_code", return_value={"access_token": "atk_test"}),
        patch("app.api.routes_auth.authing_client.resolve_user", return_value=fake_user),
    ):
        response = authing_client.get("/auth/callback?code=abc&state=state123", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/ui/observatory/"
    assert settings.auth_session_cookie in response.cookies

    authing_client.cookies.set(settings.auth_session_cookie, "atk_test")
    with patch("app.auth.authing_client.resolve_user", return_value=fake_user):
        whoami = authing_client.get("/auth/whoami")
    assert whoami.status_code == 200
    body = whoami.json()
    assert body["sub"] == "authing_test_user"
    assert body["display_name"] == "测试用户"


def test_observatory_requires_login_when_authing_enabled(authing_client: TestClient):
    response = authing_client.get("/ui/observatory/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login")


def test_observatory_logged_in_non_admin_returns_403(authing_client: TestClient):
    from app.auth.session import SessionUser

    import app.api.ui_session as ui_session

    session = SessionUser(
        principal_id="user:regular_user",
        sub="regular_user",
        display_name="普通用户",
        email=None,
        phone=None,
        is_admin=False,
    )
    with (
        patch("app.auth.session.resolve_session_user", return_value=session),
        patch.object(ui_session, "resolve_session_user", return_value=session),
    ):
        response = authing_client.get("/ui/observatory/", follow_redirects=False)
    assert response.status_code == 403
    assert "返回我的主页" in response.text


def test_auth_logout_clears_session_and_redirects_to_authing_logout(authing_client: TestClient):
    authing_client.cookies.set(settings.auth_session_cookie, "atk_test")
    with patch(
        "app.api.routes_auth.authing_client.build_logout_url",
        return_value="https://ma3.authing.cn/oidc/session/end?client_id=test",
    ) as mock_logout:
        response = authing_client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://ma3.authing.cn/oidc/session/end?client_id=test"
    mock_logout.assert_called_once_with(
        post_logout_redirect=settings.resolve_authing_post_logout_redirect_uri(),
    )
    assert response.cookies.get(settings.auth_session_cookie) in ("", None)
    whoami = authing_client.get("/auth/whoami")
    assert whoami.status_code == 401


def test_upsert_user_principal_sqlite():
    from app.storage.db import initialize_database, upsert_user_principal

    initialize_database()
    row = upsert_user_principal(
        sso_user="authing_test_user",
        display_name="测试用户",
        metadata={"provider": "authing"},
    )
    assert row["principal_id"] == "user:authing_test_user"
