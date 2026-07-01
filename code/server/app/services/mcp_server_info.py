"""MCP server block — client update URLs and upgrade flags (scheme B)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.client_bundle import CLIENT_UPDATE_URLS, ClientReport


def parse_version(version: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for piece in str(version).split(".")[:3]:
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def version_lt(left: str, right: str) -> bool:
    return parse_version(left) < parse_version(right)


def parse_tool_schema_version(version: str) -> int:
    raw = str(version)
    if ".v" in raw:
        suffix = raw.rsplit(".v", 1)[-1]
        try:
            return int(suffix)
        except ValueError:
            return 0
    return 0


def tool_schema_lt(left: str, right: str) -> bool:
    return parse_tool_schema_version(left) < parse_tool_schema_version(right)


def build_mcp_server_block(*, client_report: ClientReport | None = None) -> dict[str, Any]:
    report = client_report or ClientReport()
    block: dict[str, Any] = {
        "service_version": settings.service_version,
        "skill_bundle_version": settings.skill_version,
        "protocol_version": settings.protocol_version,
        "tool_schema_version": settings.tool_schema_version,
        "api_version": settings.api_version,
        "min_skill_bundle_version": settings.min_client_version,
        "min_tool_schema_version": settings.min_tool_schema_version,
        "recommended_skill_bundle_version": settings.recommended_client_version,
        "min_client_version": settings.min_client_version,
        "recommended_client_version": settings.recommended_client_version,
        "git_commit": settings.git_commit,
        "deployed_at": settings.started_at,
        "client_update_urls": list(CLIENT_UPDATE_URLS),
        "client_state_path": settings.client_state_filename,
        "sync_command": settings.client_sync_command,
        "client_version_reported": report.reported,
    }

    skill = report.skill_bundle_version
    tool = report.tool_schema_version
    if skill:
        block["client_version"] = skill
        block["client_skill_bundle_version"] = skill
    if tool:
        block["client_tool_schema_version"] = tool

    if not report.reported:
        block.update(
            {
                "policy_refresh_required": False,
                "mcp_reload_required": False,
                "client_update_required": False,
                "client_update_recommended": False,
            }
        )
        return block

    policy_breaking = bool(skill and version_lt(skill, settings.min_client_version))
    policy_refresh = bool(skill and version_lt(skill, settings.skill_version))
    policy_recommended = bool(skill and version_lt(skill, settings.recommended_client_version))

    mcp_breaking = bool(tool and tool_schema_lt(tool, settings.min_tool_schema_version))
    mcp_reload = bool(tool and tool != settings.tool_schema_version)
    mcp_recommended = bool(tool and tool_schema_lt(tool, settings.tool_schema_version))

    policy_refresh_required = policy_refresh or policy_breaking
    mcp_reload_required = mcp_reload or mcp_breaking

    client_update_required = policy_breaking or mcp_breaking
    client_update_recommended = (not client_update_required) and (
        policy_recommended or mcp_recommended or policy_refresh_required or mcp_reload_required
    )

    block.update(
        {
            "policy_refresh_required": policy_refresh_required,
            "mcp_reload_required": mcp_reload_required,
            "client_update_required": client_update_required,
            "client_update_recommended": client_update_recommended,
        }
    )
    return block


def attach_server_block(
    structured: dict[str, Any],
    *,
    client_report: ClientReport | None = None,
    client_version: str | None = None,
) -> dict[str, Any]:
    if client_report is None and client_version is not None:
        client_report = ClientReport(skill_bundle_version=client_version)
    return {**structured, "server": build_mcp_server_block(client_report=client_report)}


def extract_client_report(arguments: dict[str, Any]) -> tuple[dict[str, Any], ClientReport]:
    raw = dict(arguments)
    skill = raw.pop("client_version", None)
    tool = raw.pop("tool_schema_version", None)
    if skill is not None:
        skill = str(skill).strip() or None
    if tool is not None:
        tool = str(tool).strip() or None
    return raw, ClientReport(skill_bundle_version=skill, tool_schema_version=tool)


def extract_client_version(arguments: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    raw, report = extract_client_report(arguments)
    return raw, report.skill_bundle_version
