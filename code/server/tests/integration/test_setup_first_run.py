"""Self-host first-run setup wizard and DB registration override."""
from __future__ import annotations

from app.core.config import settings
from app.services import local_auth_service, setup_service
from app.storage import db

_ORIGIN = {"Origin": "http://testserver"}


def _enable_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    monkeypatch.setattr(settings, "authing_app_id", "")
    monkeypatch.setattr(settings, "authing_app_secret", "")
    monkeypatch.setattr(settings, "local_auth", True)
    monkeypatch.setattr(settings, "local_auth_open_registration", True)
    monkeypatch.setattr(settings, "api_key_encryption_secret", "test-setup-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ())


def _register(client, *, username: str, password: str = "password123", next_path: str = "/ui/setup/") -> None:
    r = client.post(
        "/auth/register",
        data={
            "username": username,
            "password": password,
            "password_confirm": password,
            "display_name": username,
            "next": next_path,
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text[:500]
    token = r.cookies[settings.auth_session_cookie]
    client.cookies.set(settings.auth_session_cookie, token)


def _mint_key(client) -> None:
    created = client.post("/api/keys", json={"label": "setup-key"}, headers=_ORIGIN)
    assert created.status_code == 200, created.text


def test_zero_accounts_home_redirects_to_setup(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    assert setup_service.setup_needs_owner()
    # Public landing stays reachable; other entry URLs still funnel to setup.
    home = isolated_client.get("/ui/home/", follow_redirects=False)
    assert home.status_code == 200
    assert "/ui/setup/" in home.text
    for path in ("/", "/ui/", "/ui/setup/"):
        r = isolated_client.get(path, follow_redirects=False)
        if path == "/ui/setup/":
            assert r.status_code == 200
            assert "管理员" in r.text or "admin" in r.text.lower()
        else:
            assert r.status_code == 302, path
            assert "/ui/setup/" in r.headers["location"] or r.headers["location"].endswith("/ui/setup/")


def test_zero_accounts_all_pages_redirect_to_setup(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    assert setup_service.setup_needs_owner()
    # Login/register pages stay reachable so the first admin can be created.
    login = isolated_client.get("/auth/login", follow_redirects=False)
    assert login.status_code == 200
    for path in (
        "/ui/me/",
        "/ui/keys/",
        "/ui/libraries/",
        "/ui/observatory/",
        "/ui/orgs/",
    ):
        r = isolated_client.get(path, follow_redirects=False)
        assert r.status_code == 302, path
        assert r.headers["location"].endswith("/ui/setup/"), path
    # Agent / API rails stay open
    assert isolated_client.get("/mcp/info").status_code == 200
    assert isolated_client.get("/healthz").status_code == 200


def test_first_register_enters_checklist(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register(isolated_client, username="owner1")
    assert setup_service.setup_state() == "guided_ramp"
    page = isolated_client.get("/ui/setup/")
    assert page.status_code == 200
    assert "API Key" in page.text or "签发" in page.text
    assert setup_service.setup_complete() is False


def test_db_registration_toggle_blocks_second_user(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    monkeypatch.setattr(settings, "local_auth_open_registration", True)
    _register(isolated_client, username="owner2")
    assert local_auth_service.is_registration_open() is True

    close = isolated_client.post(
        "/ui/setup/registration",
        data={"open": "0"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert close.status_code == 303
    assert local_auth_service.is_registration_open() is False
    assert db.get_instance_setting("local_registration_open") == "false"

    isolated_client.cookies.clear()
    blocked = isolated_client.post(
        "/auth/register",
        data={
            "username": "second",
            "password": "password123",
            "password_confirm": "password123",
            "next": "/ui/me/",
        },
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert blocked.status_code == 200
    assert "closed" in blocked.text.lower() or "关闭" in blocked.text or "admin" in blocked.text.lower()

    # Re-open via service (same as Observatory / setup)
    setup_service.set_registration_open(True)
    assert local_auth_service.is_registration_open() is True
    ok = local_auth_service.register_local_user(username="second", password="password123")
    assert ok["is_admin"] is False


def test_setup_complete_after_key_and_finish(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register(isolated_client, username="owner3")
    assert setup_service.setup_in_progress()

    _mint_key(isolated_client)
    assert setup_service.admin_has_non_bootstrap_api_key()
    assert setup_service.setup_complete() is False

    ack = isolated_client.post(
        "/ui/setup/registration-ack",
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert ack.status_code == 303
    assert ack.headers["location"].endswith("/ui/setup/?ok=kept%20registration%20open") or "ui/setup" in ack.headers["location"]
    # Closing/ack alone must NOT leave the wizard — Finish is required.
    assert setup_service.checklist_ready_to_finish() is True
    assert setup_service.setup_complete() is False
    assert setup_service.setup_state() == "guided_ramp"
    setup_page = isolated_client.get("/ui/setup/", follow_redirects=False)
    assert setup_page.status_code == 200
    assert "完成引导" in setup_page.text or "Finish" in setup_page.text
    assert "logout" in setup_page.text.lower() or "退出" in setup_page.text

    finish = isolated_client.post(
        "/ui/setup/complete",
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert finish.status_code == 303
    assert setup_service.setup_complete() is True
    assert setup_service.setup_state() == "steady"

    setup = isolated_client.get("/ui/setup/", follow_redirects=False)
    assert setup.status_code == 302
    assert setup.headers["location"].endswith("/ui/home/")


def test_finish_setup_button_sets_flag(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register(isolated_client, username="owner4")
    _mint_key(isolated_client)
    assert setup_service.setup_in_progress()

    close = isolated_client.post(
        "/ui/setup/registration",
        data={"open": "0"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert close.status_code == 303
    assert "ui/setup" in close.headers["location"]
    assert setup_service.setup_complete() is False
    assert setup_service.checklist_ready_to_finish() is True

    finish = isolated_client.post(
        "/ui/setup/complete",
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert finish.status_code == 303
    assert finish.headers["location"].endswith("/ui/home/")
    assert db.get_instance_setting("setup_complete") == "1"


def test_me_shows_setup_banner_while_in_progress(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register(isolated_client, username="owner5", next_path="/ui/me/")
    me = isolated_client.get("/ui/me/")
    assert me.status_code == 200
    assert "/ui/setup/" in me.text


def test_observatory_registration_toggle(isolated_client, monkeypatch):
    _enable_local(monkeypatch)
    _register(isolated_client, username="opsowner")
    page = isolated_client.get("/ui/observatory/local-users/")
    assert page.status_code == 200
    assert "开放注册" in page.text

    r = isolated_client.post(
        "/ui/observatory/local-users/registration",
        data={"open": "0"},
        headers=_ORIGIN,
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert local_auth_service.is_registration_open() is False
