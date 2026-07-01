from __future__ import annotations

from app.core.config import settings
from tests.helpers.mcp_client import McpClient


def test_server_block_requires_both_versions_reported(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    doctor = mcp.structured("ma3_doctor")
    assert doctor["server"]["client_version_reported"] is False
    assert doctor["server"]["policy_refresh_required"] is False
    assert doctor["server"]["mcp_reload_required"] is False


def test_server_block_stale_skill_only(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    doctor = mcp.structured(
        "ma3_doctor",
        {"client_version": "0.0.1", "tool_schema_version": settings.tool_schema_version},
    )
    server = doctor["server"]
    assert server["policy_refresh_required"] is True
    assert server["mcp_reload_required"] is False
    assert server["client_update_required"] is True


def test_server_block_stale_mcp_only(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    doctor = mcp.structured(
        "ma3_doctor",
        {"client_version": settings.skill_version, "tool_schema_version": "ma3.mcp.v0"},
    )
    server = doctor["server"]
    assert server["policy_refresh_required"] is False
    assert server["mcp_reload_required"] is True
    assert server["client_update_required"] is True
