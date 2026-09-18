"""Integration: MCP OAuth AS discovery + PKCE token exchange (ADR-016)."""
from __future__ import annotations

import base64
import hashlib
import secrets

from app.core.config import settings
from app.services import mcp_oauth_as_service
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import complete_display_name_setup
from app.storage import db
from tests.helpers.mcp_client import McpClient
from tests.integration.conftest import _enable_authing, _patch_session


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def test_prm_and_as_metadata(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    prm = isolated_client.get("/.well-known/oauth-protected-resource")
    assert prm.status_code == 200
    body = prm.json()
    assert body["resource"] == "http://testserver/mcp"
    assert body["authorization_servers"] == ["http://testserver"]
    assert "header" in body["bearer_methods_supported"]

    prm_mcp = isolated_client.get("/.well-known/oauth-protected-resource/mcp")
    assert prm_mcp.status_code == 200
    assert prm_mcp.json()["resource"] == body["resource"]

    as_meta = isolated_client.get("/.well-known/oauth-authorization-server")
    assert as_meta.status_code == 200
    meta = as_meta.json()
    assert meta["authorization_response_iss_parameter_supported"] is True
    assert meta["authorization_endpoint"].endswith("/oauth/authorize")
    assert meta["token_endpoint"].endswith("/oauth/token")
    assert "S256" in meta["code_challenge_methods_supported"]
    assert meta["client_id_metadata_document_supported"] is True


def test_pkce_oauth_exchange_and_mcp_whoami(isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_library(portal_user.principal_id, portal_user.display_name)

    verifier, challenge = _pkce_pair()
    redirect_uri = "https://chatgpt.com/connector_platform_oauth_redirect"
    client_id = "https://chatgpt.com/oauth/client.json"
    monkeypatch.setattr(
        mcp_oauth_as_service,
        "fetch_client_metadata",
        lambda value: {
            "client_id": value,
            "redirect_uris": [redirect_uri],
            "token_endpoint_auth_methods_supported": ["none"],
        },
    )
    resource = settings.mcp_resource_url()

    auth = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,
            "scope": "mcp",
            "state": "xyz",
        },
        follow_redirects=False,
    )
    assert auth.status_code == 302
    location = auth.headers["location"]
    assert location.startswith(redirect_uri)
    assert "code=" in location
    assert "state=xyz" in location
    assert "iss=http%3A%2F%2Ftestserver" in location
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(location).query)["code"][0]

    token = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": resource,
        },
    )
    assert token.status_code == 200, token.text
    payload = token.json()
    assert payload["token_type"] == "Bearer"
    assert payload["access_token"].startswith("ma3mcp_")
    assert payload["resource"] == resource

    mcp = McpClient(isolated_client)
    who = mcp.structured("ma3_whoami", bearer=payload["access_token"])
    assert who["caller"]["via"] == "mcp_oauth_token"
    assert who["caller"]["principal_id"] == portal_user.principal_id
    assert settings.default_library_id in who["writable_library_ids"]

    ctx = mcp.structured(
        "ma3_context",
        {"problem": "oauth entitlement projection smoke", "max_cases": 1},
        bearer=payload["access_token"],
    )
    assert "cases" in ctx or "ungrouped_records" in ctx

    # Key path still works (regression).
    from app.services.api_key_service import hash_key

    key = f"ma3v4_{secrets.token_hex(12)}"
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(5)}",
        key_hash=hash_key(key),
        principal_id=portal_user.principal_id,
        label="oauth-regression",
        grants=[
            {"library_id": settings.default_library_id, "role": "writer"},
        ],
    )
    key_who = mcp.structured("ma3_whoami", api_key=key)
    assert key_who["caller"]["via"] == "db_api_key"


def test_mcp_401_includes_www_authenticate(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    mcp = McpClient(isolated_client)
    raw = mcp.post_raw(
        "tools/call",
        {"name": "ma3_context", "arguments": {"problem": "need auth"}},
    )
    assert raw["status_code"] == 401
    www = raw["headers"].get("www-authenticate") or raw["headers"].get("WWW-Authenticate")
    assert www is not None
    assert "resource_metadata=" in www
    assert "/.well-known/oauth-protected-resource" in www
    assert raw["body"]["error"]["code"] == -32001


def test_authorize_redirects_to_login_when_anonymous(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    _enable_authing(monkeypatch)
    verifier, challenge = _pkce_pair()
    response = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "cursor-local",
            "redirect_uri": "http://127.0.0.1:9999/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": settings.mcp_resource_url(),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/auth/login?next=")


def test_chatgpt_stable_redirect_is_allowed():
    assert mcp_oauth_as_service.redirect_uri_allowed(
        "https://chatgpt.com/connector_platform_oauth_redirect"
    )


def test_cimd_binds_client_to_declared_redirect(monkeypatch):
    client_id = "https://chatgpt.com/oauth/client.json"
    monkeypatch.setattr(
        mcp_oauth_as_service,
        "fetch_client_metadata",
        lambda value: {
            "client_id": value,
            "redirect_uris": ["https://chatgpt.com/connector_platform_oauth_redirect"],
            "token_endpoint_auth_methods_supported": ["none"],
        },
    )
    assert mcp_oauth_as_service.client_redirect_uri_allowed(
        client_id,
        "https://chatgpt.com/connector_platform_oauth_redirect",
    )
    assert not mcp_oauth_as_service.client_redirect_uri_allowed(
        client_id,
        "https://attacker.example/callback",
    )


def test_cimd_fetch_rejects_non_chatgpt_hosts(monkeypatch):
    called = False

    class UnexpectedClient:
        def __init__(self, **_kwargs):
            nonlocal called
            called = True

    monkeypatch.setattr(mcp_oauth_as_service.httpx, "Client", UnexpectedClient)
    assert mcp_oauth_as_service.fetch_client_metadata("https://127.0.0.1/client.json") is None
    assert called is False


def test_cimd_accepts_loopback_runtime_port(monkeypatch):
    client_id = "https://chatgpt.com/oauth/client.json"
    monkeypatch.setattr(
        mcp_oauth_as_service,
        "fetch_client_metadata",
        lambda _value: {
            "client_id": client_id,
            "redirect_uris": ["http://127.0.0.1/callback/id"],
            "token_endpoint_auth_methods_supported": ["none"],
        },
    )
    assert mcp_oauth_as_service.client_redirect_uri_allowed(
        client_id, "http://127.0.0.1:54321/callback/id"
    )


def test_cimd_rejects_malformed_client_id():
    assert not mcp_oauth_as_service.client_redirect_uri_allowed(
        "https://[invalid", "https://chatgpt.com/connector_platform_oauth_redirect"
    )


def test_cimd_rejects_unsafe_or_mismatched_redirects(monkeypatch):
    client_id = "https://chatgpt.com/oauth/client.json"
    monkeypatch.setattr(
        mcp_oauth_as_service,
        "fetch_client_metadata",
        lambda _value: {
            "client_id": client_id,
            "redirect_uris": [
                "http://remote.example/callback#fragment",
                "http://127.0.0.1/callback;safe",
            ],
            "token_endpoint_auth_methods_supported": ["none"],
        },
    )
    assert not mcp_oauth_as_service.client_redirect_uri_allowed(
        client_id, "http://remote.example/callback#fragment"
    )
    assert not mcp_oauth_as_service.client_redirect_uri_allowed(
        client_id, "http://127.0.0.1:54321/callback;different"
    )
