from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def _build_search_payload(problem: str) -> dict:
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


def _exercise_agents_bootstrap(client: TestClient) -> None:
    agents_doc = client.get("/agents.md")
    assert agents_doc.status_code == 200, agents_doc.text
    doc_text = agents_doc.text
    assert "POST /search" in doc_text
    assert "GET /records/{record_id}" in doc_text
    assert "POST /agent/ingest" in doc_text

    health = client.get("/healthz")
    assert health.status_code == 200, health.text


def case_search_then_read_then_write_success(client: TestClient) -> str:
    search = client.post(
        "/search",
        json=_build_search_payload("reduce claude code approval prompts on windows powershell"),
    )
    assert search.status_code == 200, search.text
    search_json = search.json()
    assert search_json["primary_records"], "expected a reusable primary record"

    best = search_json["primary_records"][0]
    best_record_id = best["record"]["record_id"]

    record = client.get(f"/records/{best_record_id}?allowed_scopes=public")
    assert record.status_code == 200, record.text
    record_json = record.json()
    assert record_json["record_id"] == best_record_id

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
            "searched ma3 first and reused the top matching record",
            "prompt frequency dropped after the config update",
        ],
        "actions": [
            {
                "action": "searched ma3 for prior approval-reduction records",
                "note": f"selected {best_record_id} as the best match",
            },
            {
                "action": "updated the local Claude Code approval configuration",
                "note": "kept the sandbox boundary unchanged",
            },
            {
                "action": "reran the same workflow",
                "note": None,
            },
        ],
        "outcome": "success",
        "result_summary": "approval prompt frequency dropped after reusing the recommended config pattern",
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
        "not_applicable_if": ["hosted environment with a different config schema"],
        "dry_run": False,
        "draft_only": False,
    }
    ingest = client.post("/agent/ingest", json=ingest_payload)
    assert ingest.status_code == 200, ingest.text
    ingest_json = ingest.json()
    assert ingest_json["persisted"] is True
    assert ingest_json["requires_manual_review"] is False
    assert ingest_json["feedback"] is not None
    assert ingest_json["relation"] is not None

    return "case_search_then_read_then_write_success passed"


def case_search_conflict_then_write_derivative(client: TestClient) -> str:
    search = client.post(
        "/search",
        json=_build_search_payload("approval_policy ignored in claude code powershell"),
    )
    assert search.status_code == 200, search.text
    search_json = search.json()
    assert search_json["contrasting_records"], "expected at least one contrasting record"

    failed = search_json["contrasting_records"][0]
    failed_record_id = failed["record"]["record_id"]

    ingest_payload = {
        "problem": "approval_policy was ignored in claude code powershell",
        "task_type": "permission_reduction",
        "goal": "find a working config key after the first suggestion failed",
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
            "the first config key behaved like the known failure case from ma3",
        ],
        "actions": [
            {
                "action": "searched ma3 and reviewed the contrasting failure record",
                "note": failed_record_id,
            },
            {
                "action": "switched from approval_policy to approval_mode=full-auto",
                "note": "kept the same environment and workflow",
            },
        ],
        "outcome": "success",
        "result_summary": "moving away from approval_policy recovered the workflow",
        "evidence": [
            {
                "kind": "manual_observation",
                "summary": "the previously ineffective key was replaced and the workflow improved",
                "ref": None,
            }
        ],
        "based_on_record_id": failed_record_id,
        "feedback_type": "derived_record",
        "relation_type": "derived_from",
        "applicable_if": ["same config family and same shell environment"],
        "not_applicable_if": ["future client versions that already support approval_policy"],
        "dry_run": False,
        "draft_only": False,
    }
    ingest = client.post("/agent/ingest", json=ingest_payload)
    assert ingest.status_code == 200, ingest.text
    ingest_json = ingest.json()
    assert ingest_json["persisted"] is True
    assert ingest_json["feedback"] is not None
    assert ingest_json["relation"] is not None
    assert ingest_json["relation"]["to_record_id"] == failed_record_id

    return "case_search_conflict_then_write_derivative passed"


def case_high_risk_preview_requires_review(client: TestClient) -> str:
    search = client.post(
        "/search",
        json=_build_search_payload("remote exec export credential bundle from production"),
    )
    assert search.status_code == 200, search.text

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
        "observations": [
            "this should not be auto-applied without review",
        ],
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
    ingest = client.post("/agent/ingest", json=ingest_payload)
    assert ingest.status_code == 200, ingest.text
    ingest_json = ingest.json()
    assert ingest_json["persisted"] is False
    assert ingest_json["dry_run"] is True
    assert ingest_json["requires_manual_review"] is True
    assert ingest_json["record"]["status"] == "draft"
    assert ingest_json["record"]["risk_level"] == "critical"
    assert ingest_json["record"]["visibility_scope"] == "private"

    return "case_high_risk_preview_requires_review passed"


def main() -> None:
    with TestClient(app) as client:
        _exercise_agents_bootstrap(client)
        results = [
            case_search_then_read_then_write_success(client),
            case_search_conflict_then_write_derivative(client),
            case_high_risk_preview_requires_review(client),
        ]

    for line in results:
        print(line)
    print("claude code integration cases passed")


if __name__ == "__main__":
    main()
