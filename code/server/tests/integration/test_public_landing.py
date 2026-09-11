from __future__ import annotations

from app.core.config import settings
from tests.integration.test_user_portal import _enable_authing, _patch_session


def test_root_redirects_to_home_when_anonymous(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    for path in ("/", "/ui", "/ui/"):
        response = isolated_client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/ui/home/"


def test_root_redirects_to_me_when_logged_in(authing_portal_client):
    for path in ("/", "/ui", "/ui/"):
        response = authing_portal_client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/ui/me/"


def test_home_renders_landing_without_login(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    response = isolated_client.get("/ui/home/")
    assert response.status_code == 200
    text = response.text
    assert "landing-hero" in text
    assert "/auth/login?next=" in text
    assert f"/ui/libraries/{settings.default_library_id}/" in text
    assert "/client/agent-onboarding.md" in text
    assert "/client/connect.md" in text
    assert "https://ma3-talk.slack.com" in text
    assert "paste-to-agent" in text.lower() or "贴给你的 agent" in text or "把下面内容贴给" in text
    assert "stat-card" in text


def test_home_redirects_to_me_when_logged_in(authing_portal_client):
    response = authing_portal_client.get("/ui/home/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/ui/me/"


def test_home_english_locale(isolated_client, monkeypatch):
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, None)
    response = isolated_client.get("/ui/home/?lang=en-US")
    assert response.status_code == 200
    assert "MA3: Stand on prior agents" in response.text
    assert "Sign in / Register" in response.text


def test_home_dev_mode_cta(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", None)
    monkeypatch.setattr(settings, "bootstrap_selfhost", False)
    response = isolated_client.get("/ui/home/")
    assert response.status_code == 200
    assert "/client/agent-onboarding.md" in response.text
    assert "进入门户" not in response.text


def test_home_bootstrap_mode_cta(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", None)
    monkeypatch.setattr(settings, "local_auth", False)
    monkeypatch.setattr(settings, "bootstrap_selfhost", True)
    response = isolated_client.get("/ui/home/")
    assert response.status_code == 200
    assert "/mcp/info" in response.text
    assert "bootstrap" in response.text.lower() or "API Key" in response.text


def test_home_local_auth_mode_cta(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", None)
    monkeypatch.setattr(settings, "local_auth", True)
    monkeypatch.setattr(settings, "bootstrap_selfhost", True)
    response = isolated_client.get("/ui/home/")
    assert response.status_code == 200
    # Day-0 (no owner): primary CTA points at setup; after owner exists, login.
    assert "/ui/setup/" in response.text or "/auth/login" in response.text
    assert (
        "local" in response.text.lower()
        or "本地" in response.text
        or "注册" in response.text
        or "管理员" in response.text
    )


def test_me_without_oidc_returns_html_explain(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", None)
    monkeypatch.setattr(settings, "local_auth", False)
    monkeypatch.setattr(settings, "bootstrap_selfhost", True)
    response = isolated_client.get("/ui/me/")
    assert response.status_code == 503
    assert "text/html" in response.headers.get("content-type", "")
    assert "bootstrap" in response.text.lower() or "OIDC" in response.text
    assert "this page requires Authing login" not in response.text


def test_auth_login_without_oidc_returns_html_explain(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", None)
    monkeypatch.setattr(settings, "local_auth", False)
    monkeypatch.setattr(settings, "bootstrap_selfhost", True)
    for path in ("/auth/login", "/auth/login/start"):
        response = isolated_client.get(
            path,
            params={"next": "http://192.168.1.100:8010/ui/me/"},
        )
        assert response.status_code == 503, path
        assert "text/html" in response.headers.get("content-type", ""), path
        assert "bootstrap" in response.text.lower() or "OIDC" in response.text, path
        assert "Authing auth is not configured" not in response.text, path
        assert "/mcp/info" in response.text or "/client/agent-onboarding.md" in response.text, path
