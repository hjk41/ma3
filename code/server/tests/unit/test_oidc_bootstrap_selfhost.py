"""Unit tests for OIDC env resolution and self-host bootstrap."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services import bootstrap_selfhost
from app.storage import db


def test_oidc_env_preferred_over_authing(monkeypatch):
    monkeypatch.setenv("MA3_OIDC_ENABLED", "1")
    monkeypatch.setenv("MA3_OIDC_ISSUER", "https://idp.example.com/realms/ma3")
    monkeypatch.setenv("MA3_OIDC_CLIENT_ID", "ma3-client")
    monkeypatch.setenv("MA3_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MA3_AUTHING_ENABLED", "0")
    s = Settings()
    assert s.oidc_configured is True
    assert s.authing_configured is True  # alias
    assert s.oidc_issuer_base() == "https://idp.example.com/realms/ma3"
    assert "oidc" in s.feature_flags
    assert "authing" not in s.feature_flags


def test_authing_legacy_appends_oidc_path(monkeypatch):
    monkeypatch.delenv("MA3_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("MA3_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("MA3_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("MA3_OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("MA3_AUTHING_ENABLED", "1")
    monkeypatch.setenv("MA3_AUTHING_ISSUER", "https://app.authing.cn")
    monkeypatch.setenv("MA3_AUTHING_APP_ID", "appid")
    monkeypatch.setenv("MA3_AUTHING_APP_SECRET", "appsecret")
    s = Settings()
    assert s.oidc_configured is True
    assert s.oidc_issuer_base() == "https://app.authing.cn/oidc"
    assert "authing" in s.feature_flags


def test_bootstrap_creates_key_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MA3_OIDC_ENABLED", raising=False)
    monkeypatch.delenv("MA3_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("MA3_AUTHING_ENABLED", raising=False)
    monkeypatch.delenv("MA3_AUTHING_ISSUER", raising=False)
    db_path = tmp_path / "ma3.db"
    key_file = tmp_path / "bootstrap_api_key.txt"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MA3_BOOTSTRAP_SELFHOST", "1")
    monkeypatch.setenv("MA3_BOOTSTRAP_KEY_FILE", str(key_file))
    monkeypatch.setenv("MA3_DISABLE_EMBEDDINGS", "1")
    # Reload settings fields used by bootstrap
    from app.core import config as config_mod

    config_mod.settings = Settings()
    monkeypatch.setattr(bootstrap_selfhost, "settings", config_mod.settings)
    monkeypatch.setattr(db, "settings", config_mod.settings) if hasattr(db, "settings") else None

    db.initialize_database()
    result = bootstrap_selfhost.ensure_bootstrap_key()
    assert result is not None
    assert result["plaintext_key"].startswith("ma3k_")
    assert key_file.is_file()
    assert "plaintext_key=" in key_file.read_text(encoding="utf-8")

    # Second call is idempotent (file exists)
    assert bootstrap_selfhost.ensure_bootstrap_key() is None
