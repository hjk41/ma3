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
    assert 'agent-onboarding.md">Agent onboarding 文档</a>' in text
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
    response = isolated_client.get("/ui/home/")
    assert response.status_code == 200
    assert "/ui/me/" in response.text
    assert "landing.dev_alert" not in response.text
