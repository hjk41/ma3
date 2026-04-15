from __future__ import annotations

from app.models.enums import RecordStatus, RiskLevel, VerificationLevel
from app.models.query import SearchQuery
from app.models.result import SearchMatch, SearchResponse
from app.storage.fts import fts_tag_search, fts_content_search
from app.storage.repositories import FeedbackRepository, RecordRepository, RelationRepository
from app.services.embedding_service import embed_text
from app.services.scoring import score_record


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
        tag_hits = fts_tag_search(problem, accessible_library_ids)
        content_hits = fts_content_search(problem, accessible_library_ids)
        fts_tag_scores = dict(tag_hits)
        fts_content_scores = dict(content_hits)
        candidate_ids = set(fts_tag_scores) | set(fts_content_scores)

    # Explicit tag filter on the query (SearchQuery.tags) — direct record_id
    # boost even when tags don't appear verbatim in the problem text.
    if payload.tags:
        tag_query = " ".join(payload.tags)
        extra_hits = fts_tag_search(tag_query, accessible_library_ids, limit=40)
        if extra_hits:
            extra_ids = {r for r, _ in extra_hits}
            candidate_ids = (candidate_ids or set()) | extra_ids
            for r, s in extra_hits:
                # Boost explicit tag hits above regular problem-text tag hits
                fts_tag_scores[r] = max(fts_tag_scores.get(r, 0.0), s * 1.5)

    # Fetch records: batch lookup when candidates exist, full scan as fallback
    if candidate_ids:
        records = record_repo.get_batch_accessible(candidate_ids, accessible_library_ids)
    else:
        records = record_repo.list_accessible(accessible_library_ids)

    # ── Stage 2: Embed query + batch-load record embeddings ───────────────────
    query_embedding = embed_text(problem) if problem else None
    all_ids = {r.record_id for r in records}
    record_embeddings = record_repo.get_embeddings_batch(all_ids)

    # ── Stage 3: Score and classify ───────────────────────────────────────────
    primary: list[SearchMatch] = []
    contrasting: list[SearchMatch] = []

    for record in records:
        if record.status != RecordStatus.active:
            continue
        if record.verification_level == VerificationLevel.l0:
            continue
        if record.risk_level == RiskLevel.critical:
            continue

        feedback_items = feedback_repo.list_by_record(record.record_id)
        relations = relation_repo.list_by_record(record.record_id)
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

    primary.sort(key=lambda item: item.match_score, reverse=True)
    contrasting.sort(key=lambda item: item.match_score, reverse=True)

    return SearchResponse(
        primary_records=primary[: payload.max_primary],
        contrasting_records=contrasting[: payload.max_contrasting],
    )
