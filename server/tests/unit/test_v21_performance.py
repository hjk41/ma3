from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import config
from app.models.common import TargetRef
from app.models.enums import FeedbackType, RelationType
from app.models.feedback import Feedback, ResultSummary
from app.models.record import Record
from app.models.relation import RecordRelation
from app.storage import db as db_module
from app.storage.repositories import FeedbackRepository, RecordRepository, RelationRepository
from tests.conftest import make_ingest_payload, make_search_payload


def test_batch_feedback_and_relations_group_by_record():
    now = "2026-01-01T00:00:00+00:00"
    rec1 = Record(
        record_id="vk_perf_1",
        library_id=None,
        title="ma3 perf one",
        problem_family="perf",
        summary="one",
        claim="one",
        target=TargetRef(product="ma3"),
        result=ResultSummary(outcome="success", summary="one"),
        created_at=now,
        updated_at=now,
    )
    rec2 = Record(
        record_id="vk_perf_2",
        library_id=None,
        title="ma3 perf two",
        problem_family="perf",
        summary="two",
        claim="two",
        target=TargetRef(product="ma3"),
        result=ResultSummary(outcome="success", summary="two"),
        created_at=now,
        updated_at=now,
    )
    repo = RecordRepository()
    repo.insert(rec1)
    repo.insert(rec2)

    FeedbackRepository().insert(Feedback(
        feedback_id="fb_perf_1",
        record_id=rec1.record_id,
        feedback_type=FeedbackType.success_reuse,
        summary="worked",
        result=ResultSummary(outcome="success", summary="worked"),
        created_at=now,
    ))
    RelationRepository().insert(RecordRelation(
        relation_id="rel_perf_1",
        from_record_id=rec2.record_id,
        to_record_id=rec1.record_id,
        relation_type=RelationType.derived_from,
        summary="derived",
        created_at=now,
    ))

    feedback = FeedbackRepository().list_by_record_ids({rec1.record_id, rec2.record_id})
    relations = RelationRepository().list_by_record_ids({rec1.record_id, rec2.record_id})

    assert [item.feedback_id for item in feedback[rec1.record_id]] == ["fb_perf_1"]
    assert feedback[rec2.record_id] == []
    assert [item.relation_id for item in relations[rec1.record_id]] == ["rel_perf_1"]
    assert [item.relation_id for item in relations[rec2.record_id]] == ["rel_perf_1"]


def test_search_uses_batch_feedback_relation_loading(authed_client, monkeypatch):
    first = authed_client.post("/agent/ingest", json=make_ingest_payload(
        problem="ma3 performance search timeout",
        target={"product": "ma3", "component": "search"},
        tags=["ma3", "performance", "search"],
    )).json()
    authed_client.post("/agent/ingest", json=make_ingest_payload(
        problem="ma3 performance followup",
        target={"product": "ma3", "component": "search"},
        tags=["ma3", "performance", "search"],
        based_on_record_id=first["record"]["record_id"],
    ))

    def forbidden(*args, **kwargs):  # pragma: no cover - only used on failure
        raise AssertionError("per-record list_by_record should not be called by search")

    monkeypatch.setattr(FeedbackRepository, "list_by_record", forbidden)
    monkeypatch.setattr(RelationRepository, "list_by_record", forbidden)

    resp = authed_client.post("/search", json=make_search_payload(
        problem="ma3 performance search",
        query_intent="find_verified_fix",
        task_type="performance",
        target={"product": "ma3", "component": "search"},
        goal="find search performance records",
        tags=["ma3", "performance", "search"],
        max_primary=5,
    ))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["primary_records"]) >= 1


def test_metrics_and_stats_include_v21_search_perf(authed_client):
    authed_client.post("/agent/ingest", json=make_ingest_payload(
        problem="ma3 stage timing metrics",
        target={"product": "ma3", "component": "metrics"},
        tags=["ma3", "metrics", "stage-timing"],
    ))
    search = authed_client.post("/search", json=make_search_payload(
        problem="ma3 stage timing metrics",
        query_intent="find_verified_fix",
        task_type="observability",
        target={"product": "ma3", "component": "metrics"},
        goal="find metrics stage timing",
        tags=["ma3", "metrics", "stage-timing"],
    ))
    assert search.status_code == 200

    metrics = authed_client.get("/metrics").text
    assert "ma3_search_stage_duration_seconds_count" in metrics
    assert "ma3_db_queries_total" in metrics
    assert "ma3_db_connection_checkouts_total" in metrics

    stats = authed_client.get("/v2/stats/search").json()
    assert stats["window_hours"] == 48
    assert any(item["route"] == "/search" for item in stats["by_hour"])


def test_v2_search_explain_includes_performance_stage(authed_client):
    authed_client.post("/v2/agent/report", json={
        "problem": "ma3 explain performance stage",
        "task_type": "performance",
        "goal": "record explain performance",
        "target": {"product": "ma3", "component": "search"},
        "outcome": "success",
        "result_summary": "explain performance seed",
        "actions": [{"action": "seed"}],
        "tags": ["ma3", "performance", "explain"],
    })
    resp = authed_client.post("/v2/search/explain", json={
        "problem": "ma3 explain performance stage",
        "task_type": "performance",
        "goal": "find explain performance",
        "target": {"product": "ma3", "component": "search"},
        "tags": ["ma3", "performance", "explain"],
        "include_explain": True,
    })
    assert resp.status_code == 200, resp.text
    stages = resp.json()["explain"]["stages"]
    perf = [stage for stage in stages if stage["name"] == "performance"]
    assert perf
    assert "stages_ms" in perf[0]
    assert "query_hash" in perf[0]
    assert "ma3 explain performance stage" not in json.dumps(perf[0])


def test_postgres_pool_wrapper_uses_connection_pool(monkeypatch):
    class FakeRaw:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=()):
            self.executed.append((sql, params))
            return self

    class FakeContext:
        def __init__(self):
            self.raw = FakeRaw()

        def __enter__(self):
            return self.raw

        def __exit__(self, exc_type, exc, tb):
            return None

    class FakePool:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            FakePool.instances.append(self)

        def connection(self):
            return FakeContext()

        def close(self):
            self.closed = True

    monkeypatch.setattr(db_module, "ConnectionPool", FakePool)
    monkeypatch.setattr(db_module, "dict_row", object())
    monkeypatch.setattr(db_module, "psycopg", object())
    monkeypatch.setattr(db_module, "_pg_pool", None)

    orig_backend = config.settings.db_backend
    orig_url = config.settings.database_url
    try:
        object.__setattr__(config.settings, "db_backend", "postgresql")
        object.__setattr__(config.settings, "database_url", "postgresql://example/ma3")
        object.__setattr__(config.settings, "db_pool_enabled", True)
        with db_module.get_connection() as conn:
            conn.execute("SELECT ?", (1,))
        assert FakePool.instances
        assert FakePool.instances[0].kwargs["min_size"] == config.settings.db_pool_min_size
    finally:
        db_module.close_postgres_pool()
        object.__setattr__(config.settings, "db_backend", orig_backend)
        object.__setattr__(config.settings, "database_url", orig_url)


def test_postgres_pool_can_be_disabled_for_benchmark(monkeypatch):
    class FakeRaw:
        def __init__(self):
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=()):
            self.executed.append((sql, params))
            return self

    calls = []

    class FakePsycopg:
        @staticmethod
        def connect(url, row_factory=None):
            calls.append((url, row_factory))
            return FakeRaw()

    class ForbiddenPool:
        def __init__(self, **kwargs):  # pragma: no cover - only used on failure
            raise AssertionError("pool should not be constructed when disabled")

    monkeypatch.setattr(db_module, "ConnectionPool", ForbiddenPool)
    monkeypatch.setattr(db_module, "dict_row", object())
    monkeypatch.setattr(db_module, "psycopg", FakePsycopg)
    monkeypatch.setattr(db_module, "_pg_pool", None)

    orig_backend = config.settings.db_backend
    orig_url = config.settings.database_url
    orig_enabled = config.settings.db_pool_enabled
    try:
        object.__setattr__(config.settings, "db_backend", "postgresql")
        object.__setattr__(config.settings, "database_url", "postgresql://example/ma3")
        object.__setattr__(config.settings, "db_pool_enabled", False)
        with db_module.get_connection() as conn:
            conn.execute("SELECT ?", (1,))
        assert calls == [("postgresql://example/ma3", db_module.dict_row)]
    finally:
        db_module.close_postgres_pool()
        object.__setattr__(config.settings, "db_backend", orig_backend)
        object.__setattr__(config.settings, "database_url", orig_url)
        object.__setattr__(config.settings, "db_pool_enabled", orig_enabled)


def test_fixed_benchmark_request_file_is_valid():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "perf_requests.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 8
    names = {row["name"] for row in rows}
    assert len(names) == len(rows)
    for row in rows:
        assert row["route"] in {"/search", "/v2/search/explain", "/v2/agent/context"}
        text = json.dumps(row, ensure_ascii=False).lower()
        assert "password" not in text
        assert "api_key" not in text
        assert "secret" not in text
