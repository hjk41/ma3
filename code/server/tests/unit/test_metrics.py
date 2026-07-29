"""Phase 1 Prometheus metrics tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import metrics as metrics_mod
from app.core.config import settings
from app.main import app


def test_metrics_disabled_by_default():
    assert settings.metrics_enabled is False
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 404


def test_metrics_endpoint_and_http_counter(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    # Reset build-info latch so labels refresh under enabled flag
    metrics_mod._build_info_set = False  # noqa: SLF001

    client = TestClient(app)
    r0 = client.get("/healthz")
    assert r0.status_code == 200

    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "ma3_http_requests_total" in body
    assert 'route="/healthz"' in body or 'route="/healthz"' in body.replace("\\", "")
    assert "ma3_build_info" in body
    assert "ma3_http_requests_in_flight" in body


def test_mcp_tool_metrics(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "dev_auth", True)
    metrics_mod._build_info_set = False  # noqa: SLF001

    client = TestClient(app)
    r = client.post(
        "/mcp",
        headers={"X-API-Key": settings.dev_api_key},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ma3_whoami", "arguments": {}},
        },
    )
    assert r.status_code == 200
    assert "error" not in r.json() or r.json().get("result")

    metrics_body = client.get("/metrics").text
    assert "ma3_mcp_tool_calls_total" in metrics_body
    assert 'tool="ma3_whoami"' in metrics_body
    assert 'outcome="ok"' in metrics_body
    assert "ma3_mcp_tool_duration_seconds" in metrics_body
