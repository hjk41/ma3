from __future__ import annotations

import pytest

from fastapi import HTTPException

from app.core.config import settings
from app.services import api_key_service
from app.services.onboarding_service import (
    create_personal_dev_key,
    ensure_personal_library,
    normalize_api_key_grants,
    personal_library_id,
    resolve_key_grants,
)
from app.storage import db


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "onboard-unit.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "max_keys_per_principal", 10)
    db.initialize_database()


def test_ensure_personal_library_is_idempotent():
    first = ensure_personal_library("user:alice", "Alice")
    second = ensure_personal_library("user:alice", "Alice")
    assert first["library_id"] == second["library_id"]
    libs = [lib for lib in db.list_libraries() if lib.get("kind") == "personal" and lib.get("owner_principal_id") == "user:alice"]
    assert len(libs) == 1


def test_ensure_personal_library_reuses_seed_style_library():
    db.ensure_library(
        "lib_personal_seed_style",
        name="Seed Style",
        visibility="private",
        kind="personal",
        owner_principal_id="user:bob",
    )
    lib = ensure_personal_library("user:bob", "Bob")
    assert lib["library_id"] == "lib_personal_seed_style"


def test_create_personal_dev_key_grants_and_resolves():
    created = create_personal_dev_key("user:carol", "Carol", label="laptop")
    assert created["plaintext_key"].startswith("ma3k_")
    assert created["key_prefix"] == created["plaintext_key"][:12]
    resolved = api_key_service.resolve_api_key(created["plaintext_key"])
    assert resolved is not None
    assert settings.default_library_id in resolved.writable
    personal = db.find_personal_library("user:carol")
    assert personal is not None
    assert personal["library_id"] in resolved.writable


def test_key_quota_enforced(monkeypatch):
    monkeypatch.setattr(settings, "max_keys_per_principal", 1)
    create_personal_dev_key("user:dave", "Dave", label="one")
    with pytest.raises(HTTPException) as exc:
        create_personal_dev_key("user:dave", "Dave", label="two")
    assert exc.value.status_code == 400


def test_personal_library_id_is_deterministic():
    assert personal_library_id("user:alice") == personal_library_id("user:alice")
    assert personal_library_id("user:alice").startswith("lib_personal_")


def test_resolve_key_grants_defaults_dual_writer():
    lib_id = personal_library_id("user:eve")
    grants = resolve_key_grants(
        personal_library_id=lib_id,
        personal_role="writer",
        community_role="writer",
        principal_id="user:eve",
    )
    assert grants == [
        {"library_id": lib_id, "role": "writer"},
        {"library_id": settings.default_library_id, "role": "writer"},
    ]


def test_free_tier_rejects_community_non_writer():
    lib_id = personal_library_id("user:free")
    with pytest.raises(HTTPException) as exc:
        resolve_key_grants(
            personal_library_id=lib_id,
            personal_role="writer",
            community_role="reader",
            principal_id="user:free",
        )
    assert exc.value.status_code == 400


def test_paid_tier_allows_community_reader(monkeypatch):
    monkeypatch.setattr(settings, "paid_principal_ids", ("user:paid",))
    lib_id = personal_library_id("user:paid")
    grants = resolve_key_grants(
        personal_library_id=lib_id,
        personal_role="reader",
        community_role="reader",
        principal_id="user:paid",
    )
    assert grants == [
        {"library_id": lib_id, "role": "reader"},
        {"library_id": settings.default_library_id, "role": "reader"},
    ]


def test_normalize_api_key_grants_from_explicit_list():
    lib_id = personal_library_id("user:frank")
    grants = normalize_api_key_grants(
        [
            {"library_id": lib_id, "role": "reader"},
            {"library_id": settings.default_library_id, "role": "writer"},
        ],
        personal_library_id=lib_id,
        principal_id="user:frank",
    )
    assert grants == [
        {"library_id": lib_id, "role": "reader"},
        {"library_id": settings.default_library_id, "role": "writer"},
    ]
