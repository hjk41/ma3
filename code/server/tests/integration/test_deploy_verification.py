from __future__ import annotations

import os
import time

import httpx
import pytest

from tests.helpers.mcp_client import McpClient

pytestmark = pytest.mark.deploy

MIN_RECORDS = int(os.environ.get("MA3_EXPECT_MIN_RECORDS", "30"))
MIN_CASES = int(os.environ.get("MA3_EXPECT_MIN_CASES", "20"))
MIN_MIHOMO_HITS = int(os.environ.get("MA3_EXPECT_MIN_MIHOMO_HITS", "1"))
MIN_LIBRARIES = int(os.environ.get("MA3_EXPECT_MIN_LIBRARIES", "2"))
EXPECTED_INSTANCE_ID = os.environ.get("MA3_EXPECT_INSTANCE_ID", "ma3-v1-202")


@pytest.fixture(scope="module")
def mcp(deploy_http, deploy_api_key) -> McpClient:
    return McpClient(deploy_http, api_key=deploy_api_key)


@pytest.fixture(scope="module", autouse=True)
def wait_for_deploy_service(deploy_base_url: str):
    deadline = time.time() + float(os.environ.get("MA3_READY_TIMEOUT", "30"))
    last_status = None
    with httpx.Client(base_url=deploy_base_url, timeout=5.0, trust_env=False) as client:
        while time.time() < deadline:
            try:
                response = client.get("/healthz")
                last_status = response.status_code
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return
            except httpx.HTTPError:
                last_status = "connection_error"
            time.sleep(1)
    pytest.fail(f"deploy service not ready at {deploy_base_url}/healthz (last={last_status})")


def test_deploy_healthz(deploy_http):
    response = deploy_http.get("/healthz")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["api_version"] == "v1"
    assert body["instance_id"] == EXPECTED_INSTANCE_ID
    assert "postgresql" in body["features"] or "sqlite" in body["features"]


def test_deploy_mcp_info_and_tools(mcp: McpClient):
    tools = {t["name"] for t in mcp.rpc("tools/list")["tools"]}
    assert "ma3_context" in tools
    assert "ma3_report" in tools
    assert "ma3_doctor" in tools

    report = next(t for t in mcp.rpc("tools/list")["tools"] if t["name"] == "ma3_report")
    assert "AgentAction" in report["inputSchema"]["$defs"]


def test_deploy_doctor_record_counts(mcp: McpClient):
    doctor = mcp.structured("ma3_doctor")
    assert doctor["status"] == "ok"
    assert doctor["records"] >= MIN_RECORDS, doctor
    assert doctor["database"] == "postgresql"


def test_deploy_whoami_sees_migrated_libraries(mcp: McpClient):
    whoami = mcp.structured("ma3_whoami")
    assert whoami["caller"]["type"] == "admin"
    assert len(whoami["readable_library_ids"]) >= MIN_LIBRARIES, whoami
    assert len(whoami["writable_library_ids"]) >= MIN_LIBRARIES, whoami


def test_deploy_legacy_knowledge_searchable(mcp: McpClient):
    context = mcp.structured(
        "ma3_context",
        {"problem": "mihomo proxy docker", "max_cases": 5, "max_records_per_case": 3},
    )
    hit_count = sum(len(group.get("records", [])) for group in context.get("cases", []))
    hit_count += len(context.get("ungrouped_records", []))
    assert hit_count >= MIN_MIHOMO_HITS, context

    explain = mcp.structured("ma3_search_explain", {"problem": "nginx reverse proxy"})
    assert explain["explain"]["hits"] >= 1, explain


def test_deploy_ma3_validate_roundtrip(mcp: McpClient):
    ok = mcp.structured(
        "ma3_validate",
        {
            "tool_name": "ma3_context",
            "arguments": {"problem": "deployment verification probe"},
        },
    )
    assert ok["ok"] is True


def test_deploy_ma3_report_dry_run(mcp: McpClient):
    body = mcp.structured(
        "ma3_report",
        {
            "problem": "deploy verification dry-run probe",
            "outcome": "success",
            "result_summary": "must not persist",
            "dry_run": True,
        },
    )
    assert body["persisted"] is False
    assert body["dry_run"] is True


def test_deploy_client_auto_upgrade_flags(mcp: McpClient, deploy_http):
    stale = mcp.structured(
        "ma3_doctor",
        {"client_version": "0.0.1", "tool_schema_version": "ma3.mcp.v0"},
    )
    assert stale["server"]["client_update_required"] is True
    assert stale["server"]["policy_refresh_required"] is True
    assert stale["server"]["mcp_reload_required"] is True

    manifest = deploy_http.get("/client/manifest.json").json()
    fresh = mcp.structured(
        "ma3_doctor",
        {
            "client_version": manifest["skill_bundle_version"],
            "tool_schema_version": manifest["tool_schema_version"],
        },
    )
    assert fresh["server"]["client_update_required"] is False
    assert fresh["server"]["mcp_reload_required"] is False

    assert deploy_http.get("/client/mcp-tools.json").status_code == 200
    policy = deploy_http.get("/client/templates/ma3-agent-policy.mdc").text
    assert "ma3-client.json" in policy
    assert "sync_ma3_client" in policy


@pytest.mark.deploy
def test_deploy_eval_claude_db_api_key(deploy_http):
    """Regression: eval tenant keys in api_keys table must authenticate tools/call."""
    key = os.environ.get("MA3_EVAL_CLAUDE_KEY", "").strip()
    if not key:
        pytest.skip("MA3_EVAL_CLAUDE_KEY not set (eval profile key on deploy host)")
    mcp = McpClient(deploy_http, api_key=key)
    who = mcp.structured("ma3_whoami", {"client_version": "0.0.0", "tool_schema_version": "ma3.mcp.v0"})
    assert who["caller"]["type"] == "api_key"
    assert who["caller"]["via"] == "db_api_key"
    assert who["writable_library_ids"], who
    ctx = mcp.structured("ma3_context", {"problem": "deploy eval key auth probe", "client_version": "0.0.0"})
    assert "cases" in ctx


@pytest.mark.postgres
def test_deploy_database_migration_state():
    database_url = os.environ.get("MA3_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("MA3_DATABASE_URL not set for postgres checks")

    import psycopg

    with psycopg.connect(database_url) as conn:
        legacy_records = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='legacy_records'"
        ).fetchone()[0]
        assert legacy_records == 1

        migrated_records = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        migrated_cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        legacy_count = conn.execute("SELECT COUNT(*) FROM legacy_records").fetchone()[0]

    assert migrated_records >= MIN_RECORDS
    assert migrated_cases >= MIN_CASES
    assert legacy_count >= MIN_RECORDS
