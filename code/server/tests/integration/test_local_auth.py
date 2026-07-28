"""Local username/password auth for self-host (no OIDC) — HTTP / portal coverage."""
from __future__ import annotations

from app.core.config import settings
from app.services import local_auth_service
from app.storage import db
from tests.helpers.mcp_client import McpClient

_ORIGIN = {"Origin": "http://testserver"}


def _enable_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    monkeypatch.setattr(settings, "authing_app_id", "")
    monkeypatch.setattr(settings, "authing_app_secret", "")
    monkeypatch.setattr(settings, "local_auth", True)
    monkeypatch.setattr(settings, "local_auth_open_registration", True)
    monkeypatch.setattr(settings, "api_key_encryption_secret", "test-local-auth-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ())


def _register_via_http(client, *, username: str, password: str = "password123", display_name: str = "") -> str:
    r = client.post(
        "/auth/register",
        data={
            "username": username,
            "password": password,
            "password_confirm": password,
            "display_name": display_name,
            "next": "/ui/me/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]
    assert settings.auth_session_cookie in r.cookies
    token = r.cookies[settings.auth_session_cookie]
    client.cookies.set(settings.auth_session_cookie, token)
    return token


def _login_via_http(client, *, username: str, password: str = "password123") -> str:
    r = client.post(
        "/auth/login",
        data={"username": username, "password": password, "next": "/ui/me/"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]
    token = r.cookies[settings.auth_session_cookie]
    client.cookies.set(settings.auth_session_cookie, token)
    return token


def test_register_first_user_is_admin(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    assert settings.local_auth_enabled
    account = local_auth_service.register_local_user(
        username="Admin1", password="password123", display_name="Admin One"
    )
    assert account["is_admin"] is True
    assert account["username"] == "admin1"
    assert db.get_local_account("admin1") is not None


def test_register_login_session_and_me(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register_via_http(isolated_client, username="alice", display_name="Alice")
    me = isolated_client.get("/ui/me/")
    assert me.status_code == 200
    assert "Alice" in me.text
    keys = isolated_client.get("/ui/keys/")
    assert keys.status_code == 200


def test_login_get_and_post_forms(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="formuser", password="password123")
    page = isolated_client.get("/auth/login")
    assert page.status_code == 200
    assert 'name="username"' in page.text
    assert 'name="password"' in page.text
    reg = isolated_client.get("/auth/register")
    assert reg.status_code == 200
    assert 'name="display_name"' in reg.text
    _login_via_http(isolated_client, username="formuser")
    assert isolated_client.get("/ui/me/").status_code == 200


def test_login_wrong_password(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="bob", password="password123")
    r = isolated_client.post(
        "/auth/login",
        data={"username": "bob", "password": "wrongpass1", "next": "/ui/me/"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "invalid" in r.text.lower() or "密码" in r.text or "username" in r.text.lower()


def test_second_user_not_admin_by_default(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="first", password="password123")
    second = local_auth_service.register_local_user(username="second", password="password123")
    assert second["is_admin"] is False


def test_healthz_feature_flag_local_auth(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    body = isolated_client.get("/healthz").json()
    assert "local_auth" in body["features"]
    assert "oidc" not in body["features"]


def test_local_auth_off_keeps_bootstrap_503(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    monkeypatch.setattr(settings, "authing_app_id", "")
    monkeypatch.setattr(settings, "authing_app_secret", "")
    monkeypatch.setattr(settings, "local_auth", False)
    monkeypatch.setattr(settings, "bootstrap_selfhost", True)
    r = isolated_client.get("/ui/me/", follow_redirects=False)
    assert r.status_code == 503


def test_duplicate_username_http(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register_via_http(isolated_client, username="unique1")
    isolated_client.cookies.clear()
    r = isolated_client.post(
        "/auth/register",
        data={
            "username": "Unique1",
            "password": "password123",
            "password_confirm": "password123",
            "next": "/ui/me/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "taken" in r.text.lower() or "已" in r.text


def test_short_password_rejected(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    r = isolated_client.post(
        "/auth/register",
        data={
            "username": "shortpw",
            "password": "1234567",
            "password_confirm": "1234567",
            "next": "/ui/me/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "8" in r.text or "password" in r.text.lower() or "密码" in r.text


def test_invalid_username_rejected(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    r = isolated_client.post(
        "/auth/register",
        data={
            "username": "bad user!",
            "password": "password123",
            "password_confirm": "password123",
            "next": "/ui/me/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "username" in r.text.lower() or "用户名" in r.text


def test_password_mismatch_rejected(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    r = isolated_client.post(
        "/auth/register",
        data={
            "username": "mismatch1",
            "password": "password123",
            "password_confirm": "password124",
            "next": "/ui/setup/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "不一致" in r.text or "match" in r.text.lower()
    assert db.count_local_accounts() == 0


def test_setup_page_has_password_toggle_and_confirm(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    page = isolated_client.get("/ui/setup/")
    assert page.status_code == 200
    assert 'name="password_confirm"' in page.text
    assert "password-toggle" in page.text
    assert "ma3TogglePassword" in page.text


def test_closed_registration_http(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    monkeypatch.setattr(settings, "local_auth_open_registration", False)
    _register_via_http(isolated_client, username="gatekeeper")
    isolated_client.cookies.clear()
    r = isolated_client.post(
        "/auth/register",
        data={
            "username": "latecomer",
            "password": "password123",
            "password_confirm": "password123",
            "next": "/ui/me/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "closed" in r.text.lower() or "关闭" in r.text or "admin" in r.text.lower()


def test_logout_clears_session(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register_via_http(isolated_client, username="logoutme")
    assert isolated_client.get("/ui/me/").status_code == 200
    out = isolated_client.get("/auth/logout", follow_redirects=False)
    assert out.status_code == 302
    assert out.headers["location"] == "/ui/home/"
    # Cookie cleared — subsequent me requires login
    isolated_client.cookies.clear()
    me = isolated_client.get("/ui/me/", follow_redirects=False)
    assert me.status_code == 302
    assert "/auth/login" in me.headers["location"]


def test_whoami_json(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register_via_http(isolated_client, username="whoami", display_name="Who Am I")
    who = isolated_client.get("/auth/whoami")
    assert who.status_code == 200
    body = who.json()
    assert body["via"] == "local"
    assert body["is_admin"] is True
    assert body["display_name"] == "Who Am I"
    assert body["principal_id"].startswith("user:")


def test_unauthenticated_me_redirects_to_login(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    # With zero accounts, all pages go to setup first.
    r0 = isolated_client.get("/ui/me/", follow_redirects=False)
    assert r0.status_code == 302
    assert r0.headers["location"].endswith("/ui/setup/")
    local_auth_service.register_local_user(username="gateuser", password="password123")
    r = isolated_client.get("/ui/me/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


def test_mint_api_key_and_mcp(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register_via_http(isolated_client, username="keyuser", display_name="Key User")
    created = isolated_client.post("/api/keys", json={"label": "agent"}, headers=_ORIGIN)
    assert created.status_code == 200, created.text
    plaintext = created.json()["plaintext_key"]
    assert plaintext.startswith("ma3k_")
    mcp = McpClient(isolated_client, api_key=plaintext)
    who = mcp.structured("ma3_whoami")
    assert who["caller"]["type"] == "api_key"
    assert settings.default_library_id in who["readable_library_ids"]


def test_observatory_local_users_admin_flow(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register_via_http(isolated_client, username="opsadmin", display_name="Ops Admin")
    local_auth_service.register_local_user(username="member", password="password123")

    page = isolated_client.get("/ui/observatory/local-users/")
    assert page.status_code == 200
    assert "opsadmin" in page.text
    assert "member" in page.text

    promote = isolated_client.post(
        "/ui/observatory/local-users/admin",
        data={"username": "member", "is_admin": "1"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert promote.status_code == 303
    assert "/ui/observatory/local-users/" in promote.headers["location"]
    row = db.get_local_account("member")
    assert row is not None
    assert bool(int(row["is_admin"])) is True

    demote = isolated_client.post(
        "/ui/observatory/local-users/admin",
        data={"username": "member", "is_admin": "0"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert demote.status_code == 303
    assert bool(int(db.get_local_account("member")["is_admin"])) is False


def test_observatory_requires_admin_when_local_auth(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="adminx", password="password123")
    _register_via_http(isolated_client, username="pleb", display_name="Pleb")
    # second user is not admin
    denied = isolated_client.get("/ui/observatory/local-users/", follow_redirects=False)
    assert denied.status_code == 403


def test_oidc_disables_local_auth_routes(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn")
    monkeypatch.setattr(settings, "authing_app_id", "app")
    monkeypatch.setattr(settings, "authing_app_secret", "secret")
    monkeypatch.setattr(settings, "local_auth", True)
    assert settings.local_auth_enabled is False
    assert settings.portal_auth_enabled is True
    # Local register should bounce to OIDC login start path (redirect to IdP or login)
    r = isolated_client.get("/auth/register", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/auth/login" in r.headers.get("location", "")


def test_landing_shows_local_auth_cta(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    # Day-0: marketing landing stays visible; primary CTA points at setup.
    home = isolated_client.get("/ui/home/", follow_redirects=False)
    assert home.status_code == 200
    assert "/ui/setup/" in home.text
    setup = isolated_client.get("/ui/setup/")
    assert setup.status_code == 200
    assert "创建管理员" in setup.text or "admin" in setup.text.lower()
    assert 'name="password_confirm"' in setup.text
