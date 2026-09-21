"""Integration tests for the unified GTN search pipeline (design/12 §7.2).

Focus on the lexical (embeddings-disabled) path — this is how the 202 eval host
runs and the path that previously degenerated to ``ORDER BY created_at DESC``.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from app.storage import db
from app.storage import search as search_module
from app.storage.search import search_records


@pytest.fixture(autouse=True)
def _lexical_mode(monkeypatch):
    monkeypatch.setattr(settings, "disable_embeddings", True)
    monkeypatch.setattr(settings, "search_hide_clearly_wrong", True)
    monkeypatch.setattr(settings, "search_rel_min", 0.35)


def _lib() -> str:
    return f"lib_test_{uuid.uuid4().hex[:12]}"


def _add(lib: str, problem: str, summary: str = "ok") -> str:
    row = db.insert_record(
        library_id=lib,
        case_id=None,
        status="active",
        problem=problem,
        outcome="resolved",
        result_summary=summary,
        payload={"problem": problem},
    )
    return row["record_id"]


def _ids(lib: str, query: str, limit: int = 20):
    records, _ = search_records({lib}, query, limit=limit)
    return [str(r["id"]) for r in records]


def test_lexical_fix_ranks_above_policy_noise():
    lib = _lib()
    fix = _add(lib, "mihomo proxy docker container fails to start", "fix mixed-port config")
    noise = _add(lib, "agent policy upgrade notes", "mihomo mentioned once in passing")
    order = _ids(lib, "mihomo proxy docker")
    assert order[0] == fix
    assert noise not in order  # matched one token, but falls below the relevance floor


def test_low_relevance_matches_are_not_returned_to_fill_limit():
    lib = _lib()
    strong = _add(lib, "mihomo proxy docker networking issue", "mihomo proxy docker fix")
    weak = _add(lib, "unrelated note mentioning mihomo", "misc")

    order = _ids(lib, "mihomo proxy docker", limit=20)

    assert order == [strong]
    assert weak not in order


def test_all_low_relevance_matches_return_empty():
    lib = _lib()
    _add(lib, "unrelated note mentioning mihomo", "misc")

    assert _ids(lib, "mihomo proxy docker") == []


def test_min_relevance_gate_is_shared_by_vector_and_hybrid_paths(monkeypatch):
    lib = _lib()
    at_threshold = _add(lib, "candidate at threshold")
    below_threshold = _add(lib, "candidate below threshold")
    monkeypatch.setattr(settings, "disable_embeddings", False)
    monkeypatch.setattr(settings, "search_rel_min", 0.35)
    monkeypatch.setattr(
        search_module,
        "_relevance_pool",
        lambda *_args, **_kwargs: {at_threshold: 0.35, below_threshold: 0.349999},
    )

    assert _ids(lib, "arbitrary query") == [at_threshold]


def test_lexical_not_created_at_desc():
    lib = _lib()
    strong_old = _add(lib, "mihomo proxy docker networking issue", "detailed mihomo proxy docker fix")
    weak_new = _add(lib, "unrelated note mentioning mihomo", "misc")
    order = _ids(lib, "mihomo proxy docker")
    # newest (weak_new) must NOT come first — relevance beats recency
    assert order[0] == strong_old


def test_pool_composition_stability():
    lib = _lib()
    a = _add(lib, "mihomo proxy docker one two", "aaa")
    b = _add(lib, "mihomo proxy note", "bbb")
    before = _ids(lib, "mihomo proxy docker")
    _add(lib, "totally different subject about kubernetes", "ccc")  # non-matching noise
    after = _ids(lib, "mihomo proxy docker")
    assert [r for r in before if r in (a, b)] == [r for r in after if r in (a, b)]


def test_cjk_query_matches():
    lib = _lib()
    rid = _add(lib, "mihomo 代理 配置 问题 排查", "修复 代理 配置")
    order = _ids(lib, "代理 配置")
    assert rid in order


def test_superseded_hidden_when_flag_on():
    lib = _lib()
    good = _add(lib, "mihomo proxy docker good fix", "works")
    stale = _add(lib, "mihomo proxy docker stale answer", "old")
    superseder = _add(lib, "mihomo proxy docker replacement", "new")
    db.insert_record_relations(source_id=superseder, based_on_record_ids=[stale], relation_type="supersedes")

    order = _ids(lib, "mihomo proxy docker")
    assert stale not in order  # clearly_wrong (superseded) hidden
    assert good in order and superseder in order


def test_superseded_sinks_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "search_hide_clearly_wrong", False)
    lib = _lib()
    good = _add(lib, "mihomo proxy docker good", "works")
    stale = _add(lib, "mihomo proxy docker stale detailed detailed", "old")
    superseder = _add(lib, "mihomo proxy docker new", "new")
    db.insert_record_relations(source_id=superseder, based_on_record_ids=[stale], relation_type="supersedes")

    order = _ids(lib, "mihomo proxy docker")
    assert stale in order  # visible but sunk
    assert order[-1] == stale


def test_hide_clearly_wrong_respects_limit():
    lib = _lib()
    good_ids = [_add(lib, f"mihomo proxy docker fix number {i}", "ok") for i in range(4)]
    stale = _add(lib, "mihomo proxy docker bad", "bad")
    superseder = _add(lib, "mihomo proxy docker sup", "sup")
    db.insert_record_relations(source_id=superseder, based_on_record_ids=[stale], relation_type="supersedes")

    order = _ids(lib, "mihomo proxy docker", limit=3)
    assert len(order) == 3
    assert stale not in order


def test_downvoted_record_sinks():
    lib = _lib()
    good = _add(lib, "mihomo proxy docker correct", "works")
    bad = _add(lib, "mihomo proxy docker wrong detailed detailed", "misleading")
    for i in range(25):
        db.set_record_feedback(bad, f"user:dv{i}", -1)
    order = _ids(lib, "mihomo proxy docker")
    # bad is clearly_wrong by votes -> hidden (flag on)
    assert bad not in order
    assert good in order


def test_explain_attached_only_when_requested():
    lib = _lib()
    _add(lib, "mihomo proxy docker explain test", "ok")
    plain, _ = search_records({lib}, "mihomo proxy docker", limit=5, explain=False)
    assert all("_rank" not in r for r in plain)

    detailed, explain_map = search_records({lib}, "mihomo proxy docker", limit=5, explain=True)
    assert detailed and "_rank" in detailed[0]
    rank = detailed[0]["_rank"]
    for key in ("relevance", "rel_eff", "label", "wilson_L", "wilson_U", "Q", "final_score", "wrong_tier"):
        assert key in rank
    assert explain_map
