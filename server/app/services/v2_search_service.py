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


RANKING_CONFIG_VERSION = "v2.0.0-initial"


def query_hash(payload: V2AgentContextRequest | dict) -> str:
    if hasattr(payload, "model_dump_json"):
        raw = payload.model_dump_json(exclude={"include_explain"})
    else:
        raw = repr(sorted(payload.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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
        max_primary=min(20, payload.max_cases * payload.max_records_per_case),
        max_contrasting=3,
    )


def build_agent_context(
    payload: V2AgentContextRequest,
    accessible_library_ids: set[str],
    library_id: str | None = None,
) -> V2AgentContextResponse:
    started = time.perf_counter()
    qh = query_hash(payload)
    v1_response = search_records(_to_v1_query(payload), accessible_library_ids)
    matches = v1_response.primary_records
    record_ids = {m.record.record_id for m in matches}
    case_ids = {m.record.case_id for m in matches if m.record.case_id}
    cases_by_id = {c.case_id: c for c in CaseRepository().list_by_ids_accessible(case_ids, accessible_library_ids)}
    relations_by_record = V2GraphRepository().relations_by_record_ids(record_ids)

    groups: dict[str, V2CaseRecordGroup] = {}
    ungrouped = []
    score_breakdown = []
    for match in matches:
        rec = match.record
        score_breakdown.append({
            "record_id": rec.record_id,
            "case_id": rec.case_id,
            "score": match.match_score,
            "reasons": match.why_matched,
        })
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
        explain = V2SearchExplain(
            query_hash=qh,
            ranking_config_version=RANKING_CONFIG_VERSION,
            candidate_count=len(matches) + len(v1_response.contrasting_records),
            returned_record_count=sum(len(g.records) for g in ordered_groups) + len(ungrouped),
            returned_case_count=len(ordered_groups),
            full_scan=full_scan,
            stages=[
                {"name": "v1_candidate_search", "records": len(matches), "contrasting": len(v1_response.contrasting_records)},
                {"name": "case_grouping", "cases": len(ordered_groups), "ungrouped_records": len(ungrouped)},
            ],
            score_breakdown=score_breakdown,
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
