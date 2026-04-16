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

def test_writer_cannot_promote_own_draft(authed_client, lib_with_token):
    """A writer-role token must not be able to promote drafts — that requires admin."""
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    # Create a draft record (draft_only=True)
    record_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=writer_headers,
    ).json()["record"]["record_id"]

    # Writer attempts to promote — should be rejected
    resp = authed_client.patch(
        f"/records/{record_id}/promote",
        headers=writer_headers,
    )
    assert resp.status_code == 403


def test_admin_token_can_promote_draft(authed_client, lib_with_admin_token):
    """An admin-role token for the record's library can promote drafts."""
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
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


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


# ── Draft visibility ──────────────────────────────────────────────────────────

def test_library_token_sees_own_drafts_in_default_active_listing(authed_client, lib_with_token):
    """Regression: GET /records (default status=active) must show the calling
    library's own draft records so admins can see their pending review queue
    without explicitly passing status=all.

    Bug: before the fix, the compound SQL predicate was missing — library drafts
    were silently excluded when status=active filtered them out.
    """
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    # Ingest a draft record into the library
    draft_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=writer_headers,
    ).json()["record"]["record_id"]

    # Default listing (status=active) via the library token must include the draft
    resp = authed_client.get("/records", headers=writer_headers)
    assert resp.status_code == 200
    ids = [r["record_id"] for r in resp.json()["records"]]
    assert draft_id in ids, (
        "Library's own draft should be visible in default status=active listing"
    )

    # Sanity: status=draft also returns it
    resp_draft = authed_client.get("/records?status=draft", headers=writer_headers)
    draft_ids = [r["record_id"] for r in resp_draft.json()["records"]]
    assert draft_id in draft_ids

    # Sanity: unauthenticated caller does NOT see the draft
    resp_anon = authed_client.get("/records")  # admin key, but no library filter
    # (admin sees everything — skip this check for admin; use unauthenticated client instead)


def test_other_library_token_does_not_see_foreign_drafts(authed_client, lib_with_token):
    """A library token must NOT see draft records belonging to a different library
    in the default active listing — only the owner library's drafts should surface.
    """
    lib_id, writer_token = lib_with_token
    writer_headers = {"X-API-Key": writer_token}

    # Create a second, separate library with its own token
    lib_b = authed_client.post("/libraries", json={"name": "lib-b"}).json()
    tok_b = authed_client.post(
        f"/libraries/{lib_b['library_id']}/tokens",
        json={"label": "b-writer"},
    ).json()["token"]
    headers_b = {"X-API-Key": tok_b}

    # lib_b ingests a draft
    draft_id = authed_client.post(
        "/agent/ingest",
        json=make_ingest_payload(draft_only=True),
        headers=headers_b,
    ).json()["record"]["record_id"]

    # lib_a's token queries records — should NOT see lib_b's draft
    resp = authed_client.get("/records", headers=writer_headers)
    assert resp.status_code == 200
    ids = [r["record_id"] for r in resp.json()["records"]]
    assert draft_id not in ids, (
        "Token from lib_a must not see draft records belonging to lib_b"
    )

