from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.services.embedding_service import cosine_similarity, embed_text
from app.services.search_context_service import SearchContext, context_boost
from app.storage.db import (
    _fetch_records_by_ids,
    _fetchall,
    _like_search_records,
    _list_active_record_ids,
    ann_vector_search,
    connect,
    get_embeddings_batch,
    get_feedback_summaries,
    get_superseded_record_ids,
    is_postgres,
    pgvector_ready,
)


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return {rid: 0.0 for rid in scores}
    return {rid: score / max_score for rid, score in scores.items()}


def _feedback_multiplier(up: int, down: int) -> float:
    net = up - down
    if net <= -3:
        return 0.3
    if net < 0:
        return 0.7
    if net >= 3:
        return 1.15
    return 1.0


def _fts_query_text(problem: str) -> str:
    tokens = [t for t in re.split(r"\s+", problem.strip()) if len(t) >= 2][:8]
    if not tokens:
        return problem[:200]
    return " | ".join(tokens)


def _fts_search_pg(library_ids: set[str], problem: str, limit: int) -> dict[str, float]:
    if not problem.strip():
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    query_text = _fts_query_text(problem)
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.search_tsv, to_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.search_tsv @@ to_tsquery('simple', ?)
          AND i.library_id IN ({placeholders})
          AND i.status = 'active'
        ORDER BY score DESC
        LIMIT ?
    """
    params: list[Any] = [query_text, query_text, *library_ids, limit]
    try:
        with connect() as conn:
            rows = _fetchall(conn, sql, params)
    except Exception:
        return _fts_search_pg_plain(library_ids, problem, limit)
    scores = {str(row["record_id"]): float(row["score"]) for row in rows if float(row["score"]) > 0}
    if scores:
        return scores
    return _fts_search_pg_plain(library_ids, problem, limit)


def _fts_search_pg_plain(library_ids: set[str], problem: str, limit: int) -> dict[str, float]:
    if not problem.strip() or not library_ids:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    fallback = problem[:200]
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.search_tsv, plainto_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.search_tsv @@ plainto_tsquery('simple', ?)
          AND i.library_id IN ({placeholders})
          AND i.status = 'active'
        ORDER BY score DESC
        LIMIT ?
    """
    try:
        with connect() as conn:
            rows = _fetchall(conn, sql, [fallback, fallback, *library_ids, limit])
    except Exception:
        return {}
    return {str(row["record_id"]): float(row["score"]) for row in rows if float(row["score"]) > 0}


def _vector_scores(
    library_ids: set[str],
    problem: str,
    candidate_ids: set[str] | None,
    limit: int,
) -> dict[str, float]:
    query_embedding = embed_text(problem)
    if query_embedding is None:
        return {}

    if is_postgres() and candidate_ids is None and pgvector_ready():
        try:
            return ann_vector_search(library_ids, query_embedding, limit)
        except Exception:
            pass

    ids = candidate_ids or _list_active_record_ids(library_ids)
    if not ids:
        return {}

    embeddings = get_embeddings_batch(ids)
    scores: dict[str, float] = {}
    for record_id, vector in embeddings.items():
        scores[record_id] = max(0.0, cosine_similarity(query_embedding, vector))
    if not scores:
        return {}

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return dict(ranked[:limit])


def _payload_map(record_ids: list[str], library_ids: set[str]) -> dict[str, dict[str, Any]]:
    rows = _fetch_records_by_ids(record_ids, library_ids, include_payload=True)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload")
        out[str(row["id"])] = payload if isinstance(payload, dict) else {}
    return out


def _apply_context_boost(
    combined: dict[str, float],
    library_ids: set[str],
    ctx: SearchContext | None,
    *,
    explain: bool,
    explain_map: dict[str, dict[str, Any]],
) -> dict[str, float]:
    if not combined or ctx is None:
        return combined
    payloads = _payload_map(list(combined), library_ids)
    adjusted: dict[str, float] = {}
    for record_id, score in combined.items():
        factor = context_boost(payloads.get(record_id, {}), ctx)
        adjusted[record_id] = score * factor
        if explain:
            entry = explain_map.setdefault(record_id, {})
            entry["context_factor"] = round(factor, 4)
            entry["base_score"] = round(score, 4)
    return adjusted


def _apply_feedback_and_filter(
    combined: dict[str, float],
    library_ids: set[str],
    *,
    explain: bool,
    explain_map: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    if not combined:
        return {}, {}
    explain_map = explain_map or {}
    record_ids = list(combined)
    superseded = get_superseded_record_ids(record_ids, library_ids)
    feedback = get_feedback_summaries(record_ids)
    adjusted: dict[str, float] = {}
    for record_id, base_score in combined.items():
        if record_id in superseded:
            if explain:
                explain_map[record_id] = {"excluded": "superseded", "base_score": base_score}
            continue
        fb = feedback.get(record_id, {"up": 0, "down": 0})
        factor = _feedback_multiplier(int(fb.get("up", 0)), int(fb.get("down", 0)))
        final = base_score * factor
        adjusted[record_id] = final
        if explain:
            entry = explain_map.setdefault(record_id, {})
            entry.setdefault("base_score", round(base_score, 4))
            entry["feedback_factor"] = factor
            entry["combined_score"] = round(final, 4)
            entry["feedback"] = fb
    return adjusted, explain_map


def _hybrid_search(
    library_ids: set[str],
    problem: str,
    limit: int,
    *,
    explain: bool = False,
    context: SearchContext | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    pool_limit = max(limit * 4, 40)
    fts_scores = _fts_search_pg(library_ids, problem, limit=pool_limit) if is_postgres() else {}
    vector_scores = _vector_scores(library_ids, problem, None, limit=pool_limit)

    candidate_ids = set(fts_scores) | set(vector_scores)
    if not candidate_ids:
        records = _like_search_records(library_ids, problem, limit)
        return records, {}

    fts_norm = _normalize_scores(fts_scores)
    combined: dict[str, float] = {}
    for record_id in candidate_ids:
        fts_part = fts_norm.get(record_id, 0.0)
        vec_part = vector_scores.get(record_id, 0.0)
        if fts_part and vec_part:
            hybrid = 0.4 * fts_part + 0.6 * vec_part
            combined[record_id] = max(vec_part, hybrid)
        elif vec_part:
            combined[record_id] = vec_part
        else:
            combined[record_id] = fts_part * 0.5

    explain_map: dict[str, dict[str, Any]] = {}
    combined = _apply_context_boost(combined, library_ids, context, explain=explain, explain_map=explain_map)
    adjusted, explain_map = _apply_feedback_and_filter(combined, library_ids, explain=explain, explain_map=explain_map)
    if explain:
        for record_id, base in combined.items():
            entry = explain_map.setdefault(record_id, {})
            if "excluded" not in entry:
                entry.setdefault("fts", round(fts_norm.get(record_id, 0.0), 4))
                entry.setdefault("vector", round(vector_scores.get(record_id, 0.0), 4))
                if "base_score" not in entry:
                    entry["base_score"] = round(base, 4)

    ranked_ids = [rid for rid, _ in sorted(adjusted.items(), key=lambda item: item[1], reverse=True)[:limit]]
    records = _fetch_records_by_ids(ranked_ids, library_ids, include_payload=True)
    order = {rid: idx for idx, rid in enumerate(ranked_ids)}
    records.sort(key=lambda row: order.get(str(row["id"]), 10_000))
    if explain:
        for record in records:
            rid = str(record["id"])
            if rid in explain_map:
                record["_rank"] = explain_map[rid]
    return records, explain_map


def search_records(
    library_ids: set[str],
    problem: str,
    limit: int = 20,
    *,
    explain: bool = False,
    context: SearchContext | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not library_ids:
        return [], {}
    problem = problem.strip()
    if not problem:
        return [], {}

    if settings.disable_embeddings:
        return _like_search_records(library_ids, problem, limit), {}

    if is_postgres():
        return _hybrid_search(library_ids, problem, limit, explain=explain, context=context)

    vector_scores = _vector_scores(library_ids, problem, None, limit=limit * 4)
    if vector_scores:
        explain_map: dict[str, dict[str, Any]] = {}
        boosted = _apply_context_boost(vector_scores, library_ids, context, explain=explain, explain_map=explain_map)
        adjusted, explain_map = _apply_feedback_and_filter(boosted, library_ids, explain=explain, explain_map=explain_map)
        ranked_ids = [rid for rid, _ in sorted(adjusted.items(), key=lambda item: item[1], reverse=True)[:limit]]
        records = _fetch_records_by_ids(ranked_ids, library_ids, include_payload=True)
        if explain:
            for record in records:
                rid = str(record["id"])
                if rid in explain_map:
                    record["_rank"] = explain_map[rid]
        return records, explain_map

    records = _like_search_records(library_ids, problem, limit)
    return records, {}
