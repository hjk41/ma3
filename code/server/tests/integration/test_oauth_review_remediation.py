"""Remediation tests for design/28 (OAuth review fixes)."""
from __future__ import annotations

import base64
import hashlib
import secrets

from app.core.config import settings
from app.core.public_url import localhost_aliases, resource_acceptable, resolve_mcp_resource_url
from app.core.security import RawCredential, resolve_from_credential
from app.services import mcp_oauth_as_service, mcp_oauth_token_service
from app.services.api_key_service import hash_key
from app.services.entitlement_service import mcp_grants_for_principal
from app.services.onboarding_service import ensure_personal_library
from app.services.principal_service import complete_display_name_setup
from app.services.redaction_service import redact_text
from app.storage import db
from app.storage.db import initialize_database
from tests.helpers.mcp_client import McpClient
from tests.integration.conftest import _enable_authing, _patch_session


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    # token_urlsafe can exceed 128 chars for large nbytes; clamp to RFC range.
    while not mcp_oauth_as_service.validate_code_verifier(verifier):
        verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def test_localhost_aliases_and_resource_acceptable():
    aliases = localhost_aliases("http://127.0.0.1:8000/mcp")
    assert "http://localhost:8000/mcp" in aliases
    assert resource_acceptable("http://localhost:8000/mcp", request=None)


def test_prm_uses_request_host_when_public_base_unset(isolated_client, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", None)
    prm = isolated_client.get(
        "/.well-known/oauth-protected-resource",
        headers={"Host": "192.168.1.50:8000"},
    )
    assert prm.status_code == 200
    assert prm.json()["resource"] == "http://192.168.1.50:8000/mcp"

    raw = isolated_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ma3_context", "arguments": {"problem": "need auth"}},
        },
        headers={"Host": "192.168.1.50:8000"},
    )
    assert raw.status_code == 401
    www = raw.headers.get("www-authenticate") or raw.headers.get("WWW-Authenticate") or ""
    assert "192.168.1.50:8000" in www


def test_authorize_redirects_to_setup_when_display_name_unlocked(isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    # Do NOT complete display name setup.
    assert db.user_display_name_is_locked(portal_user.principal_id) is False

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
    assert response.headers["location"].startswith("/ui/me/setup/?next=")


def test_oauth_layer1_excludes_api_key_only_library(isolated_client, monkeypatch, portal_user):
    initialize_database()
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    monkeypatch.setattr(settings, "dev_auth", False)
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_library(portal_user.principal_id, portal_user.display_name)

    # Create a private library the user does not own; attach only via API key grant.
    extra_lib = f"lib_extra_{secrets.token_hex(4)}"
    db.create_library(extra_lib, name="Key-only lib", visibility="private", kind="custom")
    key = f"ma3k_{secrets.token_hex(16)}"
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(5)}",
        key_hash=hash_key(key),
        principal_id=portal_user.principal_id,
        label="key-only",
        grants=[{"library_id": extra_lib, "role": "writer"}],
    )

    readable, _, _ = mcp_grants_for_principal(portal_user.principal_id)
    assert extra_lib not in readable

    verifier, challenge = _pkce_pair()
    auth = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "c",
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": settings.mcp_resource_url(),
        },
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]
    token = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "client_id": "c",
            "code_verifier": verifier,
            "resource": settings.mcp_resource_url(),
        },
    ).json()
    mcp = McpClient(isolated_client)
    who = mcp.structured("ma3_whoami", bearer=token["access_token"])
    assert extra_lib not in who.get("readable_library_ids", [])
    key_who = mcp.structured("ma3_whoami", api_key=key)
    assert extra_lib in key_who.get("readable_library_ids", [])


def test_pkce_rejects_short_verifier(isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)

    verifier, challenge = _pkce_pair()
    auth = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "c",
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": settings.mcp_resource_url(),
        },
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]
    bad = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "client_id": "c",
            "code_verifier": "too-short",
            "resource": settings.mcp_resource_url(),
        },
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_grant"


def test_pkce_rejects_invalid_challenge_on_authorize(isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)

    response = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "c",
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "code_challenge": "not-valid!!",
            "code_challenge_method": "S256",
            "resource": settings.mcp_resource_url(),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=invalid_request" in response.headers["location"]


def test_redact_ma3k_and_ma3mcp_prefixes():
    text = "key=ma3k_deadbeef0123456789abcdef and tok=ma3mcp_aabbccddeeff001122334455"
    out = redact_text(text)
    assert "ma3k_" not in out
    assert "ma3mcp_" not in out
    assert "[REDACTED:api_key]" in out
    assert "[REDACTED:token]" in out


def test_db_api_key_wins_over_matching_dev_key(monkeypatch):
    initialize_database()
    plaintext = f"ma3k_collide_{secrets.token_hex(16)}"
    monkeypatch.setattr(settings, "dev_auth", True)
    monkeypatch.setattr(settings, "dev_api_key", plaintext)
    db.upsert_user_principal(sso_user="collide", display_name="Collide")
    principal_id = "user:collide"
    ensure_personal_library(principal_id, "Collide")
    personal = db.find_personal_library(principal_id)
    assert personal is not None
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(5)}",
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label="collide",
        grants=[{"library_id": str(personal["library_id"]), "role": "writer"}],
    )
    principal = resolve_from_credential(RawCredential(value=plaintext, source="api_key_header"))
    assert principal.via == "db_api_key"
    assert principal.is_admin_bypass is False


def test_token_requires_resource_and_rejects_host_mismatch(isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "public_base_url", "http://testserver")
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)

    verifier, challenge = _pkce_pair()
    resource = settings.mcp_resource_url()
    auth = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "c",
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,
        },
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]

    missing = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "client_id": "c",
            "code_verifier": verifier,
        },
    )
    assert missing.status_code == 400
    assert missing.json()["error"] == "invalid_target"

    # Re-issue a fresh code (previous code may still be unused because missing resource failed before consume).
    # Actually missing resource fails before consume — code still valid. Wrong resource should also fail without consuming? 
    # Current code validates before consume — good.
    wrong = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "client_id": "c",
            "code_verifier": verifier,
            "resource": "http://evil.example/mcp",
        },
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "invalid_target"

    ok = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "client_id": "c",
            "code_verifier": verifier,
            "resource": resource,
        },
    )
    assert ok.status_code == 200, ok.text


def test_portal_role_access_ignores_key_grants(monkeypatch):
    from app.services.entitlement_service import list_entitled_libraries

    initialize_database()
    db.upsert_user_principal(sso_user="portal-role", display_name="Portal Role")
    principal_id = "user:portal-role"
    ensure_personal_library(principal_id, "Portal Role")

    lib_id = f"lib_reader_{secrets.token_hex(4)}"
    db.create_library(lib_id, name="Reader Lib", visibility="private", kind="custom")
    db.upsert_library_grant(
        library_id=lib_id,
        principal_id=principal_id,
        role="reader",
        created_by=principal_id,
    )

    key = f"ma3k_{secrets.token_hex(16)}"
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(5)}",
        key_hash=hash_key(key),
        principal_id=principal_id,
        label="writer-key",
        grants=[{"library_id": lib_id, "role": "writer"}],
    )

    rows = {row["library_id"]: row for row in list_entitled_libraries(principal_id)}
    assert lib_id in rows
    assert rows[lib_id]["role"] == "reader"
    assert rows[lib_id]["access"] == "读"
    assert rows[lib_id]["key_prefixes"]  # annotation may be present
    # Key-only private lib must not appear.
    only_key_lib = f"lib_keyonly_{secrets.token_hex(4)}"
    db.create_library(only_key_lib, name="Key Only", visibility="private", kind="custom")
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(5)}",
        key_hash=hash_key(f"ma3k_{secrets.token_hex(16)}"),
        principal_id=principal_id,
        label="only",
        grants=[{"library_id": only_key_lib, "role": "writer"}],
    )
    rows2 = {row["library_id"] for row in list_entitled_libraries(principal_id)}
    assert only_key_lib not in rows2


def test_lan_host_authorize_and_token_exchange(isolated_client, monkeypatch, portal_user):
    monkeypatch.setattr(settings, "public_base_url", None)
    _enable_authing(monkeypatch)
    _patch_session(monkeypatch, portal_user)
    db.upsert_user_principal(sso_user=portal_user.sub, display_name=portal_user.sub)
    complete_display_name_setup(portal_user.principal_id, portal_user.display_name)
    ensure_personal_library(portal_user.principal_id, portal_user.display_name)

    host = "192.168.1.50:8000"
    resource = f"http://{host}/mcp"
    verifier, challenge = _pkce_pair()
    auth = isolated_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "lan-client",
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,
        },
        headers={"Host": host},
        follow_redirects=False,
    )
    assert auth.status_code == 302, auth.headers
    assert "code=" in auth.headers["location"]
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(auth.headers["location"]).query)["code"][0]
    token = isolated_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8765/callback",
            "client_id": "lan-client",
            "code_verifier": verifier,
            "resource": resource,
        },
        headers={"Host": host},
    )
    assert token.status_code == 200, token.text
    access = token.json()["access_token"]
    who_resp = isolated_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ma3_whoami", "arguments": {}},
        },
        headers={"Host": host, "Authorization": f"Bearer {access}"},
    )
    assert who_resp.status_code == 200, who_resp.text
    structured = who_resp.json()["result"]["structuredContent"]
    assert structured["caller"]["via"] == "mcp_oauth_token"
