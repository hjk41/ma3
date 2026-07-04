from __future__ import annotations

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.storage.db import initialize_database


@pytest.fixture()
def isolated_client(tmp_path, monkeypatch):
    """Fresh SQLite database per test."""
    db_path = tmp_path / "ma3-test.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MA3_DEV_AUTH", "1")
    monkeypatch.setenv("MA3_DEV_API_KEY", "ma3dev")
    monkeypatch.setenv("MA3_DISABLE_EMBEDDINGS", "1")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "dev_auth", True)
    monkeypatch.setattr(settings, "dev_api_key", "ma3dev")
    monkeypatch.setattr(settings, "disable_embeddings", True)
    initialize_database()
    from app.storage import db as _db

    _db.set_library_write_buffer_hours(settings.default_library_id, 0)

    from app.main import app

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture(scope="session")
def deploy_base_url() -> str:
    return os.environ.get("MA3_BASE_URL", "http://192.168.31.202:8000").rstrip("/")


@pytest.fixture(scope="session")
def deploy_api_key() -> str:
    return os.environ.get("MA3_API_KEY", "ma3dev")


@pytest.fixture(scope="session")
def deploy_http(deploy_base_url: str):
    timeout = float(os.environ.get("MA3_HTTP_TIMEOUT", "30"))
    with httpx.Client(base_url=deploy_base_url, timeout=timeout, trust_env=False) as client:
        yield client
