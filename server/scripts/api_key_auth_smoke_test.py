from pathlib import Path
import os
import shutil
import sys
from uuid import uuid4

TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp_auth_tests"
run_dir = TMP_ROOT / f"run_{uuid4().hex}"
run_dir.mkdir(parents=True, exist_ok=True)

os.environ["MA3_API_KEY"] = "test-ma3-key"
os.environ["MA3_DB_PATH"] = str(run_dir / "ma3.db")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    try:
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 200
            assert client.get("/agents.md").status_code == 200

            search_payload = {
                "problem": "reduce codex approval prompts on windows powershell",
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
            assert client.post("/search", json=search_payload).status_code == 200

            agent_payload = {
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
                "observations": ["auth smoke test"],
                "actions": [{"action": "checked auth behavior", "note": None}],
                "outcome": "success",
                "result_summary": "authorized write succeeded",
                "evidence": [],
                "applicable_if": [],
                "not_applicable_if": [],
                "dry_run": True,
                "draft_only": False,
            }

            unauthorized = client.post("/agent/ingest", json=agent_payload)
            assert unauthorized.status_code == 401, unauthorized.text

            authorized = client.post(
                "/agent/ingest",
                json=agent_payload,
                headers={"X-API-Key": "test-ma3-key"},
            )
            assert authorized.status_code == 200, authorized.text

            record_payload = {
                "title": "API key auth smoke test record",
                "problem_family": "auth-check",
                "summary": "Tests protected write access.",
                "claim": "Protected writes should require a valid API key.",
                "target": {"product": "ma3", "component": "api-auth"},
                "environment": {
                    "os": "windows",
                    "shell": "powershell",
                    "runtime": "python",
                    "sandbox": "workspace-write",
                    "workspace_boundary": "workspace-write",
                    "network_profile": "restricted",
                },
                "versions": {"agent": "1.0.0", "target": "0.1.0"},
                "steps": [{"order": 1, "action": "Send request with bearer token.", "note": None}],
                "result": {"outcome": "success", "summary": "Request accepted.", "details": []},
                "evidence": [],
                "applicable_if": [],
                "not_applicable_if": [],
                "status": "active",
                "verification_level": "L1",
                "visibility_scope": "public",
                "risk_level": "low",
                "execution_mode": "review_before_apply",
                "source_type": "auth_smoke_test",
            }
            record_response = client.post(
                "/records",
                json=record_payload,
                headers={"Authorization": "Bearer test-ma3-key"},
            )
            assert record_response.status_code == 200, record_response.text
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

    print("api key auth smoke test passed")


if __name__ == "__main__":
    main()
