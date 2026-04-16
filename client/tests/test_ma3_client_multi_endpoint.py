from __future__ import annotations

import io
import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def ma3_client_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "skills" / "ma3" / "scripts" / "ma3_client.py"
    )
    spec = importlib.util.spec_from_file_location("ma3_client_under_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    spec.loader.exec_module(module)
    sys.stdout = original_stdout
    sys.stderr = original_stderr
    return module


def _match(record_id: str, score: float, endpoint: str) -> dict:
    return {
        "record": {"record_id": record_id, "title": f"Record from {endpoint}"},
        "match_score": score,
    }


def test_load_endpoints_prefers_endpoints_json_for_multiple_servers(
    ma3_client_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(ma3_client_module, "_plugin_root", lambda: str(tmp_path))
    monkeypatch.setenv("MA3_BASE_URL", "https://env.example.com")
    monkeypatch.setenv("MA3_API_KEY", "env-token")

    endpoints_path = tmp_path / "endpoints.json"
    endpoints_path.write_text(
        json.dumps(
            [
                {
                    "name": "public",
                    "base_url": "https://public.example.com/",
                    "api_key": "tok-public",
                    "library_id": "lib-public",
                },
                {
                    "name": "team-a",
                    "base_url": "https://team-a.example.com",
                    "api_key": "tok-team-a",
                    "admin_key": "admin-team-a",
                    "library_id": "lib-team-a",
                },
            ]
        ),
        encoding="utf-8",
    )

    endpoints = ma3_client_module.load_endpoints()

    assert [ep.name for ep in endpoints] == ["public", "team-a"]
    assert [ep.base_url for ep in endpoints] == [
        "https://public.example.com",
        "https://team-a.example.com",
    ]
    assert [ep.library_id for ep in endpoints] == ["lib-public", "lib-team-a"]
    assert endpoints[1].admin_key == "admin-team-a"


def test_cmd_search_fans_out_across_servers_dedupes_and_keeps_partial_errors(
    ma3_client_module, monkeypatch, capsys
):
    endpoints = [
        ma3_client_module.Endpoint(name="public", base_url="https://public.example.com"),
        ma3_client_module.Endpoint(name="team-a", base_url="https://team-a.example.com"),
        ma3_client_module.Endpoint(name="broken", base_url="https://broken.example.com"),
    ]

    responses = {
        "public": (
            200,
            {
                "primary_records": [
                    _match("rec-shared", 0.95, "public"),
                    _match("rec-public", 0.60, "public"),
                ],
                "contrasting_records": [],
            },
        ),
        "team-a": (
            200,
            {
                "primary_records": [
                    _match("rec-shared", 0.80, "team-a"),
                    _match("rec-team-a", 0.85, "team-a"),
                ],
                "contrasting_records": [],
            },
        ),
        "broken": (503, {"error": "temporary outage"}),
    }

    def fake_request_with_retry(ep, method, path, payload=None, timeout=30, retries=1):
        assert method == "POST"
        assert path == "/search"
        return responses[ep.name]

    monkeypatch.setattr(ma3_client_module, "_request_with_retry", fake_request_with_retry)

    rc = ma3_client_module.cmd_search(endpoints, {"problem": "test multi-server search"})
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert [item["record"]["record_id"] for item in out["primary_records"]] == [
        "rec-shared",
        "rec-team-a",
        "rec-public",
    ]
    assert out["primary_records"][0]["_source_endpoint"] == "public"
    assert out["primary_records"][1]["_source_endpoint"] == "team-a"
    assert out["_endpoint_errors"] == {"broken": {"status": 503, "body": {"error": "temporary outage"}}}


def test_cmd_get_record_falls_through_servers_until_found(ma3_client_module, monkeypatch, capsys):
    endpoints = [
        ma3_client_module.Endpoint(name="public", base_url="https://public.example.com"),
        ma3_client_module.Endpoint(name="team-a", base_url="https://team-a.example.com"),
    ]

    def fake_request(self, method, path, payload=None, use_admin=False):
        assert method == "GET"
        assert path == "/records/rec-team-a"
        if self.name == "public":
            return 404, {"error": "not found"}
        return 200, {"record_id": "rec-team-a", "title": "Stored in team-a"}

    monkeypatch.setattr(ma3_client_module.Endpoint, "request", fake_request)

    rc = ma3_client_module.cmd_get_record(endpoints, "rec-team-a")
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["record_id"] == "rec-team-a"
    assert out["_source_endpoint"] == "team-a"


def test_cmd_ingest_routes_to_matching_library_id(ma3_client_module, monkeypatch, capsys):
    endpoints = [
        ma3_client_module.Endpoint(
            name="team-a",
            base_url="https://team-a.example.com",
            api_key="tok-a",
            library_id="lib-a",
        ),
        ma3_client_module.Endpoint(
            name="team-b",
            base_url="https://team-b.example.com",
            api_key="tok-b",
            library_id="lib-b",
        ),
    ]
    called = []

    def fake_request(self, method, path, payload=None, use_admin=False):
        called.append((self.name, method, path, payload, use_admin))
        return 201, {"record": {"record_id": "rec-team-b"}}

    monkeypatch.setattr(ma3_client_module.Endpoint, "request", fake_request)

    rc = ma3_client_module.cmd_ingest(
        endpoints,
        {"problem": "write into the team-b library"},
        endpoint_name=None,
        library_id="lib-b",
    )
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert called == [
        ("team-b", "POST", "/agent/ingest", {"problem": "write into the team-b library"}, False)
    ]
    assert out["_endpoint"] == "team-b"
    assert out["_library_id"] == "lib-b"


def test_pick_ingest_endpoint_requires_disambiguation_when_multiple_servers_are_writable(
    ma3_client_module,
):
    endpoints = [
        ma3_client_module.Endpoint(name="team-a", base_url="https://team-a.example.com", api_key="tok-a"),
        ma3_client_module.Endpoint(name="team-b", base_url="https://team-b.example.com", api_key="tok-b"),
    ]

    with pytest.raises(SystemExit, match="Multiple endpoints have API keys configured"):
        ma3_client_module._pick_ingest_endpoint(endpoints, None)
