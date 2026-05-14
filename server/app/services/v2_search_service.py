from __future__ import annotations

import hashlib
import time

from app.core.config import settings
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.query import SearchQuery
from app.models.v2 import (
    V2AgentContextRequest,
    V2AgentContextResponse,
    V2CaseRecordGroup,
    V2SearchExplain,
)
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.services.search_service import search_records
from app.storage.v2_repositories import CaseRepository, SearchEventRepository, V2GraphRepository


RANKING_CONFIG_VERSION = "v2.1.0-metadata-rerank"
MIN_INTERNAL_CANDIDATES = 50
MAX_INTERNAL_CANDIDATES = 100
_COMMON_QUERY_TAGS = {
    "api",
    "app",
    "bug",
    "client",
    "config",
    "debug",
    "deploy",
    "deployment",
    "error",
    "fix",
    "issue",
    "job",
    "knowledge",
    "linux",
    "ltp",
    "ma3",
    "server",
    "service",
    "test",
    "ui",
}


def query_hash(payload: V2AgentContextRequest | dict) -> str:
    if hasattr(payload, "model_dump_json"):
        raw = payload.model_dump_json(exclude={"include_explain"})
    else:
        raw = repr(sorted(payload.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _candidate_pool_limit(payload: V2AgentContextRequest) -> int:
    requested = payload.max_cases * payload.max_records_per_case
    return min(MAX_INTERNAL_CANDIDATES, max(MIN_INTERNAL_CANDIDATES, requested * 4))


def _to_v1_query(payload: V2AgentContextRequest) -> SearchQuery:
    return SearchQuery(
        problem=payload.problem,
        query_intent="agent_context",
        task_type=payload.task_type,
        target=payload.target,
        goal=payload.goal,
        environment=payload.environment,
        versions=payload.versions,
        observations=payload.observations,
        constraints=payload.constraints,
        tags=payload.tags,
        max_primary=_candidate_pool_limit(payload),
        max_contrasting=3,
    )


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_rare_tag(tag: str) -> bool:
    tag = _norm(tag)
    if not tag or tag in _COMMON_QUERY_TAGS:
        return False
    return len(tag) >= 3 or any(ch.isdigit() or ch in "-_+./" for ch in tag)


def _metadata_boost(payload: V2AgentContextRequest, match) -> tuple[float, list[str], dict]:
    record = match.record
    query_tags = {_norm(tag) for tag in payload.tags if _norm(tag)}
    record_tags = {_norm(tag) for tag in record.tags if _norm(tag)}
    matched_tags = sorted(query_tags & record_tags)

    boost = 0.0
    reasons: list[str] = []
    rare_tags = [tag for tag in matched_tags if _is_rare_tag(tag)]
    if matched_tags:
        tag_boost = len(matched_tags) * 2.0
        boost += tag_boost
        reasons.append(f"v2 exact tag boost: {', '.join(matched_tags[:8])} (+{tag_boost:.1f})")
    if rare_tags:
        rare_boost = len(rare_tags) * 2.0
        boost += rare_boost
        reasons.append(f"v2 rare tag boost: {', '.join(rare_tags[:8])} (+{rare_boost:.1f})")
    if len(matched_tags) >= 3:
        synergy = min(6.0, 1.5 * (len(matched_tags) - 2))
        boost += synergy
        reasons.append(f"v2 multi-tag synergy: {len(matched_tags)} tags (+{synergy:.1f})")

    target_product_match = False
    target_component_match = False
    if _norm(payload.target.product) and _norm(payload.target.product) == _norm(record.target.product):
        target_product_match = True
        boost += 3.0
        reasons.append("v2 target product exact (+3.0)")
    if _norm(payload.target.component) and _norm(payload.target.component) == _norm(record.target.component):
        target_component_match = True
        boost += 2.0
        reasons.append("v2 target component exact (+2.0)")

    haystack = " ".join([
        record.title,
        record.problem_family,
        record.summary,
        record.claim,
    ]).lower()
    title_term_hits = [tag for tag in query_tags if _is_rare_tag(tag) and tag in haystack and tag not in record_tags]
    if title_term_hits:
        text_boost = min(4.0, len(title_term_hits) * 1.0)
        boost += text_boost
        reasons.append(f"v2 rare term text boost: {', '.join(title_term_hits[:8])} (+{text_boost:.1f})")

    details = {
        "base_score": match.match_score,
        "v2_boost": round(boost, 3),
        "final_score": round(match.match_score + boost, 3),
        "matched_query_tags": matched_tags,
        "rare_matched_tags": rare_tags,
        "target_product_match": target_product_match,
        "target_component_match": target_component_match,
    }
    return boost, reasons, details


def _rerank_matches(payload: V2AgentContextRequest, matches: list) -> tuple[list, list[dict]]:
    reranked = []
    breakdown = []
    for match in matches:
        boost, boost_reasons, details = _metadata_boost(payload, match)
        final_score = round(match.match_score + boost, 3)
        reasons = list(match.why_matched)
        reasons.extend(boost_reasons)
        updated = match.model_copy(update={"match_score": final_score, "why_matched": reasons[:10]})
        reranked.append(updated)
        breakdown.append({
            "record_id": match.record.record_id,
            "case_id": match.record.case_id,
            "title": match.record.title,
            "base_score": details["base_score"],
            "v2_boost": details["v2_boost"],
            "score": details["final_score"],
            "reasons": reasons[:10],
            "matched_query_tags": details["matched_query_tags"],
            "rare_matched_tags": details["rare_matched_tags"],
            "target_product_match": details["target_product_match"],
            "target_component_match": details["target_component_match"],
        })
    reranked.sort(key=lambda item: item.match_score, reverse=True)
    breakdown.sort(key=lambda item: item["score"], reverse=True)
    return reranked, breakdown


def build_agent_context(
    payload: V2AgentContextRequest,
    accessible_library_ids: set[str],
    library_id: str | None = None,
) -> V2AgentContextResponse:
    started = time.perf_counter()
    qh = query_hash(payload)
    v1_response = search_records(_to_v1_query(payload), accessible_library_ids)
    candidate_pool_limit = _candidate_pool_limit(payload)
    matches, score_breakdown = _rerank_matches(payload, v1_response.primary_records)
    record_ids = {m.record.record_id for m in matches}
    case_ids = {m.record.case_id for m in matches if m.record.case_id}
    cases_by_id = {c.case_id: c for c in CaseRepository().list_by_ids_accessible(case_ids, accessible_library_ids)}
    relations_by_record = V2GraphRepository().relations_by_record_ids(record_ids)

    groups: dict[str, V2CaseRecordGroup] = {}
    ungrouped = []
    for match in matches:
        rec = match.record
        if rec.case_id and rec.case_id in cases_by_id:
            group = groups.setdefault(
                rec.case_id,
                V2CaseRecordGroup(
                    case=cases_by_id[rec.case_id],
                    records=[],
                    relations=[],
                    match_score=match.match_score,
                    why_matched=list(match.why_matched),
                ),
            )
            if len(group.records) < payload.max_records_per_case:
                group.records.append(rec)
            group.relations.extend(relations_by_record.get(rec.record_id, []))
            group.match_score = max(group.match_score, match.match_score)
        else:
            ungrouped.append(rec)

    ordered_groups = sorted(groups.values(), key=lambda g: g.match_score, reverse=True)[: payload.max_cases]
    explain = None
    full_scan = not payload.problem.strip()
    if payload.include_explain:
        returned_case_ids = {group.case.case_id for group in ordered_groups}
        debug_candidates = []
        for item in score_breakdown[:20]:
            debug_candidates.append({
                **item,
                "returned": bool(item.get("case_id") in returned_case_ids or not item.get("case_id")),
            })
        explain = V2SearchExplain(
            query_hash=qh,
            ranking_config_version=RANKING_CONFIG_VERSION,
            candidate_count=len(matches) + len(v1_response.contrasting_records),
            candidate_pool_limit=candidate_pool_limit,
            returned_record_count=sum(len(g.records) for g in ordered_groups) + len(ungrouped),
            returned_case_count=len(ordered_groups),
            full_scan=full_scan,
            stages=[
                {
                    "name": "v1_candidate_search",
                    "records": len(v1_response.primary_records),
                    "contrasting": len(v1_response.contrasting_records),
                    "candidate_pool_limit": candidate_pool_limit,
                },
                {"name": "v2_metadata_rerank", "records": len(matches), "ranking_config_version": RANKING_CONFIG_VERSION},
                {"name": "case_grouping", "cases": len(ordered_groups), "ungrouped_records": len(ungrouped)},
            ],
            score_breakdown=score_breakdown,
            debug_candidates=debug_candidates,
        )

    duration = time.perf_counter() - started
    result_count = sum(len(g.records) for g in ordered_groups) + len(ungrouped)
    metrics.record_search("full_scan" if full_scan else "hybrid", duration, result_count)
    write_op_log(
        "agent_context",
        route="/v2/agent/context",
        library_id=library_id,
        query_hash=qh,
        latency_ms=round(duration * 1000, 3),
        result_count=result_count,
        case_count=len(ordered_groups),
        full_scan=full_scan,
        ranking_config_version=RANKING_CONFIG_VERSION,
        payload_summary={
            "task_type": payload.task_type,
            "target": payload.target.model_dump(),
            "tags": payload.tags,
        },
    )
    SearchEventRepository().insert_event({
        "event_id": new_id("se"),
        "library_id": library_id,
        "created_at": utc_now_iso(),
        "route": "/v2/agent/context",
        "latency_ms": round(duration * 1000, 3),
        "result_count": result_count,
        "case_count": len(ordered_groups),
        "full_scan": full_scan,
        "query_hash": qh,
        "ranking_config_version": RANKING_CONFIG_VERSION,
    })

    warnings = []
    if full_scan:
        warnings.append("empty problem triggered full-scan fallback")
    return V2AgentContextResponse(
        cases=ordered_groups,
        ungrouped_records=ungrouped[: payload.max_records_per_case],
        warnings=warnings,
        explain=explain,
        server={
            "version": settings.service_version,
            "ranking_config_version": RANKING_CONFIG_VERSION,
            "features": ["v2_agent_context", "case_grouping", "search_explain"],
        },
    )
