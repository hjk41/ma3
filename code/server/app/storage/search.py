from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.services.embedding_service import cosine_similarity, embed_text
from app.services.search_context_service import SearchContext, context_boost
from app.storage.db import (
    _fetch_records_by_ids,
    _fetchall,
    _list_searchable_record_ids,
    _search_tokens,
    ann_vector_search,
    connect,
    get_embeddings_batch,
    get_feedback_summaries,
    get_superseded_record_ids,
    is_postgres,
    pgvector_ready,
)
from app.storage.ranking import RankInput, rank


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    if max_score <= 0:
        return {rid: 0.0 for rid in scores}
    return {rid: score / max_score for rid, score in scores.items()}


def _lexical_score(tokens: list[str], *, problem: str, result_summary: str) -> float:
    if not tokens:
        return 0.0
    problem_text = problem.lower()
    summary_text = result_summary.lower()
    raw = 0
    for token in tokens:
        if token in problem_text:
            raw += 2
        if token in summary_text:
            raw += 1
    return raw / float(len(tokens) * 3)


def _visibility_sql(alias: str, principal_id: str | None) -> tuple[str, list[Any]]:
    if principal_id:
        return (
            f"({alias}.status = 'active' OR ({alias}.status = 'buffered' AND {alias}.created_by = ?))",
            [principal_id],
        )
    return f"{alias}.status = 'active'", []


def _lexical_relevance(
    library_ids: set[str],
    problem: str,
    pool_limit: int,
    *,
    principal_id: str | None,
) -> dict[str, float]:
    """Weighted-token-match relevance in [0,1] (design/12 §3.3), replacing the old
    ``ORDER BY created_at DESC`` lexical fallback.

    score = Σ_t (2·[token in problem] + 1·[token in summary]) / (|T|·3)

    Uses the raw match fraction directly (NOT pool-max normalized) so a record's
    relevance is independent of what else is in the candidate pool — this keeps
    ranking stable when unrelated records are added (design/12 §7.2 pool-stability).
    """
    if not library_ids:
        return {}
    tokens = [t.lower() for t in _search_tokens(problem)]
    if not tokens:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    op = "ILIKE" if is_postgres() else "LIKE"
    visibility, visibility_params = _visibility_sql("i", principal_id)
    token_clauses = " OR ".join(f"i.search_text {op} ?" for _ in tokens)
    query = f"""
        SELECT i.record_id
        FROM record_search_index i
        WHERE i.library_id IN ({placeholders}) AND {visibility}
          AND ({token_clauses})
        LIMIT ?
    """
    params: list[Any] = [*library_ids, *visibility_params]
    for token in tokens:
        pattern = f"%{token[:200]}%"
        params.append(pattern)
    params.append(pool_limit)
    with connect() as conn:
        candidate_rows = _fetchall(conn, query, params)
    candidate_ids = [str(row["record_id"]) for row in candidate_rows]
    rows = _fetch_records_by_ids(
        candidate_ids,
        library_ids,
        principal_id=principal_id,
    )
    scores: dict[str, float] = {}
    for row in rows:
        rid = str(row["id"])
        score = _lexical_score(
            tokens,
            problem=str(row["problem"] or ""),
            result_summary=str(row["result_summary"] or ""),
        )
        if score > 0:
            scores[rid] = score
    return scores


def _fts_query_text(problem: str) -> str:
    tokens = [t for t in re.split(r"\s+", problem.strip()) if len(t) >= 2][:8]
    if not tokens:
        return problem[:200]
    return " | ".join(tokens)


def _fts_search_pg(
    library_ids: set[str],
    problem: str,
    limit: int,
    *,
    principal_id: str | None,
) -> dict[str, float]:
    if not problem.strip():
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    query_text = _fts_query_text(problem)
    visibility, visibility_params = _visibility_sql("i", principal_id)
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.search_tsv, to_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.search_tsv @@ to_tsquery('simple', ?)
          AND i.library_id IN ({placeholders})
          AND {visibility}
        ORDER BY score DESC
        LIMIT ?
    """
    params: list[Any] = [query_text, query_text, *library_ids, *visibility_params, limit]
    try:
        with connect() as conn:
            rows = _fetchall(conn, sql, params)
    except Exception:
        return _fts_search_pg_plain(library_ids, problem, limit, principal_id=principal_id)
    scores = {str(row["record_id"]): float(row["score"]) for row in rows if float(row["score"]) > 0}
    if scores:
        return scores
    return _fts_search_pg_plain(library_ids, problem, limit, principal_id=principal_id)


def _fts_search_pg_plain(
    library_ids: set[str],
    problem: str,
    limit: int,
    *,
    principal_id: str | None,
) -> dict[str, float]:
    if not problem.strip() or not library_ids:
        return {}
    placeholders = ",".join("?" for _ in library_ids)
    fallback = problem[:200]
    visibility, visibility_params = _visibility_sql("i", principal_id)
    sql = f"""
        SELECT i.record_id,
               ts_rank_cd(i.search_tsv, plainto_tsquery('simple', ?)) AS score
        FROM record_search_index i
        WHERE i.search_tsv @@ plainto_tsquery('simple', ?)
          AND i.library_id IN ({placeholders})
          AND {visibility}
        ORDER BY score DESC
        LIMIT ?
    """
    try:
        with connect() as conn:
            rows = _fetchall(conn, sql, [fallback, fallback, *library_ids, *visibility_params, limit])
    except Exception:
        return {}
    return {str(row["record_id"]): float(row["score"]) for row in rows if float(row["score"]) > 0}


def _vector_scores(
    library_ids: set[str],
    problem: str,
    candidate_ids: set[str] | None,
    limit: int,
    *,
    principal_id: str | None,
) -> dict[str, float]:
    query_embedding = embed_text(problem)
    if query_embedding is None:
        return {}

    if is_postgres() and candidate_ids is None and pgvector_ready():
        try:
            return ann_vector_search(
                library_ids,
                query_embedding,
                limit,
                principal_id=principal_id,
            )
        except Exception:
            pass

    ids = candidate_ids or _list_searchable_record_ids(library_ids, principal_id=principal_id)
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


def _payload_map(
    record_ids: list[str],
    library_ids: set[str],
    *,
    principal_id: str | None,
) -> dict[str, dict[str, Any]]:
    rows = _fetch_records_by_ids(
        record_ids,
        library_ids,
        include_payload=True,
        principal_id=principal_id,
    )
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
    principal_id: str | None,
) -> dict[str, float]:
    if not combined or ctx is None:
        return combined
    payloads = _payload_map(list(combined), library_ids, principal_id=principal_id)
    adjusted: dict[str, float] = {}
    for record_id, score in combined.items():
        factor = context_boost(payloads.get(record_id, {}), ctx)
        adjusted[record_id] = score * factor
        if explain:
            entry = explain_map.setdefault(record_id, {})
            entry["context_factor"] = round(factor, 4)
            entry["base_score"] = round(score, 4)
    return adjusted


def _hybrid_relevance(
    library_ids: set[str],
    problem: str,
    pool_limit: int,
    *,
    explain: bool,
    explain_map: dict[str, dict[str, Any]],
    principal_id: str | None,
) -> dict[str, float]:
    """Postgres FTS + vector fusion → raw relevance dict (pre context-boost)."""
    fts_scores = (
        _fts_search_pg(library_ids, problem, limit=pool_limit, principal_id=principal_id)
        if is_postgres()
        else {}
    )
    vector_scores = _vector_scores(
        library_ids,
        problem,
        None,
        limit=pool_limit,
        principal_id=principal_id,
    )
    candidate_ids = set(fts_scores) | set(vector_scores)
    if not candidate_ids:
        return {}
    fts_norm = _normalize_scores(fts_scores)
    combined: dict[str, float] = {}
    for record_id in candidate_ids:
        fts_part = fts_norm.get(record_id, 0.0)
        vec_part = vector_scores.get(record_id, 0.0)
        if fts_part and vec_part:
            combined[record_id] = max(vec_part, 0.4 * fts_part + 0.6 * vec_part)
        elif vec_part:
            combined[record_id] = vec_part
        else:
            combined[record_id] = fts_part * 0.5
    if explain:
        for record_id in combined:
            entry = explain_map.setdefault(record_id, {})
            entry.setdefault("fts", round(fts_norm.get(record_id, 0.0), 4))
            entry.setdefault("vector", round(vector_scores.get(record_id, 0.0), 4))
    return combined


def _relevance_pool(
    library_ids: set[str],
    problem: str,
    pool_limit: int,
    *,
    explain: bool,
    context: SearchContext | None,
    explain_map: dict[str, dict[str, Any]],
    principal_id: str | None,
) -> dict[str, float]:
    """Unified relevance stage: pick a mode, fuse, apply context boost, clamp to [0,1].

    Always returns a relevance dict feeding the GTN stage — the lexical path no
    longer short-circuits to ``created_at DESC`` (design/12 B1)."""
    if settings.disable_embeddings:
        relevance = _lexical_relevance(
            library_ids,
            problem,
            pool_limit,
            principal_id=principal_id,
        )
    elif is_postgres():
        relevance = _hybrid_relevance(
            library_ids,
            problem,
            pool_limit,
            explain=explain,
            explain_map=explain_map,
            principal_id=principal_id,
        )
    else:
        relevance = _vector_scores(
            library_ids,
            problem,
            None,
            limit=pool_limit,
            principal_id=principal_id,
        )
        if not relevance:
            relevance = _lexical_relevance(
                library_ids,
                problem,
                pool_limit,
                principal_id=principal_id,
            )
    if not relevance:
        return {}
    relevance = _apply_context_boost(
        relevance,
        library_ids,
        context,
        explain=explain,
        explain_map=explain_map,
        principal_id=principal_id,
    )
    return {rid: max(0.0, min(1.0, score)) for rid, score in relevance.items()}


def search_records(
    library_ids: set[str],
    problem: str,
    limit: int = 20,
    *,
    explain: bool = False,
    context: SearchContext | None = None,
    principal_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Unified search: relevance pool → minimum relevance gate → GTN → truncate.

    Same pipeline for every backend/embedding mode so feedback (Wilson) and the
    clearly-wrong floor always apply (design/12 §5). Candidates below
    ``search_rel_min`` are dropped instead of being returned merely to fill the
    requested limit."""
    if not library_ids:
        return [], {}
    problem = problem.strip()
    if not problem:
        return [], {}

    pool_limit = max(limit * 4, 40)
    explain_map: dict[str, dict[str, Any]] = {}
    relevance = _relevance_pool(
        library_ids,
        problem,
        pool_limit,
        explain=explain,
        context=context,
        explain_map=explain_map,
        principal_id=principal_id,
    )
    relevance = {
        record_id: score
        for record_id, score in relevance.items()
        if score >= settings.search_rel_min
    }
    if not relevance:
        return [], {}

    record_ids = list(relevance)
    superseded = get_superseded_record_ids(record_ids, library_ids)
    feedback = get_feedback_summaries(record_ids)
    records = _fetch_records_by_ids(
        record_ids,
        library_ids,
        include_payload=True,
        principal_id=principal_id,
    )
    by_id = {str(row["id"]): row for row in records}

    inputs: list[RankInput] = []
    for rid, rel in relevance.items():
        row = by_id.get(rid)
        if row is None:
            continue
        fb = feedback.get(rid, {"up": 0, "down": 0})
        inputs.append(
            RankInput(
                record_id=rid,
                relevance=rel,
                up=int(fb.get("up", 0)),
                down=int(fb.get("down", 0)),
                superseded=rid in superseded,
                created_at=row.get("created_at"),
            )
        )

    ranked = rank(inputs)
    if settings.search_hide_clearly_wrong:
        ranked = [r for r in ranked if not r.is_wrong]
    ranked = ranked[:limit]

    ordered: list[dict[str, Any]] = []
    for result in ranked:
        row = by_id.get(result.record_id)
        if row is None:
            continue
        if explain:
            entry = explain_map.setdefault(result.record_id, {})
            entry.update(result.explain())
            entry["feedback"] = feedback.get(result.record_id, {"up": 0, "down": 0})
            row["_rank"] = entry
        ordered.append(row)
    return ordered, explain_map
