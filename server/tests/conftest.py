"""
Shared fixtures for the ma3 test suite.

Every test gets:
  - an isolated SQLite database in a pytest tmp_path
  - a known admin API key
  - deterministic hash-based embedding mocks (no sentence-transformers required)
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main as app_module
from app.core import config
from app.storage.db import initialize_database

# ── Constants ────────────────────────────────────────────────────────────────

ADMIN_KEY = "rc-test-admin-key"
EMBED_DIM = 384


# ── Embedding mock ────────────────────────────────────────────────────────────

def _mock_embed_text(text: str) -> np.ndarray:
    """Deterministic unit vector seeded from text hash."""
    seed = hash(text) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBED_DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def _mock_embed_record(record) -> np.ndarray:
    parts = [record.title, record.summary, record.claim] + (record.tags or [])
    return _mock_embed_text(". ".join(p for p in parts if p))


# ── Autouse: isolated settings ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    """Redirect every test to a fresh DB and set a known admin key."""
    orig_db = config.settings.db_path
    orig_database_url = config.settings.database_url
    orig_backend = config.settings.db_backend
    orig_key = config.settings.api_key
    orig_seed = config.settings.seed_path
    orig_public_base_url = config.settings.public_base_url
    orig_instance_id = config.settings.instance_id
    orig_git_commit = config.settings.git_commit
    orig_op_log_dir = config.settings.op_log_dir
    orig_log_archive_dir = config.settings.log_archive_dir
    orig_log_local_retention_days = config.settings.log_local_retention_days
    orig_log_redact_raw = config.settings.log_redact_raw

    db = tmp_path / "test.db"
    object.__setattr__(config.settings, "db_path", db)
    object.__setattr__(config.settings, "database_url", None)
    object.__setattr__(config.settings, "db_backend", "sqlite")
    object.__setattr__(config.settings, "api_key", ADMIN_KEY)
    object.__setattr__(config.settings, "public_base_url", None)
    object.__setattr__(config.settings, "instance_id", None)
    object.__setattr__(config.settings, "git_commit", None)
    object.__setattr__(config.settings, "op_log_dir", tmp_path / "ops")
    object.__setattr__(config.settings, "log_archive_dir", tmp_path / "archive")
    object.__setattr__(config.settings, "log_local_retention_days", 2)
    object.__setattr__(config.settings, "log_redact_raw", True)
    # Point seed_path at a non-existent file so seed_if_empty() is a no-op
    object.__setattr__(config.settings, "seed_path", tmp_path / "no_seed.json")

    initialize_database()
    yield

    object.__setattr__(config.settings, "db_path", orig_db)
    object.__setattr__(config.settings, "database_url", orig_database_url)
    object.__setattr__(config.settings, "db_backend", orig_backend)
    object.__setattr__(config.settings, "api_key", orig_key)
    object.__setattr__(config.settings, "seed_path", orig_seed)
    object.__setattr__(config.settings, "public_base_url", orig_public_base_url)
    object.__setattr__(config.settings, "instance_id", orig_instance_id)
    object.__setattr__(config.settings, "git_commit", orig_git_commit)
    object.__setattr__(config.settings, "op_log_dir", orig_op_log_dir)
    object.__setattr__(config.settings, "log_archive_dir", orig_log_archive_dir)
    object.__setattr__(config.settings, "log_local_retention_days", orig_log_local_retention_days)
    object.__setattr__(config.settings, "log_redact_raw", orig_log_redact_raw)


# ── Autouse: mock embeddings ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _mock_embeddings(monkeypatch):
    """Replace real sentence-transformer embeddings with deterministic mocks.

    Three patches are needed:
    - app.storage.repositories.embed_record  (module-level import in repositories.py)
    - app.services.search_service.embed_text  (module-level import in search_service.py)
    - app.services.embedding_service.embed_record  (local import in db.backfill_search_indexes)
    - app.services.embedding_service.embed_text  (for completeness)
    """
    monkeypatch.setattr("app.storage.repositories.embed_record", _mock_embed_record)
    monkeypatch.setattr("app.services.search_service.embed_text", _mock_embed_text)
    monkeypatch.setattr("app.services.embedding_service.embed_record", _mock_embed_record)
    monkeypatch.setattr("app.services.embedding_service.embed_text", _mock_embed_text)


# ── HTTP client fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Unauthenticated TestClient."""
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def authed_client(client):
    """TestClient with admin key pre-set on every request."""
    client.headers["X-API-Key"] = ADMIN_KEY
    return client


# ── Library + token helpers ───────────────────────────────────────────────────

@pytest.fixture
def lib_with_token(authed_client):
    """Create a library and return (library_id, raw_writer_token)."""
    lib = authed_client.post(
        "/libraries",
        json={"name": "test-lib", "description": "for tests", "is_public": True},
    ).json()
    tok = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "test-writer", "role": "writer"},
    ).json()
    return lib["library_id"], tok["token"]


@pytest.fixture
def lib_with_admin_token(authed_client):
    """Create a library and return (library_id, raw_admin_token)."""
    lib = authed_client.post(
        "/libraries",
        json={"name": "admin-lib", "description": "admin token tests", "is_public": True},
    ).json()
    tok = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "test-admin", "role": "admin"},
    ).json()
    return lib["library_id"], tok["token"]


# ── Payload builder helpers ───────────────────────────────────────────────────

def make_ingest_payload(**overrides) -> dict:
    base = {
        "problem": "API call times out after 10s",
        "task_type": "troubleshooting",
        "goal": "reduce timeout errors",
        "target": {"product": "my-api", "component": "http-client"},
        "outcome": "success",
        "result_summary": "Increased timeout to 30s, errors stopped",
        "actions": [{"action": "Set timeout=30 in client config"}],
        "tags": ["timeout", "http-client"],
    }
    base.update(overrides)
    return base


def make_search_payload(**overrides) -> dict:
    base = {
        "problem": "API call times out",
        "query_intent": "fix",
        "task_type": "troubleshooting",
        "target": {"product": "my-api"},
        "goal": "reduce timeout errors",
    }
    base.update(overrides)
    return base


def make_knowledge_payload(**overrides) -> dict:
    base = {
        "question": "What is the default API timeout?",
        "summary": "The default timeout is 10 seconds.",
        "source_type": "authority_defined",
        "knowledge_kind": "specification",
        "tags": ["timeout", "api"],
    }
    base.update(overrides)
    return base
