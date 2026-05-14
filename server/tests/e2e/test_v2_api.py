from __future__ import annotations

from tests.conftest import make_ingest_payload


def _v2_report_payload(**overrides):
    payload = {
        "problem": "API call times out after 10s",
        "task_type": "troubleshooting",
        "goal": "reduce timeout errors",
        "target": {"product": "my-api", "component": "http-client"},
        "outcome": "success",
        "result_summary": "Increased timeout to 30s, errors stopped",
        "actions": [{"action": "Set timeout=30 in client config"}],
        "tags": ["timeout", "http-client"],
    }
    payload.update(overrides)
    return payload


def _v2_context_payload(**overrides):
    payload = {
        "problem": "API timeout",
        "task_type": "troubleshooting",
        "goal": "reduce timeout errors",
        "target": {"product": "my-api", "component": "http-client"},
        "tags": ["timeout"],
    }
    payload.update(overrides)
    return payload


def test_v2_report_creates_case_and_context_returns_group(authed_client):
    report = authed_client.post("/v2/agent/report", json=_v2_report_payload())
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["persisted"] is True
    assert body["case_assignment"]["result"] in {"auto_new", "ambiguous_new"}
    case_id = body["case_assignment"]["case"]["case_id"]
    assert body["record"]["case_id"] == case_id

    context = authed_client.post(
        "/v2/agent/context",
        json=_v2_context_payload(include_explain=True),
    )
    assert context.status_code == 200, context.text
    ctx = context.json()
    assert ctx["explain"]["ranking_config_version"]
    assert any(group["case"]["case_id"] == case_id for group in ctx["cases"])


def test_v2_report_can_attach_to_existing_case_and_create_relation(authed_client):
    first = authed_client.post("/v2/agent/report", json=_v2_report_payload()).json()
    first_record_id = first["record"]["record_id"]
    case_id = first["case_assignment"]["case"]["case_id"]

    second = authed_client.post(
        "/v2/agent/report",
        json=_v2_report_payload(
            problem="API still times out on slow network",
            result_summary="Added retry with backoff",
            case_id=case_id,
            based_on_record_ids=[first_record_id],
        ),
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["case_assignment"]["result"] == "explicit"
    assert body["record"]["case_id"] == case_id
    assert body["relations_created"][0]["to_record_id"] == first_record_id


def test_v2_stats_doctor_metrics_and_feedback(authed_client):
    authed_client.post("/v2/agent/report", json=_v2_report_payload())
    authed_client.post("/v2/agent/context", json=_v2_context_payload(include_explain=True))

    overview = authed_client.get("/v2/stats/overview")
    assert overview.status_code == 200
    assert overview.json()["records_total"] >= 1
    assert overview.json()["cases_total"] >= 1

    doctor = authed_client.get("/v2/doctor")
    assert doctor.status_code == 200
    assert doctor.json()["status"] == "ok"

    feedback = authed_client.post(
        "/v2/search/feedback",
        json={"query_hash": "abc", "judgment": "useful"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback_id"].startswith("sf_")

    search_stats = authed_client.get("/v2/stats/search").json()
    assert search_stats["search_events"] >= 1
    assert search_stats["search_feedback"] >= 1

    metrics = authed_client.get("/metrics")
    assert metrics.status_code == 200
    assert "ma3_http_requests_total" in metrics.text
    assert "ma3_case_assignment_total" in metrics.text

    topics = authed_client.get("/v2/topics")
    assert topics.status_code == 200
    assert topics.json()["products"]

    ui = authed_client.get("/ui/overview")
    assert ui.status_code == 200
    assert "ma3 Knowledge Observatory" in ui.text


def test_topics_link_to_filtered_cases_with_pagination(authed_client):
    first = authed_client.post("/v2/agent/report", json=_v2_report_payload(
        target={"product": "topic-api", "component": "client"},
        task_type="topic drilldown alpha",
        tags=["topic-filter", "shared"],
        result_summary="First topic case",
    )).json()
    second = authed_client.post("/v2/agent/report", json=_v2_report_payload(
        target={"product": "topic-api", "component": "server"},
        task_type="topic drilldown beta",
        tags=["topic-filter"],
        result_summary="Second topic case",
    )).json()
    other = authed_client.post("/v2/agent/report", json=_v2_report_payload(
        target={"product": "other-api", "component": "client"},
        task_type="other",
        tags=["other-tag"],
        result_summary="Other case",
    )).json()

    by_product = authed_client.get("/v2/cases", params={"topic_kind": "product", "topic": "topic-api", "limit": 10})
    assert by_product.status_code == 200, by_product.text
    product_ids = {case["case_id"] for case in by_product.json()}
    assert first["case_assignment"]["case"]["case_id"] in product_ids
    assert second["case_assignment"]["case"]["case_id"] in product_ids
    assert other["case_assignment"]["case"]["case_id"] not in product_ids

    by_tag_page_1 = authed_client.get("/v2/cases", params={"topic_kind": "tag", "topic": "topic-filter", "limit": 1, "offset": 0})
    by_tag_page_2 = authed_client.get("/v2/cases", params={"topic_kind": "tag", "topic": "topic-filter", "limit": 1, "offset": 1})
    assert len(by_tag_page_1.json()) == 1
    assert len(by_tag_page_2.json()) == 1
    assert by_tag_page_1.json()[0]["case_id"] != by_tag_page_2.json()[0]["case_id"]

    by_component = authed_client.get("/v2/cases", params={"topic_kind": "component", "topic": "topic-api/client", "limit": 10})
    component_ids = {case["case_id"] for case in by_component.json()}
    assert first["case_assignment"]["case"]["case_id"] in component_ids
    assert second["case_assignment"]["case"]["case_id"] not in component_ids

    topics_page = authed_client.get("/ui/topics")
    assert topics_page.status_code == 200
    assert "/ui/cases?topic_kind=" in topics_page.text
    cases_page = authed_client.get("/ui/cases?topic_kind=tag&topic=topic-filter&limit=1&offset=0")
    assert cases_page.status_code == 200
    assert "topic_kind" in cases_page.text
    assert "Next" in cases_page.text


def test_search_explain_interactive_ui_and_feedback(authed_client):
    authed_client.post("/v2/agent/report", json=_v2_report_payload(
        target={"product": "search-ui-api", "component": "client"},
        task_type="search explain ui",
        tags=["search-ui"],
        result_summary="Search explain UI seed",
    ))

    page = authed_client.get("/ui/search-explain")
    assert page.status_code == 200
    assert "Run Search Explain" in page.text
    assert "API Key (optional" in page.text
    assert "localStorage" in page.text
    assert "/v2/search/explain" in page.text
    assert "score_breakdown" in page.text
    assert "debug_candidates" in page.text
    assert "candidate_pool_limit" in page.text
    assert "/v2/search/feedback" in page.text

    explain = authed_client.post("/v2/search/explain", json={
        "problem": "search explain ui seed",
        "task_type": "search explain ui",
        "goal": "find interactive search diagnostics",
        "target": {"product": "search-ui-api", "component": "client"},
        "tags": ["search-ui"],
        "max_cases": 5,
        "max_records_per_case": 3,
        "include_explain": True,
    })
    assert explain.status_code == 200, explain.text
    body = explain.json()
    assert body["explain"]["query_hash"]
    assert body["explain"]["score_breakdown"]
    assert body["explain"]["candidate_pool_limit"] >= 50
    assert "debug_candidates" in body["explain"]

    feedback = authed_client.post("/v2/search/feedback", json={
        "query_hash": body["explain"]["query_hash"],
        "case_id": body["cases"][0]["case"]["case_id"] if body["cases"] else None,
        "judgment": "useful",
    })
    assert feedback.status_code == 200
    assert feedback.json()["feedback_id"].startswith("sf_")


def test_search_explain_metadata_rerank_prioritizes_rare_tags_and_target(authed_client):
    broad = authed_client.post("/v2/agent/report", json=_v2_report_payload(
        problem="LTP job failed during generic deployment",
        target={"product": "auth-gateway", "component": "ltp runner"},
        task_type="ltp job troubleshooting",
        goal="fix generic ltp job failure",
        tags=["ltp", "job"],
        result_summary="Generic LTP job fix",
    ))
    assert broad.status_code == 200, broad.text

    exact = authed_client.post("/v2/agent/report", json=_v2_report_payload(
        problem="LTP MPI RDMA UCX HPC-X jobssh taskrole issue",
        target={"product": "knowledge", "component": "process_protocol"},
        task_type="ltp mpi job submission troubleshooting",
        goal="fix mpi dedup job when rdma is unavailable",
        tags=["ltp", "mpi", "openmpi", "hpc-x", "jobssh", "taskrole", "rdma", "ucx", "infiniband", "cephfs"],
        result_summary="Use the MPI LTP template with correct taskrole/jobssh/UCX/RDMA settings",
    ))
    assert exact.status_code == 200, exact.text
    exact_case_id = exact.json()["case_assignment"]["case"]["case_id"]
    exact_record_id = exact.json()["record"]["record_id"]

    explain = authed_client.post("/v2/search/explain", json={
        "problem": "ltp mpi dedup job fail rdma unavailable openmpi hpc-x jobssh taskrole ucx infiniband cephfs",
        "task_type": "ltp mpi job submission troubleshooting",
        "goal": "find prior MPI/RDMA LTP troubleshooting knowledge",
        "target": {"product": "knowledge", "component": "process_protocol"},
        "tags": ["ltp", "mpi", "openmpi", "hpc-x", "jobssh", "taskrole", "rdma", "ucx", "infiniband", "cephfs"],
        "max_cases": 1,
        "max_records_per_case": 1,
        "include_explain": True,
    })
    assert explain.status_code == 200, explain.text
    body = explain.json()
    assert body["cases"][0]["case"]["case_id"] == exact_case_id

    exact_score = next(item for item in body["explain"]["score_breakdown"] if item["record_id"] == exact_record_id)
    assert exact_score["v2_boost"] > 0
    assert {"rdma", "ucx", "hpc-x", "jobssh", "taskrole"}.issubset(set(exact_score["matched_query_tags"]))
    assert exact_score["target_product_match"] is True
    assert exact_score["target_component_match"] is True
    assert any(stage["name"] == "v2_metadata_rerank" for stage in body["explain"]["stages"])
    assert body["explain"]["debug_candidates"][0]["record_id"] == exact_record_id


def test_search_explain_can_surface_l0_knowledge_with_strong_exact_tags(authed_client):
    knowledge = authed_client.post("/knowledge", json={
        "question": "How should LTP MPI RDMA UCX jobs be launched?",
        "summary": "Use the LTP MPI template with matching taskrole/jobssh/HPC-X/UCX/RDMA settings.",
        "source_type": "derived",
        "knowledge_kind": "process_protocol",
        "tags": ["ltp", "mpi", "hpc-x", "jobssh", "taskrole", "rdma", "ucx"],
    })
    assert knowledge.status_code == 200, knowledge.text
    record_id = knowledge.json()["record_id"]
    assert knowledge.json()["verification_level"] == "L0"

    explain = authed_client.post("/v2/search/explain", json={
        "problem": "ltp mpi rdma ucx hpc-x jobssh taskrole launch problem",
        "task_type": "ltp mpi job submission troubleshooting",
        "goal": "find protocol knowledge even if low verification",
        "target": {"product": "knowledge", "component": "process_protocol"},
        "tags": ["ltp", "mpi", "hpc-x", "jobssh", "taskrole", "rdma", "ucx"],
        "max_cases": 5,
        "max_records_per_case": 3,
        "include_explain": True,
    })
    assert explain.status_code == 200, explain.text
    score = next(item for item in explain.json()["explain"]["score_breakdown"] if item["record_id"] == record_id)
    assert score["v2_boost"] > 0
    assert "low verification returned due" in " ".join(score["reasons"])


def test_public_base_url_renders_agents_and_doctor(authed_client):
    from app.core import config

    object.__setattr__(config.settings, "public_base_url", "http://ma3-ltp.example:8000")
    object.__setattr__(config.settings, "instance_id", "ma3-ltp-test")
    object.__setattr__(config.settings, "git_commit", "abc123")

    agents = authed_client.get("/agents.md")
    assert agents.status_code == 200
    assert "http://ma3-ltp.example:8000" in agents.text
    assert "https://hjk41.cc" not in agents.text

    doctor = authed_client.get("/v2/doctor").json()
    assert doctor["public_base_url"] == "http://ma3-ltp.example:8000"
    assert doctor["instance_id"] == "ma3-ltp-test"
    assert doctor["git_commit"] == "abc123"


def test_operation_log_records_requests_and_agent_events(authed_client):
    from app.core import config

    authed_client.post("/v2/agent/report", json=_v2_report_payload())
    authed_client.post("/v2/agent/context", json=_v2_context_payload(include_explain=True))
    log_files = list(config.settings.op_log_dir.glob("*.jsonl"))
    assert log_files
    text = "\n".join(path.read_text(encoding="utf-8") for path in log_files)
    assert '"event_type": "http_request"' in text
    assert '"event_type": "agent_report"' in text
    assert '"event_type": "agent_context"' in text
    assert "MA3_ADMIN_KEY" not in text
