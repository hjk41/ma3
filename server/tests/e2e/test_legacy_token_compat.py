from __future__ import annotations

from app.models.library import LibraryCreate, TokenCreate
from app.services.library_service import create_library, create_token
from scripts.migrate_v2_tokens_to_v3 import migrate
from tests.conftest import make_ingest_payload


def test_migration_and_legacy_whoami_compat(client):
    lib = create_library(LibraryCreate(name="legacy", is_public=False))
    tok = create_token(lib.library_id, TokenCreate(label="legacy-writer", role="writer"))
    migrate(apply=True)
    v2 = client.get("/libraries/whoami", headers={"X-API-Key": tok.token})
    assert v2.status_code == 200
    assert v2.json()["type"] == "library_token"
    assert v2.json()["token_id"] == tok.token_id
    assert v2.json()["role"] == "writer"
    assert v2.json()["principal_id"] == f"legacy:{tok.token_id}"

    v3 = client.get("/v3/auth/whoami", headers={"X-API-Key": tok.token})
    assert v3.status_code == 200
    assert v3.json()["principal"]["kind"] == "legacy"
    assert v3.json()["libraries"][0]["library_id"] == lib.library_id


def test_legacy_token_can_still_ingest(client):
    lib = create_library(LibraryCreate(name="legacy", is_public=False))
    tok = create_token(lib.library_id, TokenCreate(label="legacy-writer", role="writer"))
    resp = client.post("/agent/ingest", json=make_ingest_payload(), headers={"X-API-Key": tok.token})
    assert resp.status_code == 200
    assert resp.json()["record"]["library_id"] == lib.library_id
