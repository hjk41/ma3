from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.client_bundle import (
    build_client_manifest,
    build_mcp_tools_bytes,
    read_bundle_file_bytes,
)

router = APIRouter(tags=["client"])


def _serve_bytes(rel_path: str) -> Response:
    try:
        content = read_bundle_file_bytes(rel_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if rel_path.endswith(".json") and rel_path != "mcp-tools.json":
        media_type = "application/json"
    elif rel_path.endswith(".sh"):
        media_type = "text/x-shellscript"
    elif rel_path.endswith(".py"):
        media_type = "text/x-python"
    else:
        media_type = "text/plain"
    return Response(content=content, media_type=media_type)


@router.get("/client/manifest.json")
def get_client_manifest() -> dict:
    try:
        return build_client_manifest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"client bundle incomplete: {exc}") from exc


@router.get("/client/mcp-tools.json")
def get_mcp_tools_snapshot() -> Response:
    return Response(content=build_mcp_tools_bytes(), media_type="application/json")


@router.get("/client/agent-onboarding.md")
def get_agent_onboarding() -> Response:
    return _serve_bytes("agent-onboarding.md")


@router.get("/client/agent-onboarding.zh.md")
def get_agent_onboarding_zh() -> Response:
    return _serve_bytes("agent-onboarding.zh.md")


@router.get("/client/connect.md")
def get_connect() -> Response:
    return _serve_bytes("connect.md")


@router.get("/client/connect.zh.md")
def get_connect_zh() -> Response:
    return _serve_bytes("connect.zh.md")


@router.get("/client/templates/ma3-agent-policy.mdc")
def get_agent_policy_mdc() -> Response:
    return _serve_bytes("templates/ma3-agent-policy.mdc")


@router.get("/client/templates/ma3-client.env.example")
def get_client_env_example() -> Response:
    return _serve_bytes("templates/ma3-client.env.example")


@router.get("/client/skills/ma3/SKILL.md")
def get_ma3_skill_md() -> Response:
    return _serve_bytes("skills/ma3/SKILL.md")


@router.get("/client/scripts/sync_ma3_client.sh")
def get_sync_shell() -> Response:
    return _serve_bytes("scripts/sync_ma3_client.sh")


@router.get("/client/scripts/sync_ma3_client.py")
def get_sync_python() -> Response:
    return _serve_bytes("scripts/sync_ma3_client.py")


@router.get("/client/lib/ma3_sync_core.py")
def get_sync_core() -> Response:
    return _serve_bytes("lib/ma3_sync_core.py")
