from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import ResolvedPrincipal, _resolve_from_raw_only, effective_libraries, primary_write_library_id
from app.models.common import TargetRef
from app.models.enums import RecordStatus
from app.models.mcp import McpToolDescriptor, McpToolResult, McpToolValidationError
from app.models.mcp_payloads import PAYLOAD_BY_TOOL, tool_input_schema
from app.models.v2 import V2AgentContextRequest, V2AgentReportRequest, V2CaseRecordGroup
from app.services.doctor_service import server_doctor
from app.services.library_service import effective_library_ids
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.services.record_service import promote_record, reject_record
from app.services.v2_agent_service import ingest_v2_agent_report
from app.services.v2_search_service import build_agent_context
from app.storage.repositories import LibraryRepository, RecordRepository
from app.storage.v2_repositories import CaseRepository, V2GraphRepository, V2RecordRepository


MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_TOOL_SCHEMA_VERSION = "ma3.mcp.v1"


@dataclass(slots=True)
class McpAuthContext:
    raw_present: bool
    principal: ResolvedPrincipal

    @property
    def readable_library_ids(self) -> set[str]:
        return effective_library_ids(self.principal)

    @property
    def writable_library_ids(self) -> set[str]:
        return set(effective_libraries(self.principal, role_at_least="writer"))

    @property
    def caller_summary(self) -> dict[str, Any]:
        if self.principal.is_admin_bypass:
            return {
                "type": "admin",
                "principal_id": self.principal.principal_id,
                "kind": self.principal.kind,
                "via": self.principal.via,
            }
        if self.principal.kind == "legacy":
            return {
                "type": "library_token",
                "principal_id": self.principal.principal_id,
                "kind": self.principal.kind,
                "via": self.principal.via,
                "token_id": self.principal.token_id,
                "library_id": self.principal.library_id,
                "role": self.principal.role,
                "label": self.principal.label,
            }
        if self.principal.kind != "anonymous":
            return {
                "type": self.principal.kind,
                "principal_id": self.principal.principal_id,
                "kind": self.principal.kind,
                "via": self.principal.via,
                "api_key_id": self.principal.api_key_id,
                "label": self.principal.display_name,
            }
        return {"type": "anonymous", "principal_id": self.principal.principal_id, "kind": "anonymous", "via": "anonymous"}


def resolve_mcp_auth(raw: str | None) -> McpAuthContext:
    principal = _resolve_from_raw_only(raw)
    return McpAuthContext(raw_present=bool(raw), principal=principal)


_TOOL_DESCRIPTIONS: dict[str, str] = {
    "ma3_context": (
        "Return agent-ready ma3 context for a task: matched cases, records, warnings, "
        "and optional explain data. Inputs are validated against the Ma3ContextPayload "
        "Pydantic model — invalid arguments fail with -32602 and a structured "
        "error.data.validation_errors list."
    ),
    "ma3_report": (
        "Write back an agent outcome to ma3 and assign it to a case. Inputs are "
        "validated against the Ma3ReportPayload Pydantic model; see "
        "inputSchema.$defs.AgentAction for the exact item shape of `actions` and "
        "inputSchema.$defs.EvidenceItem for `evidence`. Use ma3_validate first for "
        "dry-run validation without consuming write quota."
    ),
    "ma3_case": "Read one ma3 case timeline with records and relations visible to the caller.",
    "ma3_search_explain": (
        "Diagnostic ma3 search that always includes ranking/candidate explain data. "
        "Same input shape as ma3_context."
    ),
    "ma3_doctor": "Diagnose remote MCP authentication, server health, version, database, and index state.",
    "ma3_whoami": "Return the caller identity and visible library summary without exposing token material.",
    "ma3_list_drafts": (
        "List pending-review draft records for one library visible to the caller. "
        "Requires writer-or-higher access to the library."
    ),
    "ma3_review_record": (
        "Approve or reject one draft record. Requires library-admin or global-admin "
        "rights for the record's library."
    ),
    "ma3_validate": (
        "Dry-run validator. Returns {ok: true} when `arguments` would pass Pydantic "
        "validation for `tool_name`, or the same structured validation_errors list "
        "that a real call would emit. Cheap, never persists, and ideal for an agent "
        "retry loop that wants to confirm payload shape before consuming write quota."
    ),
}


_TOOL_ORDER: tuple[str, ...] = (
    "ma3_context",
    "ma3_report",
    "ma3_case",
    "ma3_search_explain",
    "ma3_list_drafts",
    "ma3_review_record",
    "ma3_validate",
    "ma3_doctor",
    "ma3_whoami",
)


def list_mcp_tools() -> list[McpToolDescriptor]:
    return [
        McpToolDescriptor(
            name=name,
            description=_TOOL_DESCRIPTIONS[name],
            inputSchema=tool_input_schema(name),
        )
        for name in _TOOL_ORDER
        if name in PAYLOAD_BY_TOOL
    ]


def _validate_args(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run the tool's Pydantic payload validator and return the cleaned dict.

    On failure, raise ``McpToolValidationError`` carrying the structured
    Pydantic errors list so the route layer can attach it to error.data.
    """

    model = PAYLOAD_BY_TOOL.get(tool_name)
    if model is None:
        raise HTTPException(status_code=404, detail="tool_not_found")
    try:
        validated = model.model_validate(arguments)
    except ValidationError as exc:
        raise McpToolValidationError(tool_name, exc.errors()) from exc
    return validated.model_dump(mode="python")


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _tool_result(summary: str, structured: dict[str, Any], include_full_json: bool = False) -> McpToolResult:
    content = [{"type": "text", "text": summary}]
    if include_full_json:
        content.append({"type": "text", "text": _json_text(structured)})
    return McpToolResult(content=content, structuredContent=structured)


def _target(args: dict[str, Any]) -> dict[str, Any]:
    target = args.get("target")
    if isinstance(target, dict) and target.get("product"):
        return target
    product = args.get("target_product") or args.get("product") or "unknown"
    component = args.get("target_component") or args.get("component")
    out = {"product": product}
    if component:
        out["component"] = component
    return out


def _context_request(args: dict[str, Any], *, explain: bool = False) -> V2AgentContextRequest:
    problem = args.get("problem") or args.get("query") or ""
    if not str(problem).strip():
        raise ValueError("problem is required")
    payload = {
        "problem": problem,
        "task_type": args.get("task_type") or "general",
        "goal": args.get("goal") or args.get("problem") or "find relevant ma3 knowledge",
        "target": _target(args),
        "environment": args.get("environment"),
        "versions": args.get("versions"),
        "observations": args.get("observations") or [],
        "constraints": args.get("constraints") or [],
        "tags": args.get("tags") or [],
        "max_cases": args.get("max_cases", 3),
        "max_records_per_case": args.get("max_records_per_case", 3),
        "include_explain": bool(args.get("include_explain") or explain),
    }
    return V2AgentContextRequest.model_validate(payload)


def _report_request(args: dict[str, Any]) -> V2AgentReportRequest:
    problem = args.get("problem") or ""
    result_summary = args.get("result_summary") or args.get("summary") or ""
    if not str(problem).strip():
        raise ValueError("problem is required")
    if not str(result_summary).strip():
        raise ValueError("result_summary is required")
    payload = {
        "problem": problem,
        "task_type": args.get("task_type") or "general",
        "goal": args.get("goal") or args.get("problem") or "write reusable ma3 outcome",
        "target": _target(args),
        "environment": args.get("environment"),
        "versions": args.get("versions"),
        "observations": args.get("observations") or [],
        "actions": args.get("actions") or [],
        "outcome": args.get("outcome") or "success",
        "result_summary": result_summary,
        "evidence": args.get("evidence") or [],
        "based_on_record_ids": args.get("based_on_record_ids") or [],
        "relation_type": args.get("relation_type"),
        "applicable_if": args.get("applicable_if") or [],
        "not_applicable_if": args.get("not_applicable_if") or [],
        "tags": args.get("tags") or [],
        "case_id": args.get("case_id"),
        "case_assignment_mode": args.get("case_assignment_mode") or "auto",
        "dry_run": bool(args.get("dry_run", False)),
        "redaction_mode": args.get("redaction_mode") or "auto",
    }
    return V2AgentReportRequest.model_validate(payload)


def _compact_context(data: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for group in data.get("cases", []):
        case = group.get("case") or {}
        records = group.get("records") or []
        cases.append({
            "case_id": case.get("case_id"),
            "title": case.get("title"),
            "summary": case.get("summary"),
            "match_score": group.get("match_score"),
            "record_count": len(records),
            "top_records": [
                {
                    "record_id": r.get("record_id"),
                    "title": r.get("title"),
                    "summary": r.get("summary"),
                    "risk_level": r.get("risk_level"),
                    "status": r.get("status"),
                }
                for r in records[:3]
            ],
            "why_matched": group.get("why_matched") or [],
        })
    ungrouped = data.get("ungrouped_records") or []
    out = {
        "cases": cases,
        "ungrouped_records": [
            {"record_id": r.get("record_id"), "title": r.get("title"), "summary": r.get("summary")}
            for r in ungrouped[:5]
        ],
        "warnings": data.get("warnings") or [],
        "server": data.get("server") or {},
    }
    if data.get("explain"):
        explain = data["explain"]
        out["explain"] = {
            "query_hash": explain.get("query_hash"),
            "candidate_count": explain.get("candidate_count"),
            "returned_case_count": explain.get("returned_case_count"),
            "returned_record_count": explain.get("returned_record_count"),
            "full_scan": explain.get("full_scan"),
            "stages": explain.get("stages") or [],
        }
    return out


def _context_summary(compact: dict[str, Any]) -> str:
    lines = [f"ma3_context: {len(compact['cases'])} cases, {len(compact['ungrouped_records'])} ungrouped records"]
    for idx, case in enumerate(compact["cases"], start=1):
        lines.append(f"{idx}. {case.get('title')} ({case.get('case_id')}) records={case.get('record_count')}")
        if case.get("summary"):
            lines.append(f"   {case['summary'][:300]}")
    if compact.get("warnings"):
        lines.append("warnings: " + "; ".join(compact["warnings"]))
    if compact.get("explain", {}).get("query_hash"):
        lines.append(f"query_hash: {compact['explain']['query_hash']}")
    return "\n".join(lines)


def _require_write_library_id(auth: McpAuthContext) -> str | None:
    try:
        return primary_write_library_id(auth.principal)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(status_code=401, detail="auth_missing") from exc
        if exc.status_code == 403:
            raise HTTPException(status_code=403, detail="permission_denied") from exc
        raise


def _require_library_writer(auth: McpAuthContext, library_id: str) -> None:
    if auth.principal.is_admin_bypass:
        return
    lib = LibraryRepository().get(library_id)
    if auth.principal.kind == "anonymous" and (lib is None or not lib.is_public):
        raise HTTPException(status_code=401, detail="auth_missing")
    if library_id not in auth.writable_library_ids:
        raise HTTPException(status_code=403, detail="permission_denied")


def _require_record_admin(auth: McpAuthContext, library_id: str | None) -> None:
    if auth.principal.is_admin_bypass:
        return
    if auth.principal.kind == "anonymous":
        raise HTTPException(status_code=401, detail="auth_missing")
    if not library_id or effective_libraries(auth.principal, role_at_least="admin").get(library_id) != "admin":
        raise HTTPException(status_code=403, detail="permission_denied")


def call_mcp_tool(tool_name: str, arguments: dict[str, Any], auth: McpAuthContext) -> McpToolResult:
    started = time.perf_counter()
    status = "ok"
    error_type = None
    include_full_json = bool(arguments.get("include_full_json", False))
    try:
        if tool_name not in PAYLOAD_BY_TOOL:
            raise HTTPException(status_code=404, detail="tool_not_found")

        validated = _validate_args(tool_name, arguments)

        if tool_name == "ma3_context":
            req = _context_request(validated)
            resp = build_agent_context(
                req,
                auth.readable_library_ids,
                library_id=auth.principal.library_id,
                route="/mcp/ma3_context",
            )
            full = resp.model_dump(mode="json")
            compact = _compact_context(full)
            return _tool_result(_context_summary(compact), compact if not include_full_json else full, include_full_json=False)

        if tool_name == "ma3_search_explain":
            req = _context_request(validated, explain=True)
            resp = build_agent_context(
                req,
                auth.readable_library_ids,
                library_id=auth.principal.library_id,
                route="/mcp/ma3_search_explain",
            )
            full = resp.model_dump(mode="json")
            compact = _compact_context(full)
            return _tool_result(_context_summary(compact), compact if not include_full_json else full, include_full_json=False)

        if tool_name == "ma3_report":
            library_id = _require_write_library_id(auth)
            req = _report_request(validated)
            resp = ingest_v2_agent_report(req, library_id=library_id, accessible_library_ids=auth.readable_library_ids)
            full = resp.model_dump(mode="json")
            compact = {
                "persisted": full.get("persisted"),
                "record_id": (full.get("record") or {}).get("record_id"),
                "case_assignment": full.get("case_assignment"),
                "requires_manual_review": full.get("requires_manual_review"),
                "review_reasons": full.get("review_reasons") or [],
                "relations_created": len(full.get("relations_created") or []),
            }
            summary = f"ma3_report: persisted={compact['persisted']} record_id={compact['record_id']} case_assignment={compact['case_assignment'].get('result') if compact.get('case_assignment') else None}"
            return _tool_result(summary, compact if not include_full_json else full, include_full_json=False)

        if tool_name == "ma3_case":
            case_id = validated["case_id"]
            cases = CaseRepository().list_by_ids_accessible({case_id}, auth.readable_library_ids)
            if not cases:
                raise HTTPException(status_code=404, detail="case not found")
            records = V2RecordRepository().records_for_cases({case_id}, limit_per_case=100).get(case_id, [])
            relations_by_record = V2GraphRepository().relations_by_record_ids({r.record_id for r in records})
            relations = []
            for items in relations_by_record.values():
                relations.extend(items)
            group = V2CaseRecordGroup(case=cases[0], records=records, relations=relations)
            full = group.model_dump(mode="json")
            compact = {
                "case": full.get("case"),
                "record_count": len(full.get("records") or []),
                "records": [
                    {"record_id": r.get("record_id"), "title": r.get("title"), "summary": r.get("summary")}
                    for r in (full.get("records") or [])[:10]
                ],
                "relation_count": len(full.get("relations") or []),
            }
            summary = f"ma3_case: {case_id} records={compact['record_count']} relations={compact['relation_count']}"
            return _tool_result(summary, compact if not include_full_json else full, include_full_json=False)

        if tool_name == "ma3_doctor":
            full = server_doctor()
            full["mcp"] = {
                "status": "ok",
                "endpoint": "/mcp",
                "protocol_version": MCP_PROTOCOL_VERSION,
                "tool_schema_version": MCP_TOOL_SCHEMA_VERSION,
                "auth": auth.caller_summary,
                "tools": [t.name for t in list_mcp_tools()],
            }
            summary = f"ma3_doctor: server={full.get('status')} mcp=ok auth={auth.caller_summary.get('type')}"
            return _tool_result(summary, full, include_full_json=False)

        if tool_name == "ma3_whoami":
            visible = []
            all_visible = auth.readable_library_ids
            role_map = effective_libraries(auth.principal)
            for lib in LibraryRepository().list_all():
                if lib.library_id in all_visible:
                    visible.append({
                        "library_id": lib.library_id,
                        "name": lib.name,
                        "is_public": lib.is_public,
                        "is_personal": lib.is_personal,
                    })
            full = {
                "identity": auth.caller_summary,
                "principal": {
                    "principal_id": auth.principal.principal_id,
                    "kind": auth.principal.kind,
                    "display_name": auth.principal.display_name,
                    "via": auth.principal.via,
                    "admin_bypass": auth.principal.is_admin_bypass,
                },
                "libraries": [
                    {"library_id": lib_id, "role": role}
                    for lib_id, role in sorted(role_map.items())
                ],
                "visible_libraries": visible,
            }
            summary = f"ma3_whoami: {auth.caller_summary.get('type')} visible_libraries={len(visible)}"
            return _tool_result(summary, full, include_full_json=False)

        if tool_name == "ma3_list_drafts":
            library_id = validated["library_id"]
            _require_library_writer(auth, library_id)
            lib = LibraryRepository().get(library_id)
            if lib is None:
                raise HTTPException(status_code=404, detail="library not found")
            records = [
                r for r in RecordRepository().list_by_library(library_id)
                if r.status == RecordStatus.draft
            ]
            offset = validated["offset"]
            limit = validated["limit"]
            page = records[offset:offset + limit]
            compact = {
                "library_id": library_id,
                "count": len(page),
                "total_drafts": len(records),
                "offset": offset,
                "limit": limit,
                "records": [
                    {
                        "record_id": r.record_id,
                        "title": r.title,
                        "summary": r.summary,
                        "risk_level": r.risk_level,
                        "status": r.status,
                        "updated_at": r.updated_at,
                    }
                    for r in page
                ],
            }
            full = {
                **compact,
                "records": [r.model_dump(mode="json") for r in page],
            }
            summary = f"ma3_list_drafts: library_id={library_id} count={len(page)} total={len(records)}"
            return _tool_result(summary, full if include_full_json else compact, include_full_json=False)

        if tool_name == "ma3_review_record":
            record_id = validated["record_id"]
            record = RecordRepository().get(record_id)
            if record is None:
                raise HTTPException(status_code=404, detail="record not found")
            _require_record_admin(auth, record.library_id)
            if record.status != RecordStatus.draft:
                raise ValueError("only draft records can be reviewed via MCP")
            decision = validated["decision"]
            review_note = validated["review_note"]
            if decision == "approve":
                updated = promote_record(record, review_note=review_note)
                new_status = RecordStatus.active
            else:
                updated = reject_record(record, review_note=review_note)
                new_status = RecordStatus.invalid
            compact = {
                "record_id": updated.record_id,
                "library_id": updated.library_id,
                "decision": decision,
                "old_status": RecordStatus.draft,
                "new_status": new_status,
                "review_note": updated.review_note,
                "reviewed_at": updated.reviewed_at,
                "reviewer": auth.caller_summary,
            }
            full = {**compact, "record": updated.model_dump(mode="json")}
            summary = (
                f"ma3_review_record: record_id={updated.record_id} "
                f"decision={decision} new_status={new_status}"
            )
            return _tool_result(summary, full if include_full_json else compact, include_full_json=False)

        if tool_name == "ma3_validate":
            inner_tool = validated["tool_name"]
            inner_args = validated.get("arguments") or {}
            try:
                _validate_args(inner_tool, inner_args)
                ok_payload = {"ok": True, "tool_name": inner_tool}
                return _tool_result(
                    f"ma3_validate: {inner_tool} ok",
                    ok_payload,
                    include_full_json=False,
                )
            except McpToolValidationError as exc:
                err_payload = {
                    "ok": False,
                    "tool_name": inner_tool,
                    "validation_errors": exc.errors,
                    "schema_hint": (
                        f"See tools/list inputSchema for {inner_tool}; "
                        "fix each entry in validation_errors[*].loc and retry."
                    ),
                }
                return _tool_result(
                    f"ma3_validate: {inner_tool} failed ({len(exc.errors)} error(s))",
                    err_payload,
                    include_full_json=False,
                )

        raise HTTPException(status_code=404, detail="tool_not_found")
    except McpToolValidationError as exc:
        status = "error"
        error_type = "invalid_params"
        raise
    except HTTPException as exc:
        status = "error"
        error_type = str(exc.detail)
        raise
    except (ValidationError, ValueError) as exc:
        status = "error"
        error_type = "invalid_params"
        raise ValueError(str(exc)) from exc
    finally:
        duration = time.perf_counter() - started
        metrics.record_mcp_tool(tool_name, status, duration, error_type=error_type)
        write_op_log(
            "mcp_tool_call",
            tool=tool_name,
            status=status,
            latency_ms=round(duration * 1000, 3),
            caller=auth.caller_summary,
            error_type=error_type,
            payload_summary={
                "problem": arguments.get("problem"),
                "include_full_json": bool(arguments.get("include_full_json")),
                "dry_run": bool(arguments.get("dry_run")),
            },
        )


def mcp_initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "ma3-remote-mcp",
            "version": settings.service_version,
        },
        "instructions": "Use ma3_context before technical work, ma3_report to write reusable outcomes, and ma3_doctor for diagnostics.",
    }
