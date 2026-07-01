from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app, raise_server_exceptions=True)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_observatory_stats_json():
    r = client.get("/ui/observatory/stats.json")
    assert r.status_code == 200
    stats = r.json()
    assert "organizations" in stats
    assert "libraries" in stats
    assert "users" in stats
    assert "knowledge" in stats
    assert stats["organizations"]["count"] >= 1
    assert stats["libraries"]["count"] >= 1
    assert stats["knowledge"]["records"]["total"] >= 0


def test_observatory_home_shows_stats():
    r = client.get("/ui/observatory/")
    assert r.status_code == 200
    text = r.text
    assert "Organizations" in text
    assert "Libraries" in text
    assert "Users" in text
    assert "知识分布" in text


def test_mcp_tools_list():
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert r.status_code == 200
    tools = {t["name"] for t in r.json()["result"]["tools"]}
    assert "ma3_context" in tools
    assert "ma3_report" in tools


def test_ma3_report_active_default():
    r = client.post(
        "/mcp",
        headers={"X-API-Key": "ma3dev"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "ma3_report",
                "arguments": {
                    "problem": "test problem",
                    "outcome": "resolved",
                    "result_summary": "skeleton write test",
                },
            },
        },
    )
    assert r.status_code == 200
    body = r.json()["result"]["structuredContent"]
    assert body["persisted"] is True
    assert body["status"] == "active"
    assert "server" in body
    assert body["server"]["skill_bundle_version"]
