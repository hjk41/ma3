"""
Edge cases and boundary conditions.

Covers: auth failures, malformed input, FTS special chars, pagination, library
hierarchy, token lifecycle, invite codes, and FTS/embedding cleanup on delete.
"""
from __future__ import annotations

import pytest
from tests.conftest import make_ingest_payload, make_search_payload, make_knowledge_payload


# ── Auth edge cases ───────────────────────────────────────────────────────────

def test_ingest_without_auth_returns_401(client):
    resp = client.post("/agent/ingest", json=make_ingest_payload())
    assert resp.status_code == 401


def test_knowledge_without_auth_returns_401(client):
    resp = client.post("/knowledge", json=make_knowledge_payload())
    assert resp.status_code == 401


def test_post_record_without_auth_returns_401(client):
    payload = {
        "title": "T", "problem_family": "pf", "summary": "s", "claim": "c",
        "target": {"product": "p"}, "result": {"outcome": "success", "summary": "ok"},
    }
    resp = client.post("/records", json=payload)
    assert resp.status_code == 401


def test_invalid_token_returns_401(client):
    resp = client.post(
        "/agent/ingest",
        json=make_ingest_payload(),
        headers={"X-API-Key": "not-a-real-token"},
    )
    assert resp.status_code == 401


def test_wrong_library_token_cannot_write_other_library(authed_client):
    """Token from lib A should not be able to PATCH records in lib B."""
    lib_a = authed_client.post("/libraries", json={"name": "a"}).json()
    tok_a = authed_client.post(
        f"/libraries/{lib_a['library_id']}/tokens",
        json={"label": "a-tok"},
    ).json()["token"]

    lib_b = authed_client.post("/libraries", json={"name": "b"}).json()
    tok_b = authed_client.post(
        f"/libraries/{lib_b['library_id']}/tokens",
        json={"label": "b-tok"},
    ).json()["token"]

    # B ingests a record
    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(),
        headers={"X-API-Key": tok_b},
    ).json()["record"]["record_id"]

    # A tries to patch B's record — should get 403
    patch_resp = authed_client.patch(
        f"/records/{record_id}",
        json={"summary": "tampered"},
        headers={"X-API-Key": tok_a},
    )
    assert patch_resp.status_code == 403


# ── Input validation ──────────────────────────────────────────────────────────

def test_ingest_missing_required_fields_returns_422(authed_client):
    resp = authed_client.post("/agent/ingest", json={"problem": "no other fields"})
    assert resp.status_code == 422


def test_search_missing_required_fields_returns_422(client):
    resp = client.post("/search", json={"problem": "only problem"})
    assert resp.status_code == 422


def test_knowledge_missing_required_fields_returns_422(authed_client):
    resp = authed_client.post("/knowledge", json={"question": "only question"})
    assert resp.status_code == 422


# ── FTS robustness ────────────────────────────────────────────────────────────

def test_search_with_fts_special_chars_does_not_crash(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    authed_client.post("/agent/ingest", json=make_ingest_payload(), headers=headers)

    for bad_query in ["(timeout)", "timeout OR", "timeout AND (", "**timeout**", '"unclosed']:
        resp = authed_client.post(
            "/search",
            json=make_search_payload(problem=bad_query),
            headers=headers,
        )
        assert resp.status_code == 200, f"Crashed on query: {bad_query!r}"


# ── Record not found ──────────────────────────────────────────────────────────

def test_get_nonexistent_record_returns_404(client):
    resp = client.get("/records/no-such-id-xyz")
    assert resp.status_code == 404


def test_patch_nonexistent_record_returns_404(authed_client):
    resp = authed_client.patch(
        "/records/no-such-id",
        json={"summary": "new summary"},
    )
    assert resp.status_code == 404


# ── Library lifecycle ─────────────────────────────────────────────────────────

def test_cannot_delete_library_with_children(authed_client):
    parent = authed_client.post("/libraries", json={"name": "parent"}).json()
    parent_id = parent["library_id"]

    # Create child under parent using admin
    authed_client.post(
        "/libraries",
        json={"name": "child", "parent_library_id": parent_id},
    )

    resp = authed_client.delete(f"/libraries/{parent_id}")
    assert resp.status_code == 409


def test_delete_nonexistent_library_returns_404(authed_client):
    resp = authed_client.delete("/libraries/no-such-lib")
    assert resp.status_code == 404


def test_delete_library_cleans_fts_and_embeddings(authed_client, lib_with_token):
    """After library deletion, FTS and embeddings for its records should be gone."""
    from app.storage.db import get_connection

    lib_id, token = lib_with_token
    headers = {"X-API-Key": token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["cleanupverify"]),
        headers=headers,
    ).json()["record"]["record_id"]

    # Verify the record exists in the records table (reliable pre-check)
    with get_connection() as conn:
        rec_count_before = conn.execute(
            "SELECT COUNT(*) FROM records WHERE record_id = ?", (record_id,)
        ).fetchone()[0]
    assert rec_count_before == 1

    # Delete library
    authed_client.delete(f"/libraries/{lib_id}")

    # Verify records table entry gone
    with get_connection() as conn:
        rec_count_after = conn.execute(
            "SELECT COUNT(*) FROM records WHERE record_id = ?", (record_id,)
        ).fetchone()[0]
        # FTS: total row count (fresh DB → should be 0 after delete)
        fts_count_after = conn.execute(
            "SELECT COUNT(*) FROM records_fts_tags",
        ).fetchone()[0]
        # Embeddings table is a regular table — WHERE works fine here
        emb_count_after = conn.execute(
            "SELECT COUNT(*) FROM record_embeddings WHERE record_id = ?", (record_id,)
        ).fetchone()[0]

    assert rec_count_after == 0
    assert fts_count_after == 0, "FTS tags entry not cleaned up after library delete"
    assert emb_count_after == 0, "Embedding entry not cleaned up after library delete"


# ── Pagination ────────────────────────────────────────────────────────────────

def test_list_records_pagination(authed_client, lib_with_token):
    _, token = lib_with_token
    headers = {"X-API-Key": token}

    # Ingest 5 records
    for i in range(5):
        authed_client.post(
            "/agent/ingest",
            json=make_ingest_payload(problem=f"issue {i}", result_summary=f"fix {i}"),
            headers=headers,
        )

    page1 = authed_client.get("/records?limit=2&offset=0", headers=headers).json()
    page2 = authed_client.get("/records?limit=2&offset=2", headers=headers).json()

    assert len(page1["records"]) == 2
    assert len(page2["records"]) == 2
    assert page1["records"][0]["record_id"] != page2["records"][0]["record_id"]
    assert page1["total"] == page2["total"]


# ── Invite code flow ──────────────────────────────────────────────────────────

def test_invite_code_creates_library_and_token(authed_client, client):
    # Admin creates invite
    invite = authed_client.post("/invites").json()
    assert "code" in invite

    # Anyone uses the invite
    resp = client.post(
        "/libraries/from-invite",
        json={"code": invite["code"], "name": "my-personal-lib"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["library"]["name"] == "my-personal-lib"
    assert "token" in body  # admin token returned once


def test_invite_code_cannot_be_reused(authed_client, client):
    invite = authed_client.post("/invites").json()
    code = invite["code"]

    # First use: OK
    client.post("/libraries/from-invite", json={"code": code, "name": "lib1"})

    # Second use: error
    resp = client.post("/libraries/from-invite", json={"code": code, "name": "lib2"})
    assert resp.status_code == 400



# ── Role enforcement ──────────────────────────────────────────────────────────

def test_writer_cannot_promote_active_record(authed_client, lib_with_token):
    """Promote remains admin-only and only applies to legacy drafts."""
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    # New writes are active immediately.
    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=writer_headers,
    ).json()["record"]["record_id"]

    # Writer attempts to promote — still rejected because promote is admin-only.
    resp = authed_client.patch(
        f"/records/{record_id}/promote",
        headers=writer_headers,
    )
    assert resp.status_code == 403


def test_admin_promote_rejects_non_draft_record(authed_client, lib_with_admin_token):
    """Promote is now only for legacy drafts; new writes are already active."""
    lib_id, admin_token = lib_with_admin_token
    admin_headers = {"X-API-Key": admin_token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=admin_headers,
    ).json()["record"]["record_id"]

    resp = authed_client.patch(
        f"/records/{record_id}/promote",
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_reader_token_cannot_write(authed_client, lib_with_token):
    """A reader-role token must be rejected on all write endpoints."""
    lib_id, _ = lib_with_token

    # Create a reader token
    reader_tok = authed_client.post(
        f"/libraries/{lib_id}/tokens",
        json={"label": "test-reader", "role": "reader"},
    ).json()["token"]
    reader_headers = {"X-API-Key": reader_tok}

    # reader cannot ingest
    resp = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(),
        headers=reader_headers,
    )
    assert resp.status_code == 403

    # reader cannot post knowledge
    resp = authed_client.post(
        "/knowledge",
        json=make_knowledge_payload(),
        headers=reader_headers,
    )
    assert resp.status_code == 403


def test_reader_token_can_search_private_library(authed_client, lib_with_token):
    """A reader-role token can search records in the private library."""
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    # Writer ingests a record
    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["reader-test"]),
        headers=writer_headers,
    ).json()["record"]["record_id"]

    # Create reader token
    reader_tok = authed_client.post(
        f"/libraries/{lib_id}/tokens",
        json={"label": "test-reader", "role": "reader"},
    ).json()["token"]
    reader_headers = {"X-API-Key": reader_tok}

    # Reader can search and find the record
    search_resp = authed_client.post(
        "/search",
        json=make_search_payload(tags=["reader-test"]),
        headers=reader_headers,
    )
    assert search_resp.status_code == 200
    ids = [m["record"]["record_id"] for m in search_resp.json()["primary_records"]]
    assert record_id in ids


# ── Active visibility + admin deletion ───────────────────────────────────────

def test_library_token_sees_immediately_active_record_in_default_listing(authed_client, lib_with_token):
    """Regression: writes should be visible immediately without promotion."""
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=writer_headers,
    ).json()["record"]["record_id"]

    resp = authed_client.get("/records", headers=writer_headers)
    assert resp.status_code == 200
    ids = [r["record_id"] for r in resp.json()["records"]]
    assert record_id in ids


def test_admin_can_delete_record(authed_client, lib_with_admin_token):
    """Library admin can permanently delete a record in their library."""
    _, admin_token = lib_with_admin_token
    admin_headers = {"X-API-Key": admin_token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(tags=["delete-me"]),
        headers=admin_headers,
    ).json()["record"]["record_id"]

    delete_resp = authed_client.delete(f"/records/{record_id}", headers=admin_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["ok"] is True

    get_resp = authed_client.get(f"/records/{record_id}", headers=admin_headers)
    assert get_resp.status_code == 404


def test_other_library_admin_cannot_delete_foreign_record(authed_client, lib_with_token):
    """Admin deletion is scoped to the record's library."""
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(),
        headers=writer_headers,
    ).json()["record"]["record_id"]

    lib_b = authed_client.post("/libraries", json={"name": "lib-b"}).json()
    tok_b = authed_client.post(
        f"/libraries/{lib_b['library_id']}/tokens",
        json={"label": "b-admin", "role": "admin"},
    ).json()["token"]
    headers_b = {"X-API-Key": tok_b}

    resp = authed_client.delete(f"/records/{record_id}", headers=headers_b)
    assert resp.status_code == 403
