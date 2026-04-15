import re
from urllib.parse import urlparse

import httpx

from http_server_harness import managed_ma3_server


PROMPT_TEMPLATE = "按 {url} 的说明，接入 ma3 系统"


def extract_agents_doc_url(prompt: str) -> str:
    match = re.search(r"https?://[^\s]+/agents\.md\b", prompt)
    if not match:
        raise AssertionError(f"agents.md URL not found in prompt: {prompt}")
    return match.group(0)


class PromptBootstrappedAgent:
    def __init__(self, prompt: str):
        self.prompt = prompt
        self.agents_doc_url = extract_agents_doc_url(prompt)
        parsed = urlparse(self.agents_doc_url)
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.client = httpx.Client(timeout=10.0)
        self.agents_doc = ""

    def close(self) -> None:
        self.client.close()

    def bootstrap(self) -> None:
        response = self.client.get(self.agents_doc_url)
        assert response.status_code == 200, response.text
        self.agents_doc = response.text
        assert "GET /healthz" in self.agents_doc
        assert "POST /search" in self.agents_doc
        assert "POST /agent/ingest" in self.agents_doc

        health = self.client.get(f"{self.base_url}/healthz")
        assert health.status_code == 200, health.text

    def search(self, problem: str) -> dict:
        payload = {
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
        response = self.client.post(f"{self.base_url}/search", json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    def get_record(self, record_id: str) -> dict:
        response = self.client.get(
            f"{self.base_url}/records/{record_id}",
            params={"allowed_scopes": "public"},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def ingest(self, payload: dict) -> dict:
        response = self.client.post(f"{self.base_url}/agent/ingest", json=payload)
        assert response.status_code == 200, response.text
        return response.json()


def case_prompt_only_bootstrap_to_draft_write(base_url: str) -> str:
    prompt = PROMPT_TEMPLATE.format(url=f"{base_url}/agents.md")
    agent = PromptBootstrappedAgent(prompt)
    try:
        agent.bootstrap()
        search_json = agent.search(
            "reduce claude code approval prompts on windows powershell"
        )
        assert search_json["primary_records"], "expected reusable records"

        record_id = search_json["primary_records"][0]["record"]["record_id"]
        record_json = agent.get_record(record_id)
        assert record_json["record_id"] == record_id

        ingest_json = agent.ingest(
            {
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
                    "all interaction started from the single user prompt",
                ],
                "actions": [
                    {"action": "extracted the agents.md URL from the prompt", "note": None},
                    {"action": "read the bootstrap document", "note": None},
                    {"action": "searched ma3 and selected a record", "note": record_id},
                ],
                "outcome": "success",
                "result_summary": "the prompt-only bootstrap path reached ma3 and produced a draft record",
                "evidence": [
                    {
                        "kind": "manual_observation",
                        "summary": "a single prompt was enough to bootstrap the agent workflow",
                        "ref": None,
                    }
                ],
                "based_on_record_id": record_id,
                "feedback_type": "derived_record",
                "relation_type": "derived_from",
                "applicable_if": ["agent can fetch URLs and call HTTP APIs"],
                "not_applicable_if": ["agent cannot read URLs or cannot send HTTP requests"],
                "dry_run": False,
                "draft_only": True,
            }
        )
        assert ingest_json["persisted"] is True
        assert ingest_json["draft_only"] is True
        assert ingest_json["feedback"] is None
        assert ingest_json["relation"] is None
        assert ingest_json["record"]["status"] == "draft"
    finally:
        agent.close()

    return "case_prompt_only_bootstrap_to_draft_write passed"


def case_prompt_only_bootstrap_to_preview(base_url: str) -> str:
    prompt = PROMPT_TEMPLATE.format(url=f"{base_url}/agents.md")
    agent = PromptBootstrappedAgent(prompt)
    try:
        agent.bootstrap()
        ingest_json = agent.ingest(
            {
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
                    "the bootstrap document said to prefer dry_run when uncertainty or risk exists",
                ],
                "actions": [
                    {"action": "extracted the agents.md URL from the prompt", "note": None},
                    {"action": "read the bootstrap document", "note": None},
                    {"action": "prepared a high-risk write-back preview", "note": None},
                ],
                "outcome": "success",
                "result_summary": "previewed a sensitive write-back instead of persisting it",
                "evidence": [],
                "based_on_record_id": None,
                "feedback_type": None,
                "relation_type": None,
                "applicable_if": [],
                "not_applicable_if": [],
                "dry_run": True,
                "draft_only": False,
            }
        )
        assert ingest_json["persisted"] is False
        assert ingest_json["dry_run"] is True
        assert ingest_json["requires_manual_review"] is True
        assert ingest_json["record"]["risk_level"] == "critical"
    finally:
        agent.close()

    return "case_prompt_only_bootstrap_to_preview passed"


def main() -> None:
    with managed_ma3_server(port=8899) as server:
        base_url = server["base_url"]
        results = [
            case_prompt_only_bootstrap_to_draft_write(base_url),
            case_prompt_only_bootstrap_to_preview(base_url),
        ]

    for line in results:
        print(line)
    print("prompt bootstrap bridge tests passed")


if __name__ == "__main__":
    main()
