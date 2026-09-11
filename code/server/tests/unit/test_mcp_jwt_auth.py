"""Bare Authing Bearer is no longer an MCP data credential (ADR-016)."""
from __future__ import annotations

from unittest.mock import patch

from app.auth.authing_client import AuthingUser
from app.core.config import settings
from app.core.security import RawCredential, resolve_from_credential


def test_bearer_authing_no_longer_maps_to_writer(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn/oidc")
    monkeypatch.setattr(settings, "authing_app_id", "app")
    monkeypatch.setattr(settings, "authing_app_secret", "secret")
    monkeypatch.setattr(settings, "dev_auth", False)
    fake_user = AuthingUser(sub="agent_42", display_name="Agent User", is_admin=False)
    with patch("app.auth.authing_client.resolve_user", return_value=fake_user):
        with patch(
            "app.services.principal_service.ensure_user_principal",
            return_value={"principal_id": "user:agent_42"},
        ):
            principal = resolve_from_credential(RawCredential(value="jwt-token-value", source="bearer"))
    assert principal.via == "invalid_credentials"


def test_invalid_bearer_not_anonymous(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", True)
    monkeypatch.setattr(settings, "authing_issuer", "https://example.authing.cn/oidc")
    monkeypatch.setattr(settings, "authing_app_id", "app")
    monkeypatch.setattr(settings, "authing_app_secret", "secret")
    monkeypatch.setattr(settings, "dev_auth", False)
    with patch("app.auth.authing_client.resolve_user", side_effect=Exception("401")):
        principal = resolve_from_credential(RawCredential(value="bad-jwt", source="bearer"))
    assert principal.via == "invalid_credentials"
