from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import ResolvedToken, _is_admin_key, hash_token
from app.models.common import TargetRef
from app.models.mcp import McpToolDescriptor, McpToolResult
from app.models.v2 import V2AgentContextRequest, V2AgentReportRequest, V2CaseRecordGroup
from app.services.doctor_service import server_doctor
from app.services.library_service import accessible_library_ids
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.services.v2_agent_service import ingest_v2_agent_report
from app.services.v2_search_service import build_agent_context
from app.storage.repositories import LibraryRepository, TokenRepository
from app.storage.v2_repositories import CaseRepository, V2GraphRepository, V2RecordRepository


MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_TOOL_SCHEMA_VERSION = "ma3.mcp.v1"


@dataclass(slots=True)
class McpAuthContext:
    raw_present: bool
    is_admin: bool
    token: ResolvedToken | None

    @property
    def readable_library_ids(self) -> set[str]:
        return accessible_library_ids(self.token, is_admin=self.is_admin)

    @property
    def caller_summary(self) -> dict[str, Any]:
        if self.is_admin:
            return {"type": "admin"}
        if self.token is not None:
            return {
                "type": "library_token",
                "token_id": self.token.token_id,
                "library_id": self.token.library_id,
                "role": self.token.role,
                "label": self.token.label,
            }
        return {"type": "anonymous"}


def resolve_mcp_auth(raw: str | None) -> McpAuthContext:
    if not raw:
        return McpAuthContext(raw_present=False, is_admin=False, token=None)
    if _is_admin_key(raw):
        return McpAuthContext(raw_present=True, is_admin=True, token=None)
    info = TokenRepository().get_by_hash(hash_token(raw))
    if info is None:
        raise HTTPException(status_code=401, detail="auth_invalid")
    return McpAuthContext(
        raw_present=True,
        is_admin=False,
        token=ResolvedToken(
            token_id=info.token_id,
            library_id=info.library_id,
            label=info.label,
            role=info.role,
        ),
    )


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": True,
    }


def list_mcp_tools() -> list[McpToolDescriptor]:
    return [
        McpToolDescriptor(
            name="ma3_context",
            description="Return agent-ready ma3 context for a task: matched cases, records, warnings, and optional explain data.",
            inputSchema=_schema({
                "problem": {"type": "string"},
                "goal": {"type": "string"},
                "task_type": {"type": "string"},
                "target_product": {"type": "string"},
                "target_component": {"type": "string"},
                "target": {"type": "object"},
                "environment": {"type": "object"},
                "versions": {"type": "object"},
                "observations": {"type": "array", "items": {"type": "string"}},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "max_cases": {"type": "integer", "minimum": 1, "maximum": 20},
                "max_records_per_case": {"type": "integer", "minimum": 1, "maximum": 10},
                "include_explain": {"type": "boolean"},
                "include_full_json": {"type": "boolean"},
            }, ["problem"]),
        ),
        McpToolDescriptor(
            name="ma3_report",
            description="Write back an agent outcome to ma3 and assign it to a case.",
            inputSchema=_schema({
                "problem": {"type": "string"},
                "goal": {"type": "string"},
                "task_type": {"type": "string"},
                "target_product": {"type": "string"},
                "target_component": {"type": "string"},
                "target": {"type": "object"},
                "outcome": {"type": "string"},
                "result_summary": {"type": "string"},
                "actions": {"type": "array"},
                "evidence": {"type": "array"},
                "observations": {"type": "array", "items": {"type": "string"}},
                "based_on_record_ids": {"type": "array", "items": {"type": "string"}},
                "relation_type": {"type": "string"},
                "case_id": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "redaction_mode": {"type": "string", "enum": ["auto", "none"]},
                "include_full_json": {"type": "boolean"},
            }, ["problem", "outcome", "result_summary"]),
        ),
        McpToolDescriptor(
            name="ma3_case",
            description="Read one ma3 case timeline with records and relations visible to the caller.",
            inputSchema=_schema({
                "case_id": {"type": "string"},
                "include_full_json": {"type": "boolean"},
            }, ["case_id"]),
        ),
        McpToolDescriptor(
            name="ma3_search_explain",
            description="Diagnostic ma3 search that always includes ranking/candidate explain data.",
            inputSchema=_schema({
                "problem": {"type": "string"},
                "goal": {"type": "string"},
                "task_type": {"type": "string"},
                "target_product": {"type": "string"},
                "target_component": {"type": "string"},
                "target": {"type": "object"},
                "max_cases": {"type": "integer"},
                "max_records_per_case": {"type": "integer"},
                "include_full_json": {"type": "boolean"},
            }, ["problem"]),
        ),
        McpToolDescriptor(
            name="ma3_doctor",
            description="Diagnose remote MCP authentication, server health, version, database, and index state.",
            inputSchema=_schema({"include_full_json": {"type": "boolean"}}),
        ),
        McpToolDescriptor(
            name="ma3_whoami",
            description="Return the caller identity and visible library summary without exposing token material.",
            inputSchema=_schema({"include_full_json": {"type": "boolean"}}),
        ),
    ]


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
    if auth.is_admin:
        return None
    if auth.token is None:
        raise HTTPException(status_code=401, detail="auth_missing")
    if auth.token.role not in {"writer", "admin"}:
        raise HTTPException(status_code=403, detail="permission_denied")
    return auth.token.library_id


def call_mcp_tool(tool_name: str, arguments: dict[str, Any], auth: McpAuthContext) -> McpToolResult:
    started = time.perf_counter()
    status = "ok"
    error_type = None
    include_full_json = bool(arguments.get("include_full_json", False))
    try:
        if tool_name == "ma3_context":
            req = _context_request(arguments)
            resp = build_agent_context(
                req,
                auth.readable_library_ids,
                library_id=auth.token.library_id if auth.token else None,
                route="/mcp/ma3_context",
            )
            full = resp.model_dump(mode="json")
            compact = _compact_context(full)
            return _tool_result(_context_summary(compact), compact if not include_full_json else full, include_full_json=False)

        if tool_name == "ma3_search_explain":
            req = _context_request(arguments, explain=True)
            resp = build_agent_context(
                req,
                auth.readable_library_ids,
                library_id=auth.token.library_id if auth.token else None,
                route="/mcp/ma3_search_explain",
            )
            full = resp.model_dump(mode="json")
            compact = _compact_context(full)
            return _tool_result(_context_summary(compact), compact if not include_full_json else full, include_full_json=False)

        if tool_name == "ma3_report":
            library_id = _require_write_library_id(auth)
            req = _report_request(arguments)
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
            case_id = arguments.get("case_id")
            if not case_id:
                raise ValueError("case_id is required")
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
            for lib in LibraryRepository().list_all():
                if lib.library_id in all_visible:
                    visible.append({
                        "library_id": lib.library_id,
                        "name": lib.name,
                        "is_public": lib.is_public,
                        "is_personal": lib.is_personal,
                    })
            full = {"identity": auth.caller_summary, "visible_libraries": visible}
            summary = f"ma3_whoami: {auth.caller_summary.get('type')} visible_libraries={len(visible)}"
            return _tool_result(summary, full, include_full_json=False)

        raise HTTPException(status_code=404, detail="tool_not_found")
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
                "has_problem": bool(arguments.get("problem")),
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
