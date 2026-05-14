from __future__ import annotations

from app.storage.v2_repositories import CaseRepository, V2RecordRepository
from scripts.migrate_v1_to_v2_cases import run_migration
from tests.conftest import make_ingest_payload


def _ingest(authed_client, **overrides) -> str:
    response = authed_client.post("/agent/ingest", json=make_ingest_payload(**overrides))
    assert response.status_code == 200, response.text
    return response.json()["record"]["record_id"]


def test_v1_to_v2_migration_dry_run_apply_and_idempotency(authed_client, tmp_path):
    first = _ingest(
        authed_client,
        problem="API call times out after 10s",
        result_summary="Increased timeout to 30s",
        tags=["timeout", "http-client"],
    )
    second = _ingest(
        authed_client,
        problem="API still times out on slow network",
        result_summary="Added retry with backoff",
        based_on_record_id=first,
        tags=["timeout", "http-client"],
    )
    third = _ingest(
        authed_client,
        problem="Worker queue gets stuck",
        task_type="queue recovery",
        goal="unstick queue",
        target={"product": "worker", "component": "queue"},
        result_summary="Restarted the stuck consumer",
        tags=["queue", "consumer"],
    )
    fourth = _ingest(
        authed_client,
        problem="Worker queue gets stuck again",
        task_type="queue recovery",
        goal="unstick queue",
        target={"product": "worker", "component": "queue"},
        result_summary="Cleared poison message and restarted consumer",
        tags=["consumer", "queue"],
    )

    before = authed_client.get("/v2/stats/overview").json()
    assert before["records_total"] == 4
    assert before["cases_total"] == 0
    assert before["case_coverage"]["records_with_case"] == 0

    dry_report = run_migration(apply=False, report_path=str(tmp_path / "dry.json"))
    assert dry_report["mode"] == "dry_run"
    assert dry_report["records_total"] == 4
    assert dry_report["cases_computed"] == 2
    assert dry_report["records_assigned"] == 4
    assert CaseRepository().count(None) == 0

    apply_report = run_migration(apply=True, report_path=str(tmp_path / "apply.json"))
    assert apply_report["mode"] == "apply"
    assert apply_report["cases_computed"] == 2
    assert apply_report["records_assigned"] == 4
    case_ids = {case["case_id"] for case in apply_report["cases"]}
    assert len(case_ids) == 2

    after = authed_client.get("/v2/stats/overview").json()
    assert after["cases_total"] == 2
    assert after["case_coverage"]["records_with_case"] == 4
    assert after["case_coverage"]["percentage"] == 100.0

    api_case = next(case for case in apply_report["cases"] if case["record_count"] == 2 and case["target"]["product"] == "my-api")
    case_response = authed_client.get(f"/v2/cases/{api_case['case_id']}")
    assert case_response.status_code == 200, case_response.text
    grouped = case_response.json()
    assert {record["record_id"] for record in grouped["records"]} == {first, second}
    assert any(rel["to_record_id"] == first and rel["from_record_id"] == second for rel in grouped["relations"])

    records_by_case = V2RecordRepository().records_for_cases(case_ids, limit_per_case=10)
    assert {record.record_id for records in records_by_case.values() for record in records} == {first, second, third, fourth}

    rerun = run_migration(apply=True, report_path=str(tmp_path / "rerun.json"))
    assert {case["case_id"] for case in rerun["cases"]} == case_ids
    assert authed_client.get("/v2/stats/overview").json()["cases_total"] == 2

    context = authed_client.post(
        "/v2/agent/context",
        json={
            "problem": "API timeout",
            "task_type": "troubleshooting",
            "goal": "reduce timeout errors",
            "target": {"product": "my-api", "component": "http-client"},
            "tags": ["timeout"],
            "include_explain": True,
        },
    )
    assert context.status_code == 200, context.text
    assert any(group["case"]["case_id"] == api_case["case_id"] for group in context.json()["cases"])
