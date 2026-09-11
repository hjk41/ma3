from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.client_bundle import build_client_manifest
from app.services.client_sync import HttpFetchAdapter, load_client_state, plan_sync, sync_client
from app.services.mcp_server_info import build_mcp_server_block
from app.services.client_bundle import ClientReport
from tests.helpers.mcp_client import McpClient


CLIENT_UPDATE_URLS = {
    "/client/manifest.json",
    "/client/agent-onboarding.md",
    "/client/connect.md",
    "/client/templates/ma3-agent-policy.mdc",
    "/client/templates/ma3-client.env.example",
    "/client/skills/ma3/SKILL.md",
    "/client/mcp-tools.json",
    "/client/scripts/sync_ma3_client.sh",
    "/client/scripts/sync_ma3_client.py",
    "/client/lib/ma3_sync_core.py",
}


def test_manifest_includes_mcp_tools_and_dual_versions(isolated_client):
    manifest = isolated_client.get("/client/manifest.json").json()
    assert manifest["skill_bundle_version"] == settings.skill_version
    assert manifest["tool_schema_version"] == settings.tool_schema_version
    assert manifest["min_tool_schema_version"] == settings.min_tool_schema_version
    assert manifest["client_state_path"] == settings.client_state_filename
    assert manifest["sync_command"]
    urls = {entry["url"] for entry in manifest["files"]}
    assert "/client/mcp-tools.json" in urls

    tools = isolated_client.get("/client/mcp-tools.json").json()
    assert tools["tool_schema_version"] == settings.tool_schema_version
    assert any(t["name"] == "ma3_context" for t in tools["tools"])


def test_server_block_policy_and_mcp_flags(isolated_client):
    stale = ClientReport(skill_bundle_version="0.0.1", tool_schema_version="ma3.mcp.v0")
    block = build_mcp_server_block(client_report=stale)
    assert block["policy_refresh_required"] is True
    assert block["mcp_reload_required"] is True
    assert block["client_update_required"] is True

    current = ClientReport(
        skill_bundle_version=settings.skill_version,
        tool_schema_version=settings.tool_schema_version,
    )
    fresh = build_mcp_server_block(client_report=current)
    assert fresh["policy_refresh_required"] is False
    assert fresh["mcp_reload_required"] is False
    assert fresh["client_update_required"] is False


def test_mcp_doctor_reports_dual_versions(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    doctor = mcp.structured(
        "ma3_doctor",
        {"client_version": "0.0.1", "tool_schema_version": "ma3.mcp.v0"},
    )
    server = doctor["server"]
    assert server["client_skill_bundle_version"] == "0.0.1"
    assert server["client_tool_schema_version"] == "ma3.mcp.v0"
    assert server["policy_refresh_required"] is True
    assert server["mcp_reload_required"] is True


def test_sync_client_writes_state_and_policy(isolated_client, tmp_path):
    install_dir = tmp_path / "ma3"
    state_path = install_dir / "ma3-client.json"
    bin_dir = install_dir / "bin"
    lib_dir = install_dir / "lib"
    http = HttpFetchAdapter(isolated_client)

    state, plan = sync_client(
        http,
        base_url="http://testserver",
        state_path=state_path,
        install_dir=install_dir,
        bin_dir=bin_dir,
        lib_dir=lib_dir,
        force=True,
    )

    assert state.skill_bundle_version == settings.skill_version
    assert state.tool_schema_version == settings.tool_schema_version
    assert state_path.is_file()
    policy_path = install_dir / "policy" / "ma3-agent-policy.mdc"
    skill_path = install_dir / "skills" / "ma3" / "SKILL.md"
    tools_path = install_dir / "mcp-tools.json"
    assert policy_path.is_file()
    assert skill_path.is_file()
    assert "FIRST-ACTION GATE" in policy_path.read_text(encoding="utf-8")
    assert "ma3_context" in skill_path.read_text(encoding="utf-8")
    assert tools_path.is_file()
    assert bin_dir / "sync_ma3_client.sh" in list(bin_dir.iterdir()) or (bin_dir / "sync_ma3_client.sh").is_file()
    assert (lib_dir / "ma3_sync_core.py").is_file()
    assert settings.client_state_filename == ".ma3/ma3-client.json"
    assert plan.files_to_update

    # Second sync with same remote -> no file changes
    state2, plan2 = sync_client(
        http,
        base_url="http://testserver",
        state_path=state_path,
        install_dir=install_dir,
        bin_dir=bin_dir,
        lib_dir=lib_dir,
        force=False,
    )
    assert plan2.files_to_update == []
    assert plan2.tooling_update is False
    assert state2.skill_bundle_version == state.skill_bundle_version


def test_sync_tooling_self_update(isolated_client, tmp_path):
    install_dir = tmp_path / "ma3"
    bin_dir = install_dir / "bin"
    lib_dir = install_dir / "lib"
    http = HttpFetchAdapter(isolated_client)
    manifest = build_client_manifest()

    from app.services.client_sync import sync_tooling

    updated = sync_tooling(http, manifest, bin_dir=bin_dir, lib_dir=lib_dir, force=True)
    assert "scripts/sync_ma3_client.sh" in updated
    assert "scripts/sync_ma3_client.py" in updated
    assert "lib/ma3_sync_core.py" in updated
    assert (bin_dir / "sync_ma3_client.sh").is_file()
    assert (bin_dir / "sync_ma3_client.py").is_file()
    assert (lib_dir / "ma3_sync_core.py").is_file()

    updated2 = sync_tooling(http, manifest, bin_dir=bin_dir, lib_dir=lib_dir, force=False)
    assert updated2 == []


def test_manifest_includes_env_template_and_tooling(isolated_client):
    manifest = isolated_client.get("/client/manifest.json").json()
    paths = {entry["path"] for entry in manifest["files"]}
    assert "templates/ma3-client.env.example" in paths
    assert "skills/ma3/SKILL.md" in paths
    assert "scripts/sync_ma3_client.sh" in paths
    assert manifest["sync_tooling_version"] == settings.sync_tooling_version
    assert manifest["client_config_template"] == "/client/templates/ma3-client.env.example"

    env_example = isolated_client.get("/client/templates/ma3-client.env.example").text
    assert "MA3_BASE_URL" in env_example
    assert "MA3_POLICY_REL" in env_example
    assert "MA3_SKILL_REL" in env_example

    skill = isolated_client.get("/client/skills/ma3/SKILL.md").text
    assert "ma3_context" in skill
    policy = isolated_client.get("/client/templates/ma3-agent-policy.mdc").text
    assert "FIRST-ACTION GATE" in policy
    assert 'ma3_skill_bundle_version: "1.6.0"' in policy


def test_sync_plan_detects_manifest_change(isolated_client, tmp_path, monkeypatch):
    manifest_v1 = build_client_manifest()
    state = {
        "base_url": "http://testserver",
        "skill_bundle_version": manifest_v1["skill_bundle_version"],
        "tool_schema_version": manifest_v1["tool_schema_version"],
        "synced_at": "2026-01-01T00:00:00+00:00",
        "files": {item["path"]: item["sha256"] for item in manifest_v1["files"]},
    }
    state_path = tmp_path / "ma3-client.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.setattr(settings, "skill_version", "9.9.9")
    manifest_v2 = build_client_manifest()
    plan = plan_sync(load_client_state(state_path), manifest_v2)
    assert plan.policy_refresh is True
    assert "templates/ma3-agent-policy.mdc" in plan.files_to_update


def test_policy_documents_scheme_b(isolated_client):
    policy = isolated_client.get("/client/templates/ma3-agent-policy.mdc").text
    assert "ma3-client.json" in policy
    assert "sync_ma3_client" in policy
    assert "tool_schema_version" in policy
    assert "mcp_reload_required" in policy


def test_client_update_urls_are_fetchable(isolated_client):
    for path in CLIENT_UPDATE_URLS:
        response = isolated_client.get(path)
        assert response.status_code == 200, path
        assert len(response.content) > 0, path
