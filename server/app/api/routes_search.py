import hashlib

from fastapi import APIRouter, Depends, Header

from app.core.security import resolve_optional_token, ResolvedToken, _extract_raw, _is_admin_key
from app.models.query import SearchQuery
from app.models.result import SearchResponse
from app.services.library_service import accessible_library_ids
from app.services.search_service import search_records
from app.services.metrics_service import metrics
from app.services.op_log_service import write_op_log
from app.services.perf_service import search_perf_trace
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.storage.v2_repositories import SearchEventRepository


router = APIRouter(tags=["search"])


def _query_hash(payload: SearchQuery) -> str:
    raw = payload.model_dump_json(exclude={"config_excerpt"})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@router.post("/search", response_model=SearchResponse)
def post_search(
    payload: SearchQuery,
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> SearchResponse:
    raw = _extract_raw(x_api_key, authorization)
    is_admin = bool(raw and _is_admin_key(raw))
    library_ids = accessible_library_ids(token, is_admin=is_admin)
    qh = _query_hash(payload)
    with search_perf_trace("/search", qh) as trace:
        response = search_records(payload, library_ids)
    summary = trace.finish()
    result_count = len(response.primary_records) + len(response.contrasting_records)
    duration = float(summary.get("total_ms", 0.0)) / 1000.0
    metrics.record_search("full_scan" if summary.get("full_scan") else "hybrid", duration, result_count)
    metrics.record_search_perf("/search", summary)
    write_op_log(
        "search_perf",
        route="/search",
        library_id=token.library_id if token else None,
        query_hash=qh,
        latency_ms=summary.get("total_ms"),
        result_count=result_count,
        payload_summary={
            "task_type": payload.task_type,
            "target": payload.target.model_dump(),
            "tags": payload.tags,
        },
        perf=summary,
    )
    SearchEventRepository().insert_event({
        "event_id": new_id("se"),
        "library_id": token.library_id if token else None,
        "created_at": utc_now_iso(),
        "route": "/search",
        "latency_ms": summary.get("total_ms", 0.0),
        "result_count": result_count,
        "case_count": 0,
        "full_scan": bool(summary.get("full_scan")),
        "query_hash": qh,
        "ranking_config_version": None,
        "perf": summary,
    })
    return response
