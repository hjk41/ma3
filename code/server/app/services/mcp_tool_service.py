from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import McpAuthContext, resolve_mcp_auth
from app.models.common import TargetRef
from app.models.mcp import McpToolDescriptor, McpToolResult, McpToolValidationError
from app.models.mcp_payloads import (
    Ma3CasePayload,
    Ma3ContextPayload,
    Ma3DeleteRecordPayload,
    Ma3DoctorPayload,
    Ma3FeedbackPayload,
    Ma3ListDraftsPayload,
    Ma3ListMyWritesPayload,
    Ma3LocateByIdPayload,
    Ma3ReportPayload,
    Ma3RestoreRecordPayload,
    Ma3ReviewRecordPayload,
    Ma3ValidatePayload,
    Ma3WhoamiPayload,
    PAYLOAD_BY_TOOL,
    tool_input_schema,
)
from app.services.mcp_server_info import attach_server_block, extract_client_report
from app.services.client_bundle import ClientReport
from app.services.feedback_service import apply_record_feedback, attach_feedback_to_records, resolve_mcp_feedback_principal
from app.services.record_read_service import applicability_warnings, format_records_for_read, lineage_warnings
from app.services.redaction_service import redact_payload
from app.services.report_store_service import storage_payload, validate_report_write
from app.services.write_audit_service import (
    append_write_audit,
    delete_record_for_owner,
    format_my_writes,
    resolve_report_write_plan,
    restore_record_for_caller,
)
from app.services.search_context_service import SearchContext
from app.storage import db
from app.storage.db import is_postgres

MCP_PROTOCOL_VERSION = settings.protocol_version
MCP_TOOL_SCHEMA_VERSION = settings.tool_schema_version

_TOOL_ORDER = (
    "ma3_context",
    "ma3_case",
    "ma3_locate_by_id",
    "ma3_report",
    "ma3_list_my_writes",
    "ma3_delete_record",
    "ma3_restore_record",
    "ma3_validate",
    "ma3_doctor",
    "ma3_whoami",
    "ma3_feedback",
    "ma3_list_drafts",
    "ma3_review_record",
)

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "ma3_context": "Retrieve compact prior ma3 knowledge for the current task. Required: problem.",
    "ma3_report": "Write verified agent outcome; default status active. Required: problem, outcome, result_summary.",
    "ma3_list_my_writes": "List the caller's write audit history. Optional: limit, offset.",
    "ma3_delete_record": "Owner delete a record (hard by default; soft when library has deletion protection). Required: record_id.",
    "ma3_restore_record": "Restore a trashed record in a deletion-protected library. Required: record_id.",
    "ma3_case": "Read one case timeline. Required: case_id.",
    "ma3_locate_by_id": "Fetch a single record (vk_...) or case (cs_...) by its id. Required: id.",
    "ma3_doctor": "Server, auth, and index diagnostics.",
    "ma3_whoami": "Caller identity and library visibility.",
    "ma3_feedback": "Thumbs up/down on an active record. Required: record_id, vote (up|down|clear).",
    "ma3_list_drafts": "List draft records in a library. Required: library_id.",
    "ma3_review_record": "Approve/reject draft or mark invalid (maintainer). Required: record_id, decision, review_note.",
    "ma3_validate": "Dry-run validate another tool payload. Required: tool_name, arguments.",
}


def list_mcp_tools() -> list[McpToolDescriptor]:
    return [
        McpToolDescriptor(
            name=name,
            description=_TOOL_DESCRIPTIONS[name],
            inputSchema=tool_input_schema(name),
        )
        for name in _TOOL_ORDER
    ]


def _validate_args(tool_name: str, arguments: dict[str, Any]) -> Any:
    model = PAYLOAD_BY_TOOL.get(tool_name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        raise McpToolValidationError(tool_name, exc.errors()) from exc


def _render_body_text(structured: dict[str, Any]) -> str:
    """Render the structured body as readable text for the content block.

    MCP hosts are only guaranteed to surface ``content[].text`` to the model;
    ``structuredContent`` may be dropped. So we mirror the full (already
    redacted) body here as pretty JSON so any client can read it.
    """
    try:
        return json.dumps(structured, ensure_ascii=False, indent=2, sort_keys=False)
    except (TypeError, ValueError):
        return str(structured)


def _result(structured: dict[str, Any], *, client_report: ClientReport | None = None, summary: str) -> McpToolResult:
    body_text = _render_body_text(structured)
    text = f"{summary}\n\n{body_text}" if body_text else summary
    return McpToolResult(
        content=[{"type": "text", "text": text}],
        structuredContent=attach_server_block(structured, client_report=client_report),
    )


def _coerce_target(payload: Ma3ContextPayload | Ma3ReportPayload) -> TargetRef | None:
    if payload.target:
        return payload.target
    if payload.target_product:
        return TargetRef(product=payload.target_product, component=payload.target_component)
    return None


def _search_context(payload: Ma3ContextPayload) -> SearchContext:
    target = _coerce_target(payload)
    env = payload.environment.model_dump(exclude_none=True) if payload.environment else None
    return SearchContext(
        task_type=payload.task_type,
        target_product=target.product if target else payload.target_product,
        target_component=target.component if target else payload.target_component,
        tags=list(payload.tags),
        environment=env,
    )


def _context_payload(auth: McpAuthContext, payload: Ma3ContextPayload, *, explain: bool) -> dict[str, Any]:
    lib_ids = auth.readable_library_ids
    limit = payload.max_cases * payload.max_records_per_case
    hits, rank_explain = db.search_records(
        lib_ids,
        payload.problem,
        limit=limit,
        explain=explain,
        context=_search_context(payload),
    )
    principal_id = None if auth.principal.kind == "anonymous" else auth.principal.principal_id
    hits = attach_feedback_to_records(hits, principal_id=principal_id)
    env_dict = payload.environment.model_dump(exclude_none=True) if payload.environment else None
    warnings: list[str] = [] if hits else ["no matching active records"]
    warnings.extend(applicability_warnings(hits, env_dict))
    warnings.extend(lineage_warnings(hits))
    record_ids = [str(h["id"]) for h in hits if h.get("id")]
    relations = db.get_record_relations(record_ids, readable_library_ids=lib_ids)
    hits = format_records_for_read(
        hits,
        include_full_json=payload.include_full_json,
        relations=relations,
    )
    cases: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        cid = hit.get("case_id") or "ungrouped"
        if cid == "ungrouped":
            continue
        cases.setdefault(cid, []).append(hit)
    grouped = [
        {"case_id": cid, "records": recs[: payload.max_records_per_case]}
        for cid, recs in list(cases.items())[: payload.max_cases]
    ]
    ungrouped = [h for h in hits if not h.get("case_id")][: payload.max_records_per_case]
    body: dict[str, Any] = {
        "cases": grouped,
        "ungrouped_records": ungrouped,
        "warnings": warnings,
        "library_ids": sorted(lib_ids),
        "libraries": db.list_libraries(lib_ids),
    }
    if explain:
        mode = "like" if settings.disable_embeddings else (
            "hybrid_fts_pgvector" if is_postgres() and db.pgvector_ready() else (
                "hybrid_fts_vector" if is_postgres() else "vector_like"
            )
        )
        active_count = db.count_active_records(lib_ids)
        body["explain"] = {
            "mode": mode,
            "hits": len(hits),
            "embeddings_enabled": not settings.disable_embeddings,
            "records": rank_explain,
            "vector_scan_limit": settings.vector_scan_limit,
            "active_records": active_count,
            "vector_scan_truncated": active_count > settings.vector_scan_limit,
        }
    return body


def _caller_principal_id(auth: McpAuthContext) -> str | None:
    return None if auth.principal.kind == "anonymous" else auth.principal.principal_id


def _record_visible(record: dict[str, Any], auth: McpAuthContext, caller_principal_id: str | None) -> bool:
    """Read visibility for a single record.

    Active records in a readable library are visible to everyone with read
    access. Non-active (draft/invalid) records are visible only to the library
    maintainer, an admin bypass, or the record's own author (``created_by``).
    """
    lib = record.get("library_id")
    if lib not in auth.readable_library_ids:
        return False
    if record.get("status") == "active":
        return True
    if record.get("status") == "trashed":
        if auth.principal.is_admin_bypass:
            return True
        if lib in auth.maintainer_library_ids:
            return True
        if caller_principal_id is not None and record.get("created_by") == caller_principal_id:
            return True
        return False
    if auth.principal.is_admin_bypass:
        return True
    if lib in auth.maintainer_library_ids:
        return True
    if caller_principal_id is not None and record.get("created_by") == caller_principal_id:
        return True
    return False


def call_mcp_tool(name: str, arguments: dict[str, Any], auth: McpAuthContext) -> McpToolResult:
    raw_args, client_report = extract_client_report(arguments)
    payload = _validate_args(name, raw_args)

    if name == "ma3_validate":
        assert isinstance(payload, Ma3ValidatePayload)
        if payload.arguments is None:
            return _result({"ok": False, "error": "missing_arguments"}, client_report=client_report, summary="missing arguments")
        try:
            _validate_args(payload.tool_name, payload.arguments)
        except McpToolValidationError as exc:
            return _result(
                {"ok": False, "tool_name": payload.tool_name, "validation_errors": exc.errors},
                client_report=client_report,
                summary="validation failed",
            )
        return _result({"ok": True, "tool_name": payload.tool_name}, client_report=client_report, summary="ok")

    if name == "ma3_doctor":
        lib_ids = auth.readable_library_ids
        active_count = db.count_active_records(lib_ids)
        structured = {
            "status": "ok",
            "service_version": settings.service_version,
            "records": db.count_records(),
            "active_records": active_count,
            "embeddings_enabled": not settings.disable_embeddings,
            "embeddings_indexed": db.count_embeddings(),
            "search_mode": (
                "hybrid_fts_pgvector"
                if not settings.disable_embeddings and is_postgres() and db.pgvector_ready()
                else ("hybrid_fts_vector" if not settings.disable_embeddings and is_postgres() else "like")
            ),
            "database": "postgresql" if is_postgres() else "sqlite",
            "vector_scan_limit": settings.vector_scan_limit,
            "vector_scan_truncated": active_count > settings.vector_scan_limit if not db.pgvector_ready() else False,
            "pgvector_ready": db.pgvector_ready(),
            "dev_auth_enabled": settings.dev_auth,
            "tools": [t.name for t in list_mcp_tools()],
        }
        return _result(structured, client_report=client_report, summary=f"ma3 doctor: {structured['status']}")

    if name == "ma3_whoami":
        writable = db.list_libraries(auth.writable_library_ids)
        readable = db.list_libraries(auth.readable_library_ids)
        structured = {
            "caller": auth.caller_summary,
            "readable_library_ids": sorted(auth.readable_library_ids),
            "writable_library_ids": sorted(auth.writable_library_ids),
            "maintainer_library_ids": sorted(auth.maintainer_library_ids),
            "writable_libraries": writable,
            "readable_libraries": readable,
        }
        return _result(structured, client_report=client_report, summary=json.dumps(structured["caller"]))

    if name == "ma3_context":
        assert isinstance(payload, Ma3ContextPayload)
        body = _context_payload(auth, payload, explain=False)
        return _result(body, client_report=client_report, summary=f"{len(body['cases'])} cases")

    if name == "ma3_case":
        assert isinstance(payload, Ma3CasePayload)
        case = db.get_case(
            payload.case_id,
            library_ids=auth.readable_library_ids,
            active_only=False,
            include_payload=True,
        )
        if not case:
            raise HTTPException(status_code=404, detail="case not found")
        principal_id = _caller_principal_id(auth)
        case["records"] = [r for r in case["records"] if _record_visible(r, auth, principal_id)]
        record_ids = [str(r["id"]) for r in case["records"] if r.get("id")]
        relations = db.get_record_relations(record_ids, readable_library_ids=auth.readable_library_ids)
        case["records"] = attach_feedback_to_records(case["records"], principal_id=principal_id)
        case["records"] = format_records_for_read(
            case["records"],
            include_full_json=payload.include_full_json,
            relations=relations,
        )
        return _result({"case": case}, client_report=client_report, summary=case["title"])

    if name == "ma3_locate_by_id":
        assert isinstance(payload, Ma3LocateByIdPayload)
        caller_pid = _caller_principal_id(auth)
        the_id = payload.id

        record = db.get_record(the_id)
        if record is not None:
            if not _record_visible(record, auth, caller_pid):
                raise HTTPException(status_code=404, detail="not found")
            relations = db.get_record_relations([the_id], readable_library_ids=auth.readable_library_ids)
            record = attach_feedback_to_records([record], principal_id=caller_pid)[0]
            formatted = format_records_for_read(
                [record],
                include_full_json=payload.include_full_json,
                relations=relations,
            )[0]
            return _result({"kind": "record", "record": formatted}, client_report=client_report, summary=f"record {the_id}")

        case = db.get_case(
            the_id,
            library_ids=auth.readable_library_ids,
            active_only=False,
            include_payload=True,
        )
        if case is not None:
            case["records"] = [r for r in case["records"] if _record_visible(r, auth, caller_pid)]
            record_ids = [str(r["id"]) for r in case["records"] if r.get("id")]
            relations = db.get_record_relations(record_ids, readable_library_ids=auth.readable_library_ids)
            case["records"] = attach_feedback_to_records(case["records"], principal_id=caller_pid)
            case["records"] = format_records_for_read(
                case["records"],
                include_full_json=payload.include_full_json,
                relations=relations,
            )
            return _result({"kind": "case", "case": case}, client_report=client_report, summary=case.get("title", the_id))

        raise HTTPException(status_code=404, detail="not found")

    if name == "ma3_feedback":
        assert isinstance(payload, Ma3FeedbackPayload)
        principal_id = resolve_mcp_feedback_principal(auth)
        structured = apply_record_feedback(
            record_id=payload.record_id,
            principal_id=principal_id,
            vote=payload.vote,
            readable_library_ids=auth.readable_library_ids,
        )
        return _result(structured, client_report=client_report, summary=f"{payload.vote} on {payload.record_id}")

    if name == "ma3_list_drafts":
        assert isinstance(payload, Ma3ListDraftsPayload)
        if payload.library_id not in auth.maintainer_library_ids:
            raise HTTPException(status_code=403, detail="maintainer access required")
        drafts = db.list_drafts(payload.library_id, payload.limit, payload.offset, include_payload=True)
        safe_drafts = format_records_for_read(
            drafts,
            include_full_json=payload.include_full_json,
        )
        return _result({"drafts": safe_drafts, "count": len(safe_drafts)}, client_report=client_report, summary=f"{len(safe_drafts)} drafts")

    if name == "ma3_review_record":
        assert isinstance(payload, Ma3ReviewRecordPayload)
        record = db.get_record(payload.record_id)
        if not record:
            raise HTTPException(status_code=404, detail="record not found")
        if record["library_id"] not in auth.maintainer_library_ids:
            raise HTTPException(status_code=403, detail="maintainer access required")
        old_status = record["status"]
        if payload.decision == "approve":
            if old_status != "draft":
                raise HTTPException(status_code=400, detail="only draft records can be approved")
            pl = record.get("payload") or {}
            if not isinstance(pl, dict):
                pl = {}
            if not pl.get("evidence") and not pl.get("actions"):
                raise HTTPException(status_code=400, detail="cannot approve draft without evidence or actions")
            based_on = pl.get("based_on_record_ids") or []
            if isinstance(based_on, list):
                for ref_id in based_on:
                    ref = db.get_record(str(ref_id))
                    if not ref or ref.get("status") != "active":
                        raise HTTPException(status_code=400, detail=f"based_on record must be active at approval: {ref_id}")
            new_status = "active"
        else:
            new_status = "invalid"
        updated = db.set_record_status(payload.record_id, new_status)
        if payload.decision == "approve" and updated:
            pl = updated.get("payload") or {}
            based_on = pl.get("based_on_record_ids") if isinstance(pl, dict) else []
            if isinstance(based_on, list) and based_on:
                db.insert_record_relations(
                    source_id=payload.record_id,
                    based_on_record_ids=[str(rid) for rid in based_on],
                    relation_type=pl.get("relation_type") if isinstance(pl, dict) else None,
                )
        safe_record = None
        if updated:
            safe_record = format_records_for_read([updated], include_full_json=False)[0]
        if new_status == "invalid":
            db.delete_record_relations_for_source(payload.record_id)
        structured = {
            "record_id": payload.record_id,
            "decision": payload.decision,
            "old_status": old_status,
            "new_status": new_status,
            "review_note": payload.review_note,
            "record": safe_record or updated,
        }
        return _result(structured, client_report=client_report, summary=f"{old_status} -> {new_status}")

    if name == "ma3_report":
        assert isinstance(payload, Ma3ReportPayload)
        if not auth.writable_library_ids:
            raise HTTPException(status_code=403, detail="writer access required")
        write_plan = resolve_report_write_plan(payload, auth)
        library_id = write_plan.library_id
        is_maintainer = auth.principal.is_admin_bypass or library_id in auth.maintainer_library_ids
        status = "draft" if payload.visibility == "draft" else "active"
        if payload.dry_run:
            structured = {
                "persisted": False,
                "dry_run": True,
                "status": status,
                "report_kind": write_plan.report_kind,
                "confirmation": write_plan.confirmation,
                "library_id": library_id,
            }
            return _result(structured, client_report=client_report, summary="dry run")
        validate_report_write(payload, is_maintainer=is_maintainer)
        for ref_id in payload.based_on_record_ids:
            ref = db.get_record(ref_id)
            if not ref or ref.get("library_id") not in auth.readable_library_ids:
                raise HTTPException(status_code=400, detail=f"based_on record not readable: {ref_id}")
            if ref.get("status") != "active":
                raise HTTPException(status_code=400, detail=f"based_on record must be active: {ref_id}")
        dump = storage_payload(payload.model_dump(mode="json"))
        dump["report_kind"] = write_plan.report_kind
        dump["confirmation"] = write_plan.confirmation
        if payload.redaction_mode == "auto":
            dump = redact_payload(dump)
        case_id = payload.case_id
        if payload.case_assignment_mode == "manual":
            case_id = None
        elif payload.case_assignment_mode == "force":
            if not case_id:
                raise HTTPException(status_code=400, detail="case_id required for case_assignment_mode=force")
            forced = db.get_case(case_id, library_ids={library_id}, active_only=False, include_payload=False)
            if not forced:
                raise HTTPException(status_code=400, detail=f"case not found in writable library: {case_id}")
        elif payload.case_assignment_mode == "auto" and not case_id:
            case_id = db.get_or_create_case(library_id, str(dump["problem"])[:120])
        elif case_id:
            existing = db.get_case(case_id, library_ids={library_id}, active_only=False, include_payload=False)
            if not existing:
                raise HTTPException(status_code=400, detail=f"case not found in writable library: {case_id}")
        payload_hash: str | None = None
        if payload.idempotency_key:
            hash_material = {**dump, "_visibility": payload.visibility}
            payload_hash = hashlib.sha256(json.dumps(hash_material, sort_keys=True).encode()).hexdigest()
            existing = db.get_idempotent_report(payload.idempotency_key, auth.principal.principal_id)
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise HTTPException(status_code=409, detail="idempotency_key reused with different payload")
                db.sync_record_search_index(existing["record_id"])
                record = db.get_record(existing["record_id"])
                audit = db.get_write_audit_for_record(existing["record_id"])
                structured = {
                    "persisted": True,
                    "record_id": existing["record_id"],
                    "status": record["status"] if record else status,
                    "case_assignment": {"case_id": record.get("case_id") if record else case_id, "mode": payload.case_assignment_mode},
                    "relations_written": 0,
                    "redaction_mode": payload.redaction_mode,
                    "idempotent_replay": True,
                    "report_kind": audit["report_kind"] if audit else write_plan.report_kind,
                    "confirmation": audit["confirmation"] if audit else write_plan.confirmation,
                    "library_id": library_id,
                }
                return _result(structured, client_report=client_report, summary=f"record {existing['record_id']} replay")
        row = db.insert_record(
            library_id=library_id,
            case_id=case_id,
            status=status,
            problem=str(dump["problem"]),
            outcome=str(dump["outcome"]),
            result_summary=str(dump["result_summary"]),
            payload=dump,
            idempotency_key=payload.idempotency_key,
            principal_id=auth.principal.principal_id,
            payload_hash=payload_hash,
        )
        if status == "active" and not row.get("idempotent_replay"):
            db.insert_record_relations(
                source_id=row["record_id"],
                based_on_record_ids=payload.based_on_record_ids,
                relation_type=payload.relation_type,
            )
        replay = bool(row.get("idempotent_replay"))
        if not replay:
            append_write_audit(
                record_id=row["record_id"],
                library_id=library_id,
                auth=auth,
                report_kind=write_plan.report_kind,
                confirmation=write_plan.confirmation,
            )
        resp_status = row["status"] if replay else status
        resp_case_id = row.get("case_id") if replay else case_id
        structured = {
            "persisted": True,
            "record_id": row["record_id"],
            "status": resp_status,
            "case_assignment": {"case_id": resp_case_id, "mode": payload.case_assignment_mode},
            "relations_written": len(payload.based_on_record_ids) if status == "active" and not replay else 0,
            "redaction_mode": payload.redaction_mode,
            "idempotent_replay": replay,
            "report_kind": write_plan.report_kind,
            "confirmation": write_plan.confirmation,
            "library_id": library_id,
        }
        return _result(structured, client_report=client_report, summary=f"record {row['record_id']} {status}")

    if name == "ma3_list_my_writes":
        assert isinstance(payload, Ma3ListMyWritesPayload)
        if auth.principal.kind == "anonymous":
            raise HTTPException(status_code=403, detail="authentication required")
        rows = db.list_write_audit_for_principal(
            auth.principal.principal_id,
            limit=payload.limit,
            offset=payload.offset,
        )
        writes = format_my_writes(rows, key_prefix=auth.key_prefix)
        return _result({"writes": writes, "count": len(writes)}, client_report=client_report, summary=f"{len(writes)} writes")

    if name == "ma3_delete_record":
        assert isinstance(payload, Ma3DeleteRecordPayload)
        structured = delete_record_for_owner(record_id=payload.record_id, auth=auth)
        return _result(structured, client_report=client_report, summary=f"deleted {payload.record_id}")

    if name == "ma3_restore_record":
        assert isinstance(payload, Ma3RestoreRecordPayload)
        structured = restore_record_for_caller(record_id=payload.record_id, auth=auth)
        return _result(structured, client_report=client_report, summary=f"restored {payload.record_id}")

    raise HTTPException(status_code=404, detail=f"unknown tool: {name}")


def mcp_initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": "ma3-remote-mcp",
            "version": settings.service_version,
            "skill_bundle_version": settings.skill_version,
            "min_client_version": settings.min_client_version,
            "recommended_client_version": settings.recommended_client_version,
        },
        "instructions": (
            "Use ma3_context before non-trivial work; ma3_report after verified outcomes. "
            "Pass client_version when known. Use ma3_validate before writes."
        ),
    }
