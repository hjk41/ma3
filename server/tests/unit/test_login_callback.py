from app.api.routes_auth import _safe_next
from app.core.auth import VerifyResult, _cookie_domain_for_host
from app.core import config


def test_cookie_domain_for_host():
    assert _cookie_domain_for_host("ma3.zhilicon.com") == ".zhilicon.com"
    assert _cookie_domain_for_host("auth.zhilicon.com") == ".zhilicon.com"
    assert _cookie_domain_for_host("localhost:18196") is None
    assert _cookie_domain_for_host("127.0.0.1") is None


def test_safe_next_rejects_absolute_urls():
    assert _safe_next("ma3.zhilicon.com", "/ui/me") == "/ui/me"
    assert _safe_next("ma3.zhilicon.com", "http://evil/") == "/ui/"
    assert _safe_next("ma3.zhilicon.com", "//evil") == "/ui/"


def _req(url="https://ma3.zhilicon.com/auth/callback"):
    from types import SimpleNamespace
    from starlette.datastructures import URL
    return SimpleNamespace(url=URL(url))


def test_auth_callback_sets_cookie_and_redirects(monkeypatch):
    from app.api.routes_auth import auth_callback
    monkeypatch.setattr("app.api.routes_auth.verify_sso_cookie", lambda token: VerifyResult("alice", "Alice"))
    import asyncio
    resp = asyncio.run(auth_callback(_req(), gateway_token="fake", return_to="/ui/me"))
    assert resp.status_code == 302
    assert resp.headers["location"] == "/ui/me"
    assert "gateway_token=fake" in resp.headers["set-cookie"]
    assert "Domain=.zhilicon.com" in resp.headers["set-cookie"]


def test_auth_callback_invalid_token_redirects_to_login(monkeypatch):
    from app.api.routes_auth import auth_callback
    monkeypatch.setattr("app.api.routes_auth.verify_sso_cookie", lambda token: None)
    import asyncio
    resp = asyncio.run(auth_callback(_req(), gateway_token="fake"))
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/login"


def test_auth_login_without_verify_url_is_503():
    from app.api.routes_auth import auth_login
    object.__setattr__(config.settings, "auth_verify_url", None)
    import asyncio
    resp = asyncio.run(auth_login(_req("https://ma3.zhilicon.com/auth/login")))
    assert resp.status_code == 503
