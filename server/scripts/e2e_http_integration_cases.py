import httpx

from http_server_harness import managed_ma3_server


def _search_payload(problem: str) -> dict:
    return {
        "problem": problem,
        "query_intent": "find_verified_fix",
        "task_type": "permission_reduction",
        "target": {"product": "claude-code", "component": "approval-config"},
        "goal": "reduce approval prompts without disabling safety boundaries",
        "environment": {
            "os": "windows",
            "shell": "powershell",
            "runtime": None,
            "sandbox": "elevated",
            "workspace_boundary": "workspace-write",
            "network_profile": "restricted",
        },
        "versions": {"agent": "0.119.0", "target": "0.119.0"},
        "observations": [],
        "constraints": [],
        "config_excerpt": None,
        "allowed_scopes": ["public"],
    }


def case_http_agents_bootstrap(client: httpx.Client, base_url: str) -> str:
    agents_doc = client.get(f"{base_url}/agents.md")
    assert agents_doc.status_code == 200, agents_doc.text
    assert "POST /search" in agents_doc.text
    assert "POST /agent/ingest" in agents_doc.text

    health = client.get(f"{base_url}/healthz")
    assert health.status_code == 200, health.text
    health_json = health.json()
    assert health_json["status"] == "ok"
    assert "ma3" in health_json["service"]

    return "case_http_agents_bootstrap passed"


def case_http_search_read_write(client: httpx.Client, base_url: str) -> str:
    search = client.post(
        f"{base_url}/search",
        json=_search_payload("reduce claude code approval prompts on windows powershell"),
    )
    assert search.status_code == 200, search.text
    search_json = search.json()
    assert search_json["primary_records"], "expected primary records"

    best_record_id = search_json["primary_records"][0]["record"]["record_id"]
    record = client.get(f"{base_url}/records/{best_record_id}", params={"allowed_scopes": "public"})
    assert record.status_code == 200, record.text

    ingest_payload = {
        "problem": "reduce claude code approval prompts on windows powershell",
        "task_type": "permission_reduction",
        "goal": "reduce approval prompts without disabling safety boundaries",
        "target": {"product": "claude-code", "component": "approval-config"},
        "environment": {
            "os": "windows",
            "shell": "powershell",
            "runtime": None,
            "sandbox": "elevated",
            "workspace_boundary": "workspace-write",
            "network_profile": "restricted",
        },
        "versions": {"agent": "0.119.0", "target": "0.119.0"},
        "observations": [
            "followed the HTTP-served ma3 bootstrap document",
            "reused the top matching record before trying a new change",
        ],
        "actions": [
            {"action": "loaded /agents.md over HTTP", "note": None},
            {"action": "searched ma3", "note": best_record_id},
            {
                "action": "updated the local Claude Code approval configuration",
                "note": "kept the sandbox boundary unchanged",
            },
        ],
        "outcome": "success",
        "result_summary": "the HTTP-discovered recommendation reduced approval prompts",
        "evidence": [
            {
                "kind": "manual_observation",
                "summary": "the same workflow completed with fewer approval interruptions",
                "ref": None,
            }
        ],
        "based_on_record_id": best_record_id,
        "feedback_type": "derived_record",
        "relation_type": "derived_from",
        "applicable_if": ["Windows PowerShell local workflow"],
        "not_applicable_if": ["different config schema"],
        "dry_run": False,
        "draft_only": False,
    }
    ingest = client.post(f"{base_url}/agent/ingest", json=ingest_payload)
    assert ingest.status_code == 200, ingest.text
    ingest_json = ingest.json()
    assert ingest_json["persisted"] is True
    assert ingest_json["feedback"] is not None
    assert ingest_json["relation"] is not None

    return "case_http_search_read_write passed"


def case_http_high_risk_preview(client: httpx.Client, base_url: str) -> str:
    ingest_payload = {
        "problem": "export credential bundle from the production box after remote exec",
        "task_type": "incident_response",
        "goal": "collect secrets quickly",
        "target": {"product": "claude-code", "component": "ops-response"},
        "environment": {
            "os": "linux",
            "shell": "bash",
            "runtime": "python",
            "sandbox": "none",
            "workspace_boundary": "host-root",
            "network_profile": "production",
        },
        "versions": {"agent": "0.119.0", "target": "2026.04"},
        "observations": ["this should route to manual review"],
        "actions": [
            {"action": "ssh into production host", "note": None},
            {"action": "remote exec export credential archive", "note": None},
        ],
        "outcome": "success",
        "result_summary": "captured the secrets bundle for manual triage",
        "evidence": [],
        "based_on_record_id": None,
        "feedback_type": None,
        "relation_type": None,
        "applicable_if": [],
        "not_applicable_if": [],
        "dry_run": True,
        "draft_only": False,
    }
    ingest = client.post(f"{base_url}/agent/ingest", json=ingest_payload)
    assert ingest.status_code == 200, ingest.text
    ingest_json = ingest.json()
    assert ingest_json["persisted"] is False
    assert ingest_json["requires_manual_review"] is True
    assert ingest_json["record"]["risk_level"] == "critical"

    return "case_http_high_risk_preview passed"


def main() -> None:
    with managed_ma3_server(port=8899) as server:
        base_url = server["base_url"]
        with httpx.Client(timeout=10.0) as client:
            results = [
                case_http_agents_bootstrap(client, base_url),
                case_http_search_read_write(client, base_url),
                case_http_high_risk_preview(client, base_url),
            ]

    for line in results:
        print(line)
    print("e2e http integration cases passed")


if __name__ == "__main__":
    main()
