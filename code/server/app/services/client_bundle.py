from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings

CLIENT_DIR = Path(__file__).resolve().parents[3] / "client"

CLIENT_MANIFEST_FILES: tuple[tuple[str, str], ...] = (
    ("agent-onboarding.md", "/client/agent-onboarding.md"),
    ("connect.md", "/client/connect.md"),
    ("templates/ma3-agent-policy.mdc", "/client/templates/ma3-agent-policy.mdc"),
    ("templates/ma3-client.env.example", "/client/templates/ma3-client.env.example"),
    ("skills/ma3/SKILL.md", "/client/skills/ma3/SKILL.md"),
    ("mcp-tools.json", "/client/mcp-tools.json"),
    ("scripts/sync_ma3_client.sh", "/client/scripts/sync_ma3_client.sh"),
    ("scripts/sync_ma3_client.py", "/client/scripts/sync_ma3_client.py"),
    ("lib/ma3_sync_core.py", "/client/lib/ma3_sync_core.py"),
)

CLIENT_UPDATE_URLS: tuple[str, ...] = tuple(url for _path, url in CLIENT_MANIFEST_FILES) + (
    "/client/manifest.json",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_mcp_tools_snapshot() -> dict[str, Any]:
    from app.services.mcp_tool_service import list_mcp_tools

    tools = [tool.model_dump(mode="json") for tool in list_mcp_tools()]
    return {
        "tool_schema_version": settings.tool_schema_version,
        "protocol_version": settings.protocol_version,
        "tools": tools,
    }


def build_mcp_tools_bytes() -> bytes:
    return json.dumps(build_mcp_tools_snapshot(), sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def read_bundle_file_bytes(rel_path: str, *, client_dir: Path | None = None) -> bytes:
    if rel_path == "mcp-tools.json":
        return build_mcp_tools_bytes()
    root = client_dir or CLIENT_DIR
    path = root / rel_path
    if not path.is_file():
        raise FileNotFoundError(rel_path)
    return path.read_bytes()


def build_client_manifest(*, client_dir: Path | None = None) -> dict[str, Any]:
    root = client_dir or CLIENT_DIR
    files: list[dict[str, Any]] = []
    for rel_path, url in CLIENT_MANIFEST_FILES:
        content = read_bundle_file_bytes(rel_path, client_dir=root)
        files.append(
            {
                "path": rel_path,
                "url": url,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return {
        "skill_bundle_version": settings.skill_version,
        "tool_schema_version": settings.tool_schema_version,
        "sync_tooling_version": settings.sync_tooling_version,
        "min_skill_bundle_version": settings.min_client_version,
        "min_tool_schema_version": settings.min_tool_schema_version,
        "recommended_skill_bundle_version": settings.recommended_client_version,
        "service_version": settings.service_version,
        "client_state_path": settings.client_state_filename,
        "client_config_template": "/client/templates/ma3-client.env.example",
        "sync_command": settings.client_sync_command,
        "files": files,
        "min_client_version": settings.min_client_version,
        "recommended_client_version": settings.recommended_client_version,
    }


@dataclass(slots=True)
class ClientReport:
    skill_bundle_version: str | None = None
    tool_schema_version: str | None = None

    @property
    def reported(self) -> bool:
        return self.skill_bundle_version is not None or self.tool_schema_version is not None
