"""Integration tests for ADR-013 / design-10: write confirmation, audit, and delete.

These tests encode the design as an executable spec. They cover:

* W1 — ``report_kind`` / ``confirmation`` / ``target_record_id`` on ``ma3_report``
        and the ``write_audit_log`` append.
* W2 — ``ma3_list_my_writes`` audit tool.
* W3 — ``ma3_delete_record`` hard delete + tombstone + ``source_deleted`` lineage
        warning, owner-only ACL.
* W4 — library readable ``name`` surfaced in ``ma3_whoami`` / ``ma3_context``.
* W5 — paid deletion protection: soft delete (recycle bin) + ``ma3_restore_record``.

Design deviations intentionally taken for backward compatibility (flagged for
review):

* ``report_kind`` and ``confirmation`` are OPTIONAL on the wire. Legacy callers
  that omit ``report_kind`` are treated as ``new`` with ``confirmation=agent_judged``
  so the ~50 existing ma3_report call sites and deployed agents keep working.
  When a caller DOES set ``report_kind`` to ``supplement``/``new`` it must also
  send a valid ``confirmation`` (opting into the judgment tree).
* "Default personal library" for DB-backed API keys: omitting ``library_id`` on
  ``new``/``supplement`` writes defaults to the caller's single owned personal library
  (``kind=personal``); public/community writes require explicit ``library_id``.
  Dev bypass and env writer/maintainer keys still default to ``lib_default``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.storage import db
from tests.helpers.mcp_client import McpClient

_EVIDENCE = [{"kind": "test", "summary": "write-audit integration evidence"}]


def _writer_keys(monkeypatch, *keys: str) -> None:
    monkeypatch.setattr("app.core.config.settings.writer_api_keys", tuple(keys))


def _make_library(name: str, *, visibility: str = "private") -> str:
    lib_id = db.new_id("lib")
    db.create_library(lib_id, name=name, visibility=visibility)
    return lib_id


def _make_protected_library(name: str = "Org X 部署经验", retention_days: int = 30) -> str:
    """Create an org-owned library with deletion_protection on (simulates Team plan)."""
    lib_id = _make_library(name, visibility="private")
    db.set_deletion_protection(lib_id, enabled=True, retention_days=retention_days)
    return lib_id


def _context_record_ids(ctx: dict) -> set[str]:
    ids = {r["id"] for group in ctx.get("cases", []) for r in group.get("records", [])}
    ids.update(r["id"] for r in ctx.get("ungrouped_records", []))
    return ids


def _assert_audit_row(
    *,
    record_id: str,
    principal_id: str,
    report_kind: str,
    confirmation: str,
    library_id: str | None = None,
) -> None:
    row = db.get_write_audit_for_record(record_id)
    assert row is not None, f"write_audit_log missing for {record_id}"
    assert row["principal_id"] == principal_id
    assert row["report_kind"] == report_kind
    assert row["confirmation"] == confirmation
    assert row["api_key_id"]
    if library_id is not None:
        assert row["library_id"] == library_id


# --------------------------------------------------------------------------- #
# W1: report_kind / confirmation / target_record_id
# --------------------------------------------------------------------------- #


def test_legacy_report_defaults_to_new_agent_judged(isolated_client):
    """A report with no report_kind still works and is audited as new/agent_judged."""
    mcp = McpClient(isolated_client, api_key="ma3dev")
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "legacy report without report_kind",
            "outcome": "resolved",
            "result_summary": "should default to new",
            "evidence": _EVIDENCE,
        },
    )
    assert report["persisted"] is True
    assert report["report_kind"] == "new"
    assert report["confirmation"] == "agent_judged"
    _assert_audit_row(
        record_id=report["record_id"],
        principal_id="dev:admin",
        report_kind="new",
        confirmation="agent_judged",
        library_id=settings.default_library_id,
    )


def test_explicit_new_requires_confirmation(isolated_client):
    """Opting into the judgment tree (report_kind set) requires a valid confirmation."""
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "explicit new without confirmation",
                "outcome": "resolved",
                "result_summary": "should be rejected",
                "report_kind": "new",
                "evidence": _EVIDENCE,
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32000
    assert "confirmation" in err["message"].lower()


def test_invalid_confirmation_rejected(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "new with bogus confirmation",
                "outcome": "resolved",
                "result_summary": "should fail",
                "report_kind": "new",
                "confirmation": "yolo",
                "evidence": _EVIDENCE,
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32000
    assert "confirmation" in err["message"].lower()


def test_supplement_user_confirmed_persists_and_audits(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    report = mcp.structured(
        "ma3_report",
        {
            "problem": "supplement with user confirmation",
            "outcome": "resolved",
            "result_summary": "user said yes to community library",
            "report_kind": "supplement",
            "confirmation": "user_confirmed",
            "evidence": _EVIDENCE,
        },
    )
    assert report["persisted"] is True
    assert report["report_kind"] == "supplement"
    assert report["confirmation"] == "user_confirmed"
    _assert_audit_row(
        record_id=report["record_id"],
        principal_id="dev:admin",
        report_kind="supplement",
        confirmation="user_confirmed",
        library_id=settings.default_library_id,
    )


def test_verify_writes_to_target_library_and_forces_verify_direct(isolated_client):
    """verify must pin the target's library (not lib_default) and force verify_direct."""
    other_lib = _make_library("Second Library")
    target = db.insert_record(
        library_id=other_lib,
        case_id=None,
        status="active",
        problem="target in second library",
        outcome="resolved",
        result_summary="baseline in non-default library",
        payload={"problem": "target in second library", "outcome": "resolved", "result_summary": "x"},
        principal_id="dev:admin",
    )
    target_id = target["record_id"]
    assert other_lib != settings.default_library_id

    mcp = McpClient(isolated_client, api_key="ma3dev")
    verify = mcp.structured(
        "ma3_report",
        {
            "problem": "verification of the target",
            "outcome": "confirmed",
            "result_summary": "replayed the fix, still works",
            "report_kind": "verify",
            "target_record_id": target_id,
            # Client tries to override confirmation and library — server must ignore both.
            "confirmation": "user_confirmed",
            "library_id": settings.default_library_id,
            "evidence": _EVIDENCE,
        },
    )
    assert verify["persisted"] is True
    assert verify["report_kind"] == "verify"
    assert verify["confirmation"] == "verify_direct"
    verify_rec = db.get_record(verify["record_id"])
    assert verify_rec["library_id"] == other_lib
    assert verify_rec["library_id"] != settings.default_library_id
    _assert_audit_row(
        record_id=verify["record_id"],
        principal_id="dev:admin",
        report_kind="verify",
        confirmation="verify_direct",
        library_id=other_lib,
    )


def test_refute_pins_target_library(isolated_client):
    other_lib = _make_library("Refute Target Library")
    target = db.insert_record(
        library_id=other_lib,
        case_id=None,
        status="active",
        problem="target to refute",
        outcome="resolved",
        result_summary="will be refuted",
        payload={"problem": "target to refute", "outcome": "resolved", "result_summary": "x"},
        principal_id="dev:admin",
    )
    mcp = McpClient(isolated_client, api_key="ma3dev")
    refute = mcp.structured(
        "ma3_report",
        {
            "problem": "refutation of the target",
            "outcome": "disproved",
            "result_summary": "does not hold in our environment",
            "report_kind": "refute",
            "target_record_id": target["record_id"],
            "evidence": _EVIDENCE,
        },
    )
    assert refute["report_kind"] == "refute"
    assert refute["confirmation"] == "verify_direct"
    assert db.get_record(refute["record_id"])["library_id"] == other_lib


def test_verify_requires_target_record_id(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "verify without a target",
                "outcome": "confirmed",
                "result_summary": "should fail",
                "report_kind": "verify",
                "evidence": _EVIDENCE,
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32000
    assert "target_record_id" in err["message"]


def test_verify_target_must_be_readable(isolated_client):
    """Verify against an unreadable target returns 404 (no existence leak)."""
    hidden_lib = _make_library("Hidden Library")
    hidden = db.insert_record(
        library_id=hidden_lib,
        case_id=None,
        status="active",
        problem="hidden target",
        outcome="resolved",
        result_summary="unreadable by writer",
        payload={"problem": "hidden target", "outcome": "resolved", "result_summary": "x"},
        principal_id="dev:admin",
    )

    with pytest.MonkeyPatch.context() as mp:
        _writer_keys(mp, "writer-key-a")
        writer = McpClient(isolated_client, api_key="writer-key-a")
        err = writer.rpc(
            "tools/call",
            {
                "name": "ma3_report",
                "arguments": {
                    "problem": "verify unreadable target",
                    "outcome": "confirmed",
                    "result_summary": "should fail",
                    "report_kind": "verify",
                    "target_record_id": hidden["record_id"],
                    "evidence": _EVIDENCE,
                },
            },
            expect_error=True,
        )
    assert err["code"] == -32601


def test_writer_cannot_write_to_unwritable_library(isolated_client, monkeypatch):
    """Explicit library_id the key cannot write is rejected."""
    other_lib = _make_library("Other Org Library")
    _writer_keys(monkeypatch, "writer-key-a")
    writer = McpClient(isolated_client, api_key="writer-key-a")
    err = writer.rpc(
        "tools/call",
        {
            "name": "ma3_report",
            "arguments": {
                "problem": "write to forbidden library",
                "outcome": "resolved",
                "result_summary": "should fail",
                "report_kind": "new",
                "confirmation": "user_confirmed",
                "library_id": other_lib,
                "evidence": _EVIDENCE,
            },
        },
        expect_error=True,
    )
    assert err["code"] == -32001


def test_report_schema_includes_write_audit_fields(isolated_client):
    """Published inputSchema must advertise the new write-audit fields."""
    mcp = McpClient(isolated_client)
    tools = {t["name"]: t for t in mcp.rpc("tools/list")["tools"]}
    schema = tools["ma3_report"]["inputSchema"]["properties"]
    for field in ("report_kind", "confirmation", "target_record_id", "library_id"):
        assert field in schema, f"ma3_report inputSchema missing {field}"


# --------------------------------------------------------------------------- #
# W2: ma3_list_my_writes
# --------------------------------------------------------------------------- #


def test_list_my_writes_returns_own_writes(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    r = mcp.structured(
        "ma3_report",
        {
            "problem": "audited write for list_my_writes",
            "outcome": "resolved",
            "result_summary": "should appear in audit",
            "report_kind": "new",
            "confirmation": "user_confirmed",
            "evidence": _EVIDENCE,
        },
    )
    writes = mcp.structured("ma3_list_my_writes", {})
    entries = writes["writes"]
    hit = next(w for w in entries if w["record_id"] == r["record_id"])
    assert hit["report_kind"] == "new"
    assert hit["confirmation"] == "user_confirmed"
    assert hit["library_id"] == settings.default_library_id
    assert hit["library_name"] == "Community Library"
    assert hit.get("key_prefix")
    assert hit.get("created_at")


def test_list_my_writes_is_principal_scoped(isolated_client, monkeypatch):
    """One principal's writes are not visible in another principal's audit list."""
    _writer_keys(monkeypatch, "writer-a", "writer-b")
    wa = McpClient(isolated_client, api_key="writer-a")
    wb = McpClient(isolated_client, api_key="writer-b")

    ra = wa.structured(
        "ma3_report",
        {
            "problem": "writer a private write",
            "outcome": "resolved",
            "result_summary": "belongs to a",
            "report_kind": "new",
            "confirmation": "agent_judged",
            "evidence": _EVIDENCE,
        },
    )
    b_writes = {w["record_id"] for w in wb.structured("ma3_list_my_writes", {})["writes"]}
    assert ra["record_id"] not in b_writes


def test_list_my_writes_requires_auth(isolated_client):
    anon = McpClient(isolated_client)
    err = anon.rpc("tools/call", {"name": "ma3_list_my_writes", "arguments": {}}, expect_error=True)
    assert err["code"] == -32001


def test_backfill_surfaces_pre_existing_records_in_list_my_writes(isolated_client, monkeypatch):
    """Records written before the audit log existed are attributed to their author."""
    _writer_keys(monkeypatch, "legacy-writer")
    legacy_pid = "writer:key:0"
    row = db.insert_record(
        library_id=settings.default_library_id,
        case_id=None,
        status="active",
        problem="legacy uploaded content before audit log",
        outcome="resolved",
        result_summary="should appear after backfill",
        payload={"problem": "legacy", "outcome": "resolved", "result_summary": "x"},
        principal_id=legacy_pid,
    )
    rid = row["record_id"]
    assert db.get_write_audit_for_record(rid) is None  # no live audit row

    inserted = db.backfill_write_audit_log()
    assert inserted >= 1
    audit = db.get_write_audit_for_record(rid)
    assert audit is not None
    assert audit["principal_id"] == legacy_pid

    writer = McpClient(isolated_client, api_key="legacy-writer")
    writes = writer.structured("ma3_list_my_writes", {})
    assert any(w["record_id"] == rid for w in writes["writes"])


def test_backfill_is_idempotent_and_skips_unattributed(isolated_client):
    """A second backfill adds nothing; records without created_by are skipped."""
    orphan = db.insert_record(
        library_id=settings.default_library_id,
        case_id=None,
        status="active",
        problem="orphan record with no author",
        outcome="resolved",
        result_summary="cannot be attributed",
        payload={"problem": "orphan", "outcome": "resolved", "result_summary": "x"},
        principal_id=None,
    )
    db.backfill_write_audit_log()
    first = db.backfill_write_audit_log()
    assert first == 0  # nothing new on a second pass
    assert db.get_write_audit_for_record(orphan["record_id"]) is None  # no author -> skipped


# --------------------------------------------------------------------------- #
# W3: ma3_delete_record (hard delete, tombstone, lineage, owner ACL)
# --------------------------------------------------------------------------- #


def test_owner_hard_delete_removes_record_and_writes_tombstone(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    r = mcp.structured(
        "ma3_report",
        {
            "problem": "record to be hard deleted unique token xyz789",
            "outcome": "resolved",
            "result_summary": "will be removed",
            "evidence": _EVIDENCE,
        },
    )
    rid = r["record_id"]

    deleted = mcp.structured("ma3_delete_record", {"record_id": rid})
    assert deleted["deleted"] is True
    assert deleted["mode"] == "hard"

    assert db.get_record(rid) is None
    gone = mcp.rpc("tools/call", {"name": "ma3_locate_by_id", "arguments": {"id": rid}}, expect_error=True)
    assert gone["code"] == -32601

    tomb = db.get_record_deletion(rid)
    assert tomb is not None
    assert tomb["deleted_by"] == "dev:admin"
    assert tomb["library_id"] == settings.default_library_id
    assert tomb["deleted_at"]

    ctx = mcp.structured("ma3_context", {"problem": "record to be hard deleted unique token xyz789"})
    assert rid not in _context_record_ids(ctx)


def test_non_owner_cannot_delete(isolated_client, monkeypatch):
    _writer_keys(monkeypatch, "owner-key", "other-key")
    owner = McpClient(isolated_client, api_key="owner-key")
    other = McpClient(isolated_client, api_key="other-key")
    r = owner.structured(
        "ma3_report",
        {
            "problem": "owned by owner-key",
            "outcome": "resolved",
            "result_summary": "only owner may delete",
            "report_kind": "new",
            "confirmation": "agent_judged",
            "evidence": _EVIDENCE,
        },
    )
    rid = r["record_id"]
    err = other.rpc("tools/call", {"name": "ma3_delete_record", "arguments": {"record_id": rid}}, expect_error=True)
    assert err["code"] == -32001
    assert db.get_record(rid) is not None

    ok = owner.structured("ma3_delete_record", {"record_id": rid})
    assert ok["deleted"] is True


def test_delete_missing_record_404(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    err = mcp.rpc(
        "tools/call",
        {"name": "ma3_delete_record", "arguments": {"record_id": "vk_missing"}},
        expect_error=True,
    )
    assert err["code"] == -32601


def test_hard_delete_marks_downstream_lineage_and_warns(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    prior = mcp.structured(
        "ma3_report",
        {
            "problem": "prior source record for lineage delete",
            "outcome": "resolved",
            "result_summary": "will be deleted after being referenced",
            "evidence": _EVIDENCE,
        },
    )
    downstream = mcp.structured(
        "ma3_report",
        {
            "problem": "downstream builds on prior source lineage",
            "outcome": "resolved",
            "result_summary": "depends on prior",
            "based_on_record_ids": [prior["record_id"]],
            "relation_type": "derived_from",
            "evidence": _EVIDENCE,
        },
    )
    assert downstream["relations_written"] == 1
    assert db.get_record(downstream["record_id"]) is not None

    mcp.structured("ma3_delete_record", {"record_id": prior["record_id"]})

    assert db.relation_source_deleted(source_id=downstream["record_id"], target_id=prior["record_id"]) is True

    ctx = mcp.structured("ma3_context", {"problem": "downstream builds on prior source lineage"})
    warning_text = " ".join(ctx["warnings"])
    assert prior["record_id"] in warning_text
    assert "delete" in warning_text.lower()
    assert db.get_record(downstream["record_id"]) is not None  # no cascade delete


# --------------------------------------------------------------------------- #
# W4: library naming
# --------------------------------------------------------------------------- #


def test_whoami_exposes_community_library_name(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    whoami = mcp.structured("ma3_whoami")
    libs = whoami["writable_libraries"]
    default = next(lib for lib in libs if lib["library_id"] == settings.default_library_id)
    assert default["name"] == "Community Library"
    assert default["visibility"] == "public"


def test_context_includes_library_names(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    ctx = mcp.structured("ma3_context", {"problem": "anything"})
    lib_names = {lib["library_id"]: lib["name"] for lib in ctx.get("libraries", [])}
    assert lib_names[settings.default_library_id] == "Community Library"


# --------------------------------------------------------------------------- #
# W5: deletion protection (soft delete + restore)
# --------------------------------------------------------------------------- #


def test_protected_library_soft_deletes_then_restores(isolated_client):
    protected = _make_protected_library(name="Team 库", retention_days=30)
    mcp = McpClient(isolated_client, api_key="ma3dev")
    r = mcp.structured(
        "ma3_report",
        {
            "problem": "record in protected library unique token abc123",
            "outcome": "resolved",
            "result_summary": "soft delete then restore",
            "report_kind": "new",
            "confirmation": "user_confirmed",
            "library_id": protected,
            "evidence": _EVIDENCE,
        },
    )
    rid = r["record_id"]
    assert db.get_record(rid)["library_id"] == protected

    deleted = mcp.structured("ma3_delete_record", {"record_id": rid})
    assert deleted["deleted"] is True
    assert deleted["mode"] == "soft"
    assert db.get_record_deletion(rid) is None  # no tombstone until purge

    rec = db.get_record(rid)
    assert rec is not None
    assert rec["status"] == "trashed"
    ctx = mcp.structured("ma3_context", {"problem": "record in protected library unique token abc123"})
    assert rid not in _context_record_ids(ctx)

    restored = mcp.structured("ma3_restore_record", {"record_id": rid})
    assert restored["restored"] is True
    assert db.get_record(rid)["status"] == "active"


def test_writer_owner_soft_deletes_and_restores_in_protected_library(isolated_client, monkeypatch):
    """Non-admin owner can soft-delete and restore in a protected library."""
    protected = _make_protected_library(name="Team Writer Library")
    _writer_keys(monkeypatch, "owner-writer")
    writer = McpClient(isolated_client, api_key="owner-writer")
    owner_pid = "writer:key:0"
    # Writer keys cannot MCP-write to arbitrary libraries yet; seed ownership directly.
    row = db.insert_record(
        library_id=protected,
        case_id=None,
        status="active",
        problem="writer-owned protected record",
        outcome="resolved",
        result_summary="owner soft delete restore",
        payload={"problem": "writer-owned protected record", "outcome": "resolved", "result_summary": "x"},
        principal_id=owner_pid,
    )
    rid = row["record_id"]
    deleted = writer.structured("ma3_delete_record", {"record_id": rid})
    assert deleted["mode"] == "soft"
    restored = writer.structured("ma3_restore_record", {"record_id": rid})
    assert restored["restored"] is True


def test_non_owner_cannot_restore_trashed_record(isolated_client, monkeypatch):
    protected = _make_protected_library(name="Team ACL Library")
    _writer_keys(monkeypatch, "owner-writer", "other-writer")
    owner = McpClient(isolated_client, api_key="owner-writer")
    other = McpClient(isolated_client, api_key="other-writer")
    row = db.insert_record(
        library_id=protected,
        case_id=None,
        status="active",
        problem="protected record for restore acl",
        outcome="resolved",
        result_summary="only owner restores",
        payload={"problem": "protected record for restore acl", "outcome": "resolved", "result_summary": "x"},
        principal_id="writer:key:0",
    )
    rid = row["record_id"]
    owner.structured("ma3_delete_record", {"record_id": rid})
    err = other.rpc(
        "tools/call",
        {"name": "ma3_restore_record", "arguments": {"record_id": rid}},
        expect_error=True,
    )
    assert err["code"] == -32601  # unreadable library: no existence leak
    assert db.get_record(rid)["status"] == "trashed"


def test_restore_fails_after_retention_window(isolated_client):
    protected = _make_protected_library(name="Team 库 short", retention_days=1)
    mcp = McpClient(isolated_client, api_key="ma3dev")
    r = mcp.structured(
        "ma3_report",
        {
            "problem": "record trashed beyond window",
            "outcome": "resolved",
            "result_summary": "cannot restore after purge window",
            "report_kind": "new",
            "confirmation": "user_confirmed",
            "library_id": protected,
            "evidence": _EVIDENCE,
        },
    )
    rid = r["record_id"]
    mcp.structured("ma3_delete_record", {"record_id": rid})

    stale = (datetime.now(timezone.utc) - timedelta(days=5)).replace(microsecond=0).isoformat()
    db.set_trashed_at(rid, stale)

    err = mcp.rpc(
        "tools/call",
        {"name": "ma3_restore_record", "arguments": {"record_id": rid}},
        expect_error=True,
    )
    assert err["code"] == -32000
    assert "already_purged" in err["message"].lower() or "purged" in err["message"].lower()
    assert db.get_record(rid) is None
    assert db.get_record_deletion(rid) is not None


def test_restore_rejects_non_trashed_record(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    r = mcp.structured(
        "ma3_report",
        {
            "problem": "active record cannot be restored",
            "outcome": "resolved",
            "result_summary": "nothing to restore",
            "evidence": _EVIDENCE,
        },
    )
    err = mcp.rpc(
        "tools/call",
        {"name": "ma3_restore_record", "arguments": {"record_id": r["record_id"]}},
        expect_error=True,
    )
    assert err["code"] == -32000


def test_delete_unreadable_record_is_404_not_403(isolated_client, monkeypatch):
    """Unreadable records must not leak existence via 403 on delete."""
    hidden_lib = _make_library("Hidden Delete Library")
    hidden = db.insert_record(
        library_id=hidden_lib,
        case_id=None,
        status="active",
        problem="hidden from writer delete probe",
        outcome="resolved",
        result_summary="x",
        payload={"problem": "hidden", "outcome": "resolved", "result_summary": "x"},
        principal_id="dev:admin",
    )
    with pytest.MonkeyPatch.context() as mp:
        _writer_keys(mp, "writer-probe")
        writer = McpClient(isolated_client, api_key="writer-probe")
        err = writer.rpc(
            "tools/call",
            {"name": "ma3_delete_record", "arguments": {"record_id": hidden["record_id"]}},
            expect_error=True,
        )
    assert err["code"] == -32601


def test_unprotected_library_hard_deletes_even_with_owner(isolated_client):
    """Default/free/personal/public libraries always hard-delete (no recycle bin)."""
    mcp = McpClient(isolated_client, api_key="ma3dev")
    r = mcp.structured(
        "ma3_report",
        {
            "problem": "default library record hard delete",
            "outcome": "resolved",
            "result_summary": "no protection means irreversible",
            "evidence": _EVIDENCE,
        },
    )
    rid = r["record_id"]
    deleted = mcp.structured("ma3_delete_record", {"record_id": rid})
    assert deleted["mode"] == "hard"
    assert db.get_record(rid) is None
