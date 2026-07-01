from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.embedding_service import cosine_similarity, deserialize_embedding, embed_text
from app.storage.db import (
    _fetch_records_by_ids,
    _fetchall,
    _like_search_records,
    _list_active_record_ids,
    connect,
    get_embeddings_batch,
    is_postgres,
)


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return {rid: 0.0 for rid in scores}
    return {rid: score / max_score for rid, score in scores.items()}


def _fts_search_pg(library_ids: set[str], problem: str, limit: int) -> dict[str, float]:
    if not problem.strip():
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.search_tsv, websearch_to_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.search_tsv @@ websearch_to_tsquery('simple', ?)
          AND i.library_id IN ({placeholders})
          AND i.status = 'active'
        ORDER BY score DESC
        LIMIT ?
    """
    params: list[Any] = [problem, problem, *library_ids, limit]
    try:
        with connect() as conn:
            rows = _fetchall(conn, sql, params)
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


def _hybrid_search(library_ids: set[str], problem: str, limit: int) -> list[dict[str, Any]]:
    fts_scores = _fts_search_pg(library_ids, problem, limit=max(limit * 4, 40)) if is_postgres() else {}
    vector_scores = _vector_scores(
        library_ids,
        problem,
        set(fts_scores) if fts_scores else None,
        limit=max(limit * 4, 40),
    )

    candidate_ids = set(fts_scores) | set(vector_scores)
    if not candidate_ids:
        return _like_search_records(library_ids, problem, limit)

    fts_norm = _normalize_scores(fts_scores)
    combined: dict[str, float] = {}
    for record_id in candidate_ids:
        fts_part = fts_norm.get(record_id, 0.0)
        vec_part = vector_scores.get(record_id, 0.0)
        if fts_part and vec_part:
            combined[record_id] = 0.4 * fts_part + 0.6 * vec_part
        elif vec_part:
            combined[record_id] = vec_part
        else:
            combined[record_id] = fts_part

    ranked_ids = [rid for rid, _ in sorted(combined.items(), key=lambda item: item[1], reverse=True)[:limit]]
    records = _fetch_records_by_ids(ranked_ids, library_ids)
    order = {rid: idx for idx, rid in enumerate(ranked_ids)}
    records.sort(key=lambda row: order.get(str(row["id"]), 10_000))
    return records


def search_records(library_ids: set[str], problem: str, limit: int = 20) -> list[dict[str, Any]]:
    if not library_ids:
        return []
    problem = problem.strip()
    if not problem:
        return []

    if settings.disable_embeddings:
        return _like_search_records(library_ids, problem, limit)

    if is_postgres():
        return _hybrid_search(library_ids, problem, limit)

    vector_scores = _vector_scores(library_ids, problem, None, limit=limit)
    if vector_scores:
        ranked_ids = [rid for rid, _ in sorted(vector_scores.items(), key=lambda item: item[1], reverse=True)[:limit]]
        return _fetch_records_by_ids(ranked_ids, library_ids)

    return _like_search_records(library_ids, problem, limit)
