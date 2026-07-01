from __future__ import annotations

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
    Ma3DoctorPayload,
    Ma3ListDraftsPayload,
    Ma3ReportPayload,
    Ma3ReviewRecordPayload,
    Ma3SearchExplainPayload,
    Ma3ValidatePayload,
    Ma3WhoamiPayload,
    PAYLOAD_BY_TOOL,
    tool_input_schema,
)
from app.services.mcp_server_info import attach_server_block, extract_client_report
from app.services.client_bundle import ClientReport
from app.storage import db
from app.storage.db import is_postgres

MCP_PROTOCOL_VERSION = settings.protocol_version
MCP_TOOL_SCHEMA_VERSION = settings.tool_schema_version

_TOOL_ORDER = (
    "ma3_context",
    "ma3_case",
    "ma3_search_explain",
    "ma3_report",
    "ma3_validate",
    "ma3_doctor",
    "ma3_whoami",
    "ma3_list_drafts",
    "ma3_review_record",
)

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "ma3_context": "Retrieve compact prior ma3 knowledge for the current task. Required: problem.",
    "ma3_report": "Write verified agent outcome; default status active. Required: problem, outcome, result_summary.",
    "ma3_case": "Read one case timeline. Required: case_id.",
    "ma3_search_explain": "Search with ranking explain. Required: problem.",
    "ma3_doctor": "Server, auth, and index diagnostics.",
    "ma3_whoami": "Caller identity and library visibility.",
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


def _result(structured: dict[str, Any], *, client_report: ClientReport | None = None, summary: str) -> McpToolResult:
    return McpToolResult(
        content=[{"type": "text", "text": summary}],
        structuredContent=attach_server_block(structured, client_report=client_report),
    )


def _coerce_target(payload: Ma3ContextPayload | Ma3ReportPayload) -> TargetRef | None:
    if payload.target:
        return payload.target
    if payload.target_product:
        return TargetRef(product=payload.target_product, component=payload.target_component)
    return None


def _context_payload(auth: McpAuthContext, payload: Ma3ContextPayload, *, explain: bool) -> dict[str, Any]:
    lib_ids = auth.readable_library_ids
    hits = db.search_records(lib_ids, payload.problem, limit=payload.max_cases * payload.max_records_per_case)
    cases: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        cid = hit.get("case_id") or "ungrouped"
        cases.setdefault(cid, []).append(hit)
    grouped = [
        {"case_id": cid, "records": recs[: payload.max_records_per_case]}
        for cid, recs in list(cases.items())[: payload.max_cases]
    ]
    body: dict[str, Any] = {
        "cases": grouped,
        "ungrouped_records": cases.get("ungrouped", []),
        "warnings": [] if hits else ["no matching active records"],
        "library_ids": sorted(lib_ids),
    }
    if explain:
        body["explain"] = {"mode": "skeleton", "hits": len(hits), "note": "FTS-like LIKE search in v1 skeleton"}
    return body


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
        structured = {
            "status": "ok",
            "service_version": settings.service_version,
            "records": db.count_records(),
            "embeddings_enabled": not settings.disable_embeddings,
            "database": "postgresql" if is_postgres() else "sqlite",
            "tools": [t.name for t in list_mcp_tools()],
        }
        return _result(structured, client_report=client_report, summary=f"ma3 doctor: {structured['status']}")

    if name == "ma3_whoami":
        structured = {
            "caller": auth.caller_summary,
            "readable_library_ids": sorted(auth.readable_library_ids),
            "writable_library_ids": sorted(auth.writable_library_ids),
            "maintainer_library_ids": sorted(auth.maintainer_library_ids),
        }
        return _result(structured, client_report=client_report, summary=json.dumps(structured["caller"]))

    if name == "ma3_context":
        assert isinstance(payload, Ma3ContextPayload)
        body = _context_payload(auth, payload, explain=payload.include_explain)
        return _result(body, client_report=client_report, summary=f"{len(body['cases'])} cases")

    if name == "ma3_search_explain":
        assert isinstance(payload, Ma3SearchExplainPayload)
        body = _context_payload(auth, payload, explain=True)
        return _result(body, client_report=client_report, summary="search explain")

    if name == "ma3_case":
        assert isinstance(payload, Ma3CasePayload)
        case = db.get_case(payload.case_id)
        if not case:
            raise HTTPException(status_code=404, detail="case not found")
        return _result({"case": case}, client_report=client_report, summary=case["title"])

    if name == "ma3_list_drafts":
        assert isinstance(payload, Ma3ListDraftsPayload)
        if payload.library_id not in auth.maintainer_library_ids:
            raise HTTPException(status_code=403, detail="maintainer access required")
        drafts = db.list_drafts(payload.library_id, payload.limit, payload.offset)
        return _result({"drafts": drafts, "count": len(drafts)}, client_report=client_report, summary=f"{len(drafts)} drafts")

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
            new_status = "active"
        else:
            new_status = "invalid"
        updated = db.set_record_status(payload.record_id, new_status)
        structured = {
            "record_id": payload.record_id,
            "decision": payload.decision,
            "old_status": old_status,
            "new_status": new_status,
            "review_note": payload.review_note,
            "record": updated,
        }
        return _result(structured, client_report=client_report, summary=f"{old_status} -> {new_status}")

    if name == "ma3_report":
        assert isinstance(payload, Ma3ReportPayload)
        if not auth.writable_library_ids:
            raise HTTPException(status_code=403, detail="writer access required")
        library_id = settings.default_library_id
        status = "draft" if payload.visibility == "draft" else "active"
        if payload.dry_run:
            structured = {"persisted": False, "dry_run": True, "status": status}
            return _result(structured, client_report=client_report, summary="dry run")
        case_id = payload.case_id
        if payload.case_assignment_mode == "auto" and not case_id:
            case_id = db.get_or_create_case(library_id, payload.problem[:120])
        row = db.insert_record(
            library_id=library_id,
            case_id=case_id,
            status=status,
            problem=payload.problem,
            outcome=payload.outcome,
            result_summary=payload.result_summary,
            payload=payload.model_dump(mode="json"),
        )
        structured = {
            "persisted": True,
            "record_id": row["record_id"],
            "status": status,
            "case_assignment": {"case_id": case_id, "mode": payload.case_assignment_mode},
        }
        return _result(structured, client_report=client_report, summary=f"record {row['record_id']} {status}")

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
