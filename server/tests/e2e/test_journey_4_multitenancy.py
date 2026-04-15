"""
Journey 4: Multi-tenancy isolation.

Scenario:
  Library A and Library B are separate tenants.  A's private records must NOT
  appear in B's search results, and vice-versa for private libraries.  Public
  libraries are visible to everyone (including unauthenticated callers).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import make_ingest_payload, make_search_payload, ADMIN_KEY


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def lib_a(authed_client):
    """Private library A with writer token."""
    lib = authed_client.post(
        "/libraries",
        json={"name": "lib-a", "is_public": False},
    ).json()
    tok = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "a-writer"},
    ).json()
    return lib["library_id"], tok["token"]


@pytest.fixture
def lib_b(authed_client):
    """Private library B with writer token."""
    lib = authed_client.post(
        "/libraries",
        json={"name": "lib-b", "is_public": False},
    ).json()
    tok = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "b-writer"},
    ).json()
    return lib["library_id"], tok["token"]


@pytest.fixture
def public_lib(authed_client):
    """Public library with writer token."""
    lib = authed_client.post(
        "/libraries",
        json={"name": "public-lib", "is_public": True},
    ).json()
    tok = authed_client.post(
        f"/libraries/{lib['library_id']}/tokens",
        json={"label": "pub-writer"},
    ).json()
    return lib["library_id"], tok["token"]


# ── J4-A: Library B cannot search records owned by library A ─────────────────

def test_private_record_invisible_to_other_library(authed_client, lib_a, lib_b):
    lib_a_id, tok_a = lib_a
    lib_b_id, tok_b = lib_b

    # A ingests a private record
    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["lib-a-only"]),
        headers={"X-API-Key": tok_a},
    ).json()["record"]["record_id"]

    # B searches — should not see A's record
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(tags=["lib-a-only"]),
        headers={"X-API-Key": tok_b},
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id not in primary_ids


# ── J4-B: Library A sees its own records ─────────────────────────────────────

def test_library_sees_own_records(authed_client, lib_a):
    _, tok_a = lib_a

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["my-own-record"]),
        headers={"X-API-Key": tok_a},
    ).json()["record"]["record_id"]

    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(tags=["my-own-record"]),
        headers={"X-API-Key": tok_a},
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id in primary_ids


# ── J4-C: Public library records visible to unauthenticated callers ───────────

def test_public_records_visible_without_auth(authed_client, client, public_lib):
    _, tok_pub = public_lib

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["public-record"]),
        headers={"X-API-Key": tok_pub},
    ).json()["record"]["record_id"]

    # Unauthenticated search
    search_resp = client.post(
        "/search",
        json=make_search_payload(tags=["public-record"]),
    )
    primary_ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id in primary_ids


# ── J4-D: Admin key sees records across all libraries ─────────────────────────

def test_admin_key_sees_all_libraries(authed_client, lib_a, lib_b):
    _, tok_a = lib_a
    _, tok_b = lib_b

    id_a = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["admin-sees-a"]),
        headers={"X-API-Key": tok_a},
    ).json()["record"]["record_id"]

    id_b = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["admin-sees-b"]),
        headers={"X-API-Key": tok_b},
    ).json()["record"]["record_id"]

    # Admin search for each tag
    for tag, expected_id in [("admin-sees-a", id_a), ("admin-sees-b", id_b)]:
        resp = authed_client.post(
            "/search",
            json=make_search_payload(tags=[tag]),
        )
        ids = [m["record"]["record_id"] for m in resp.json()["primary_records"]]
        assert expected_id in ids


# ── J4-E: Library delete cascades, records gone from search ───────────────────

def test_delete_library_removes_records(authed_client, lib_a):
    lib_id, tok_a = lib_a

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["to-be-deleted"]),
        headers={"X-API-Key": tok_a},
    ).json()["record"]["record_id"]

    # Delete library
    del_resp = authed_client.delete(f"/libraries/{lib_id}")
    assert del_resp.status_code == 204

    # Admin search should not find the record
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(tags=["to-be-deleted"]),
    )
    all_ids = [
        m["record"]["record_id"]
        for m in search_resp.json()["primary_records"] + search_resp.json()["contrasting_records"]
    ]
    assert record_id not in all_ids


# ── J4-F: whoami identifies caller correctly ──────────────────────────────────

def test_whoami_admin(authed_client):
    resp = authed_client.get("/libraries/whoami")
    assert resp.status_code == 200
    assert resp.json()["type"] == "admin"


def test_whoami_library_token(authed_client, lib_a):
    _, tok_a = lib_a
    resp = authed_client.get("/libraries/whoami", headers={"X-API-Key": tok_a})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "library_token"
    assert "library" in body


def test_whoami_anonymous(client):
    resp = client.get("/libraries/whoami")
    assert resp.status_code == 200
    assert resp.json()["type"] == "anonymous"
