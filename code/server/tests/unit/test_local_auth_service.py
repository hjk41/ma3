"""Unit tests for local_auth_service (password, tokens, validation)."""
from __future__ import annotations

import json
import time

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.core.config import settings
from app.services import local_auth_service
from app.services.api_key_encryption import _fernet_key_material
from app.storage import db


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "local-auth-unit.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    db.initialize_database()


def _enable_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "authing_issuer", "")
    monkeypatch.setattr(settings, "authing_app_id", "")
    monkeypatch.setattr(settings, "authing_app_secret", "")
    monkeypatch.setattr(settings, "local_auth", True)
    monkeypatch.setattr(settings, "local_auth_open_registration", True)
    monkeypatch.setattr(settings, "api_key_encryption_secret", "unit-local-auth-secret")
    monkeypatch.setattr(settings, "auth_admin_users", ())


def test_validate_username_and_password(monkeypatch):
    _enable_local(monkeypatch)
    assert local_auth_service.validate_username("Alice_1") == "alice_1"
    with pytest.raises(HTTPException) as bad_user:
        local_auth_service.validate_username("a")
    assert bad_user.value.status_code == 400
    with pytest.raises(HTTPException) as bad_pw:
        local_auth_service.validate_password("short")
    assert bad_pw.value.status_code == 400
    assert local_auth_service.validate_password("longenough") == "longenough"


def test_hash_and_verify_password(monkeypatch):
    _enable_local(monkeypatch)
    digest = local_auth_service.hash_password("password123")
    assert digest.startswith("$argon2")
    assert local_auth_service.verify_password(digest, "password123") is True
    assert local_auth_service.verify_password(digest, "password124") is False


def test_session_token_roundtrip(monkeypatch):
    _enable_local(monkeypatch)
    account = local_auth_service.register_local_user(username="tokuser", password="password123")
    token = local_auth_service.issue_local_session_token(account)
    assert token.startswith("local.v1.")
    parsed = local_auth_service.parse_local_session_token(token)
    assert parsed is not None
    assert parsed["username"] == "tokuser"
    assert parsed["principal_id"] == account["principal_id"]
    assert parsed["is_admin"] is True


def test_session_token_expired(monkeypatch):
    _enable_local(monkeypatch)
    account = local_auth_service.register_local_user(username="expuser", password="password123")
    payload = {
        "v": 1,
        "pid": account["principal_id"],
        "u": "expuser",
        "admin": True,
        "exp": int(time.time()) - 10,
    }
    raw = Fernet(_fernet_key_material()).encrypt(json.dumps(payload).encode("utf-8")).decode("ascii")
    assert local_auth_service.parse_local_session_token("local.v1." + raw) is None


def test_session_token_tampered(monkeypatch):
    _enable_local(monkeypatch)
    account = local_auth_service.register_local_user(username="tamper", password="password123")
    token = local_auth_service.issue_local_session_token(account)
    # Flip a character in the ciphertext body (not the prefix).
    body = token[len("local.v1.") :]
    flipped = ("A" if body[10] != "A" else "B") + body[11:]
    flipped = body[:10] + flipped
    assert local_auth_service.parse_local_session_token("local.v1." + flipped) is None
    assert local_auth_service.parse_local_session_token("not-a-local-token") is None
    assert local_auth_service.parse_local_session_token("local.v1.not-valid-fernet") is None


def test_duplicate_username_raises(monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="dup", password="password123")
    with pytest.raises(HTTPException) as exc:
        local_auth_service.register_local_user(username="DUP", password="password123")
    assert exc.value.status_code == 409


def test_closed_registration_after_first(monkeypatch):
    _enable_local(monkeypatch)
    monkeypatch.setattr(settings, "local_auth_open_registration", False)
    local_auth_service.register_local_user(username="only", password="password123")
    with pytest.raises(HTTPException) as exc:
        local_auth_service.register_local_user(username="second", password="password123")
    assert exc.value.status_code == 403


def test_auth_admin_users_whitelist(monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="owner", password="password123")
    monkeypatch.setattr(settings, "auth_admin_users", ("ops",))
    privileged = local_auth_service.register_local_user(username="ops", password="password123")
    assert privileged["is_admin"] is True
    normal = local_auth_service.register_local_user(username="member", password="password123")
    assert normal["is_admin"] is False


def test_set_local_account_admin(monkeypatch):
    _enable_local(monkeypatch)
    local_auth_service.register_local_user(username="root", password="password123")
    local_auth_service.register_local_user(username="promo", password="password123")
    row = local_auth_service.set_local_account_admin(username="promo", is_admin=True)
    assert row is not None
    assert bool(int(row["is_admin"])) is True
    assert db.get_local_account("promo")["is_admin"] in (1, True)


def test_local_auth_disabled_blocks_register(monkeypatch):
    monkeypatch.setattr(settings, "authing_enabled", False)
    monkeypatch.setattr(settings, "local_auth", False)
    with pytest.raises(HTTPException) as exc:
        local_auth_service.register_local_user(username="x", password="password123")
    assert exc.value.status_code == 503
