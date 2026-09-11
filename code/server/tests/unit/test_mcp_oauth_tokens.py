"""Unit tests for MCP OAuth tokens and entitlement projection (ADR-016)."""
from __future__ import annotations

from unittest.mock import patch

from app.auth.authing_client import AuthingUser
from app.core.config import settings
from app.core.security import RawCredential, resolve_from_credential, resolve_mcp_auth
from app.services import mcp_oauth_token_service
from app.services.entitlement_service import mcp_grants_for_principal
from app.services.onboarding_service import ensure_personal_library
from app.storage import db
from app.storage.db import initialize_database


def test_mcp_oauth_token_projects_entitlements(monkeypatch):
    initialize_database()
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    monkeypatch.setattr(settings, "dev_auth", False)

    db.upsert_user_principal(sso_user="oauth-proj", display_name="OAuth Proj")
    principal_id = "user:oauth-proj"
    ensure_personal_library(principal_id, "OAuth Proj")

    issued = mcp_oauth_token_service.issue_access_token(
        principal_id=principal_id,
        resource=settings.mcp_resource_url(),
        client_id="test-client",
        scope="mcp",
    )
    principal = resolve_from_credential(RawCredential(value=issued.access_token, source="bearer"))
    assert principal.via == "mcp_oauth_token"
    assert principal.principal_id == principal_id
    assert principal.grant_readable is not None
    assert settings.default_library_id in principal.grant_readable
    assert principal.grant_writable is not None
    assert settings.default_library_id in principal.grant_writable
    personal = db.find_personal_library(principal_id)
    assert personal is not None
    assert str(personal["library_id"]) in principal.grant_writable

    auth = resolve_mcp_auth(RawCredential(value=issued.access_token, source="bearer"))
    assert settings.default_library_id in auth.writable_library_ids
    assert auth.api_key_id == principal_id


def test_bare_authing_bearer_no_longer_grants_mcp(monkeypatch):
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


def test_mcp_grants_helper_includes_owned_personal(monkeypatch):
    initialize_database()
    db.upsert_user_principal(sso_user="grant-helper", display_name="Grant Helper")
    principal_id = "user:grant-helper"
    ensure_personal_library(principal_id, "Grant Helper")
    readable, writable, maintainer = mcp_grants_for_principal(principal_id)
    personal = db.find_personal_library(principal_id)
    assert personal is not None
    lid = str(personal["library_id"])
    assert lid in readable
    assert lid in writable
    assert lid in maintainer
    assert settings.default_library_id in writable
