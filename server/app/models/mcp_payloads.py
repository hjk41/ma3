"""Pydantic payload models for ma3 MCP tools.

These wrappers exist so the JSON Schema published in
``tools/list[].inputSchema`` stays synchronised with the strict Pydantic
validator the server actually runs. Before this layer was added, every tool's
schema was a hand-written dict next to a Pydantic model, and the two
descriptions drifted apart (most painfully for ``actions`` and ``evidence``,
where the server enforced ``AgentAction`` / ``EvidenceItem`` while the schema
just said ``"type": "array"``).

Each MCP tool has its own Pydantic payload model here; their shapes mirror the
loose API the MCP layer accepts (``problem`` required, the rest defaulted) and
they reuse ``AgentAction`` / ``EvidenceItem`` / ``TargetRef`` so nested ``$defs``
appear in the published schema. All models have ``extra="forbid"`` so typos
fail with the offending field name, and ``json_schema_extra={"examples": [...]}``
so clients see a concrete working payload via ``inputSchema.examples[0]``.

``tool_input_schema(tool_name)`` is the single source of truth used by both
``mcp_tool_service.list_mcp_tools()`` (advertised schema) and
``mcp_tool_service._validate_args()`` (runtime check).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentAction
from app.models.common import EnvironmentFingerprint, EvidenceItem, TargetRef, VersionInfo


_TARGET_EXAMPLE = {"product": "ma3", "component": "remote-mcp"}


_REPORT_EXAMPLE = {
    "problem": "MCP server returns -32602 with no field info",
    "outcome": "resolved",
    "result_summary": (
        "Inputs are now validated against a Pydantic schema and validation "
        "errors surface as a structured list under error.data.validation_errors."
    ),
    "task_type": "debug_mcp_protocol",
    "goal": "explain how ma3 inputSchema is generated and verified",
    "target": _TARGET_EXAMPLE,
    "observations": [
        "Manual binary-bisection identified actions as the offending field.",
        "Server-side Pydantic refused the AgentAction shape silently.",
    ],
    "actions": [
        {
            "action": "Compared published inputSchema against V2AgentReportRequest",
            "rationale": "Confirm the loose array shape mismatched the strict model",
            "ref": "server/app/services/mcp_tool_service.py",
        }
    ],
    "evidence": [
        {"kind": "log", "summary": "tools/call returned -32602 Invalid params", "ref": "ma3 stderr"}
    ],
    "based_on_record_ids": [],
    "tags": ["mcp", "schema-validation"],
    "dry_run": False,
}


_CONTEXT_EXAMPLE = {
    "problem": "Looking for prior cases on MCP schema drift between client and server.",
    "task_type": "debug_mcp_protocol",
    "goal": "find ma3 cases describing how to keep inputSchema aligned with the validator",
    "target": _TARGET_EXAMPLE,
    "tags": ["mcp", "schema-validation"],
    "max_cases": 5,
    "max_records_per_case": 3,
    "include_explain": False,
}


class Ma3ContextPayload(BaseModel):
    """Wire payload for ``ma3_context``.

    The MCP layer is intentionally looser than ``V2AgentContextRequest``:
    ``task_type`` / ``goal`` default server-side, and callers may supply
    ``target_product`` / ``target_component`` as flat strings instead of a
    nested ``target`` object.
    """

    problem: str = Field(..., min_length=1)
    task_type: str | None = None
    goal: str | None = None
    target: TargetRef | None = None
    target_product: str | None = None
    target_component: str | None = None
    environment: EnvironmentFingerprint | None = None
    versions: VersionInfo | None = None
    observations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    max_cases: int = Field(default=3, ge=1, le=20)
    max_records_per_case: int = Field(default=3, ge=1, le=10)
    include_explain: bool = False
    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [_CONTEXT_EXAMPLE]},
    )


class Ma3SearchExplainPayload(Ma3ContextPayload):
    """Wire payload for ``ma3_search_explain``. ``include_explain`` is forced True server-side."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{**_CONTEXT_EXAMPLE, "include_explain": True}]},
    )


class Ma3ReportPayload(BaseModel):
    """Wire payload for ``ma3_report``.

    Same looseness as ``Ma3ContextPayload`` for ``task_type``/``goal``/``target``,
    plus the write-side fields. ``actions`` and ``evidence`` are the typed
    nested arrays whose absence caused the original -32602 confusion.
    """

    problem: str = Field(..., min_length=1)
    outcome: str = Field(..., min_length=1)
    result_summary: str = Field(..., min_length=1)
    task_type: str | None = None
    goal: str | None = None
    target: TargetRef | None = None
    target_product: str | None = None
    target_component: str | None = None
    environment: EnvironmentFingerprint | None = None
    versions: VersionInfo | None = None
    observations: list[str] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    based_on_record_ids: list[str] = Field(default_factory=list)
    relation_type: str | None = None
    applicable_if: list[str] = Field(default_factory=list)
    not_applicable_if: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    case_id: str | None = None
    case_assignment_mode: Literal["auto", "force", "manual"] = "auto"
    dry_run: bool = False
    redaction_mode: Literal["auto", "none"] = "auto"
    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [_REPORT_EXAMPLE]},
    )


class Ma3CasePayload(BaseModel):
    """Wire payload for ``ma3_case``."""

    case_id: str = Field(..., min_length=1)
    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"case_id": "cs_01HX9F...", "include_full_json": False}]},
    )


class Ma3DoctorPayload(BaseModel):
    """Wire payload for ``ma3_doctor``."""

    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{}]},
    )


class Ma3WhoamiPayload(BaseModel):
    """Wire payload for ``ma3_whoami``."""

    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{}]},
    )


class Ma3ListDraftsPayload(BaseModel):
    """Wire payload for ``ma3_list_drafts``."""

    library_id: str = Field(..., min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "library_id": "lib_ca4043b1c70d",
                    "limit": 20,
                    "offset": 0,
                    "include_full_json": False,
                }
            ]
        },
    )


class Ma3ReviewRecordPayload(BaseModel):
    """Wire payload for ``ma3_review_record``."""

    record_id: str = Field(..., min_length=1)
    decision: Literal["approve", "reject"]
    review_note: str = Field(..., min_length=1)
    include_full_json: bool = False

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "record_id": "vk_01HX9F...",
                    "decision": "approve",
                    "review_note": "Validated against source docs and safe to promote.",
                    "include_full_json": False,
                }
            ]
        },
    )


class Ma3ValidatePayload(BaseModel):
    """Wire payload for the diagnostic ``ma3_validate`` tool.

    Runs only the Pydantic validation pipeline for the named tool against the
    supplied arguments. Returns either ``{ok: true}`` or the same structured
    ``validation_errors`` shape clients get on a real call so an agent can
    iterate quickly without consuming write quota or polluting the case graph.
    """

    tool_name: Literal[
        "ma3_report",
        "ma3_context",
        "ma3_search_explain",
        "ma3_case",
        "ma3_doctor",
        "ma3_whoami",
        "ma3_list_drafts",
        "ma3_review_record",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"tool_name": "ma3_report", "arguments": _REPORT_EXAMPLE}]
        },
    )


PAYLOAD_BY_TOOL: dict[str, type[BaseModel]] = {
    "ma3_context": Ma3ContextPayload,
    "ma3_report": Ma3ReportPayload,
    "ma3_case": Ma3CasePayload,
    "ma3_search_explain": Ma3SearchExplainPayload,
    "ma3_doctor": Ma3DoctorPayload,
    "ma3_whoami": Ma3WhoamiPayload,
    "ma3_list_drafts": Ma3ListDraftsPayload,
    "ma3_review_record": Ma3ReviewRecordPayload,
    "ma3_validate": Ma3ValidatePayload,
}


def tool_input_schema(tool_name: str) -> dict[str, Any]:
    """Return the wire JSON Schema for a given MCP tool name."""

    model = PAYLOAD_BY_TOOL[tool_name]
    return model.model_json_schema(ref_template="#/$defs/{model}")
