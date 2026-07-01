from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.services.client_bundle import (
    CLIENT_MANIFEST_FILES,
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
    return build_client_manifest()


@router.get("/client/mcp-tools.json")
def get_mcp_tools_snapshot() -> Response:
    return Response(content=build_mcp_tools_bytes(), media_type="application/json")


@router.get("/client/agent-onboarding.md", response_class=PlainTextResponse)
def get_agent_onboarding() -> str:
    return read_bundle_file_bytes("agent-onboarding.md").decode("utf-8")


@router.get("/client/templates/ma3-agent-policy.mdc", response_class=PlainTextResponse)
def get_agent_policy_mdc() -> str:
    return read_bundle_file_bytes("templates/ma3-agent-policy.mdc").decode("utf-8")


@router.get("/client/templates/ma3-client.env.example", response_class=PlainTextResponse)
def get_client_env_example() -> str:
    return read_bundle_file_bytes("templates/ma3-client.env.example").decode("utf-8")


@router.get("/client/scripts/sync_ma3_client.sh")
def get_sync_shell() -> Response:
    return _serve_bytes("scripts/sync_ma3_client.sh")


@router.get("/client/scripts/sync_ma3_client.py")
def get_sync_python() -> Response:
    return _serve_bytes("scripts/sync_ma3_client.py")


@router.get("/client/lib/ma3_sync_core.py")
def get_sync_core() -> Response:
    return _serve_bytes("lib/ma3_sync_core.py")
