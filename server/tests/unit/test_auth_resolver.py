from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.core import config
from app.core.auth import VerifyResult, _resolve_from_raw_only, clear_sso_verify_cache, resolve_principal, verify_sso_cookie
from app.models.auth import ResolvedPrincipal
from app.models.library import LibraryCreate, TokenCreate
from app.services.auth_service import bootstrap_library_admin, issue_api_key
from app.services.library_service import create_library, create_token
from app.storage.repositories import ApiKeyRepository, PrincipalRepository, TokenRepository
from app.core.security import hash_token
from tests.conftest import ADMIN_KEY


def _request(cookie: str | None = None):
    return SimpleNamespace(cookies={"gateway_token": cookie} if cookie else {})


def test_admin_key_resolves_to_admin_bypass():
    principal = _resolve_from_raw_only(ADMIN_KEY)
    assert principal.kind == "admin"
    assert principal.is_admin_bypass is True


def test_api_key_and_sso_cookie_different_user_conflict(monkeypatch):
    alice = PrincipalRepository().upsert_user("alice", "Alice")
    actor = ResolvedPrincipal(alice.principal_id, alice.kind, alice.display_name, "sso_cookie", False)
    lib = create_library(LibraryCreate(name="alice-lib", is_public=False))
    bootstrap_library_admin(lib.library_id, alice.principal_id, actor=actor)
    raw = issue_api_key(alice.principal_id, "alice-key", [lib.library_id], None, actor=actor).raw
    monkeypatch.setattr("app.core.auth.verify_sso_cookie", lambda jwt: VerifyResult(user="bob", display_name="Bob"))
    with pytest.raises(HTTPException) as exc:
        resolve_principal(_request("cookie"), x_api_key=raw, authorization=None)
    assert exc.value.status_code == 400
    assert exc.value.detail == "auth_conflict"


def test_revoked_and_expired_api_key_return_401():
    user = PrincipalRepository().upsert_user("alice", "Alice")
    actor = ResolvedPrincipal(user.principal_id, user.kind, user.display_name, "sso_cookie", False)
    lib = create_library(LibraryCreate(name="lib", is_public=False))
    bootstrap_library_admin(lib.library_id, user.principal_id, actor=actor)
    revoked = issue_api_key(user.principal_id, "revoked", [lib.library_id], None, actor=actor)
    ApiKeyRepository().revoke(revoked.info.key_id, "2999-01-01T00:00:00+00:00")
    with pytest.raises(HTTPException) as exc:
        _resolve_from_raw_only(revoked.raw)
    assert exc.value.status_code == 401

    expired = issue_api_key(user.principal_id, "expired", [lib.library_id], "2000-01-01T00:00:00+00:00", actor=actor)
    with pytest.raises(HTTPException) as exc:
        _resolve_from_raw_only(expired.raw)
    assert exc.value.status_code == 401


def test_verify_endpoint_failures_return_anonymous(monkeypatch):
    clear_sso_verify_cache()
    object.__setattr__(config.settings, "auth_verify_url", "https://auth.example/verify")

    class TimeoutClient:
        def get(self, *args, **kwargs):
            raise httpx.TimeoutException("boom")

    monkeypatch.setattr("app.core.auth._http", lambda: TimeoutClient())
    assert verify_sso_cookie("jwt-timeout") is None

    class BadClient:
        def get(self, *args, **kwargs):
            return httpx.Response(200, json={"valid": False})

    monkeypatch.setattr("app.core.auth._http", lambda: BadClient())
    assert verify_sso_cookie("jwt-invalid") is None


def test_sso_admin_flag_requires_ma3_allowlist(monkeypatch):
    object.__setattr__(config.settings, "auth_admin_users", tuple())
    monkeypatch.setattr(
        "app.core.auth.verify_sso_cookie",
        lambda jwt: VerifyResult(user="alice", display_name="Alice", admin=True),
    )
    principal = resolve_principal(_request("cookie"), x_api_key=None, authorization=None)
    assert principal.kind == "user"
    assert principal.is_admin_bypass is False


def test_lazy_legacy_resolution_without_migration():
    lib = create_library(LibraryCreate(name="legacy-lib", is_public=False))
    raw = "legacy-raw"
    TokenRepository().insert("tok_lazy", hash_token(raw), lib.library_id, "lazy", "writer", "2026-01-01T00:00:00+00:00")
    principal = _resolve_from_raw_only(raw)
    assert principal.kind == "legacy"
    assert principal.principal_id == "legacy:tok_lazy"
    assert principal.library_id == lib.library_id
