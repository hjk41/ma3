from __future__ import annotations

from app.models.enums import RecordStatus, RiskLevel, VerificationLevel
from app.models.query import SearchQuery
from app.models.result import SearchMatch, SearchResponse
from app.core.config import settings
from app.storage.fts import fts_tag_search, fts_content_search
from app.storage.repositories import FeedbackRepository, RecordRepository, RelationRepository
from app.services.embedding_service import embed_text
from app.services.scoring import score_record
from app.services.perf_service import current_trace, perf_stage


# Statuses that must never surface in agent-facing search. ``stale`` and
# ``superseded`` are intentionally NOT excluded: they remain discoverable but
# are soft-decayed in scoring (see scoring.STATUS_DECAY) so newer/active
# knowledge ranks above them while outdated knowledge can still serve as a
# last-resort fallback and stays auditable.
_SEARCH_EXCLUDED_STATUSES = {
    RecordStatus.draft,
    RecordStatus.invalid,
    RecordStatus.archived,
    RecordStatus.quarantine,
}


def search_records(payload: SearchQuery, accessible_library_ids: set[str]) -> SearchResponse:
    record_repo = RecordRepository()
    feedback_repo = FeedbackRepository()
    relation_repo = RelationRepository()

    problem = payload.problem.strip()

    # ── Stage 1: FTS pre-filter ───────────────────────────────────────────────
    # Run both indexes: tag (precise) + content (broad).
    # Union their record_id hits to form the candidate set.
    fts_tag_scores: dict[str, float] = {}
    fts_content_scores: dict[str, float] = {}
    candidate_ids: set[str] | None = None

    if problem:
        with perf_stage("fts_tag_search"):
            tag_hits = fts_tag_search(problem, accessible_library_ids)
        with perf_stage("fts_content_search"):
            content_hits = fts_content_search(problem, accessible_library_ids)
        fts_tag_scores = dict(tag_hits)
        fts_content_scores = dict(content_hits)
        candidate_ids = set(fts_tag_scores) | set(fts_content_scores)

    # Explicit tag filter on the query (SearchQuery.tags) — direct record_id
    # boost even when tags don't appear verbatim in the problem text.
    exact_tag_match_counts: dict[str, int] = {}
    if payload.tags:
        with perf_stage("exact_tag_search"):
            exact_tag_hits = record_repo.find_ids_by_exact_tags_accessible(
                payload.tags,
                accessible_library_ids,
                limit=max(80, payload.max_primary * 2),
            )
        if exact_tag_hits:
            exact_tag_match_counts = dict(exact_tag_hits)
            exact_ids = {record_id for record_id, _ in exact_tag_hits}
            candidate_ids = (candidate_ids or set()) | exact_ids
            for record_id, match_count in exact_tag_hits:
                fts_tag_scores[record_id] = max(fts_tag_scores.get(record_id, 0.0), float(match_count))

        tag_query = " ".join(payload.tags)
        with perf_stage("fts_tag_search"):
            extra_hits = fts_tag_search(tag_query, accessible_library_ids, limit=40)
        if extra_hits:
            extra_ids = {r for r, _ in extra_hits}
            candidate_ids = (candidate_ids or set()) | extra_ids
            for r, s in extra_hits:
                # Boost explicit tag hits above regular problem-text tag hits
                fts_tag_scores[r] = max(fts_tag_scores.get(r, 0.0), s * 1.5)

    # Fetch records: batch lookup when candidates exist, full scan as fallback
    with perf_stage("record_fetch"):
        if candidate_ids:
            records = record_repo.get_batch_accessible(candidate_ids, accessible_library_ids)
        else:
            records = record_repo.list_accessible(accessible_library_ids)

    trace = current_trace()
    if trace is not None:
        trace.candidate_count = len(candidate_ids or {r.record_id for r in records})
        trace.full_scan = not bool(candidate_ids)

    # ── Stage 2: Embed query + batch-load record embeddings ───────────────────
    with perf_stage("query_embedding"):
        query_embedding = embed_text(problem) if problem else None
    all_ids = {r.record_id for r in records}
    with perf_stage("embedding_fetch"):
        record_embeddings = record_repo.get_embeddings_batch(all_ids)

    # ── Stage 3: Filter, batch-load graph context, score and classify ─────────
    eligible_records = []
    for record in records:
        if record.status in _SEARCH_EXCLUDED_STATUSES:
            continue
        exact_tag_count = exact_tag_match_counts.get(record.record_id, 0)
        if record.verification_level == VerificationLevel.l0 and exact_tag_count < 3:
            continue
        if record.risk_level == RiskLevel.critical:
            continue
        eligible_records.append(record)

    eligible_ids = {r.record_id for r in eligible_records}
    with perf_stage("feedback_relation_fetch"):
        if settings.search_batch_graph_enabled:
            feedback_by_record = feedback_repo.list_by_record_ids(eligible_ids)
            relations_by_record = relation_repo.list_by_record_ids(eligible_ids)
        else:
            feedback_by_record = {
                record_id: feedback_repo.list_by_record(record_id)
                for record_id in eligible_ids
            }
            relations_by_record = {
                record_id: relation_repo.list_by_record(record_id)
                for record_id in eligible_ids
            }

    primary: list[SearchMatch] = []
    contrasting: list[SearchMatch] = []

    with perf_stage("scoring"):
        for record in eligible_records:
            exact_tag_count = exact_tag_match_counts.get(record.record_id, 0)
            feedback_items = feedback_by_record.get(record.record_id, [])
            relations = relations_by_record.get(record.record_id, [])
            score, reasons = score_record(
                payload,
                record,
                feedback_items,
                relations,
                fts_tag_scores=fts_tag_scores,
                fts_content_scores=fts_content_scores,
                query_embedding=query_embedding,
                record_embeddings=record_embeddings,
            )
            if record.verification_level == VerificationLevel.l0 and exact_tag_count >= 3:
                reasons.append(f"low verification returned due {exact_tag_count} exact query tag matches")

            match = SearchMatch(
                record=record,
                match_score=round(score, 3),
                why_matched=reasons[:6],
                conflicts=record.not_applicable_if[:3],
                relations=relations,
            )

            if record.result.outcome.lower() in {"failure", "invalid"}:
                contrasting.append(match)
            else:
                primary.append(match)

    if trace is not None:
        trace.record_count_scored = len(eligible_records)

    primary.sort(key=lambda item: item.match_score, reverse=True)
    contrasting.sort(key=lambda item: item.match_score, reverse=True)

    result_count = len(primary[: payload.max_primary]) + len(contrasting[: payload.max_contrasting])
    if trace is not None:
        trace.result_count = result_count

    return SearchResponse(
        primary_records=primary[: payload.max_primary],
        contrasting_records=contrasting[: payload.max_contrasting],
    )
