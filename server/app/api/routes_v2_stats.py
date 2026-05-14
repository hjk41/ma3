from fastapi import APIRouter, Depends, Header, Response

from app.core.security import _extract_raw, _is_admin_key, resolve_optional_token, ResolvedToken
from app.services.doctor_service import server_doctor
from app.services.library_service import accessible_library_ids
from app.services.metrics_service import metrics
from app.services.op_log_service import archive_completed_logs
from app.services.v2_stats_service import knowledge_quality, overview, quality_actions, search_stats, topics
from app.models.v2 import TopicsResponse


router = APIRouter(prefix="/v2", tags=["v2-stats"])
metrics_router = APIRouter(tags=["metrics"])


def _admin(x_api_key: str | None, authorization: str | None) -> bool:
    raw = _extract_raw(x_api_key, authorization)
    return bool(raw and _is_admin_key(raw))


@router.get("/stats/overview", response_model=dict)
def stats_overview(
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    return overview(accessible_library_ids(token, is_admin=_admin(x_api_key, authorization)))


@router.get("/stats/search", response_model=dict)
def stats_search() -> dict:
    return search_stats()


@router.get("/stats/knowledge-quality", response_model=dict)
def stats_knowledge_quality(
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    return knowledge_quality(accessible_library_ids(token, is_admin=_admin(x_api_key, authorization)))


@router.get("/stats/quality-actions", response_model=dict)
def stats_quality_actions(
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    return quality_actions(accessible_library_ids(token, is_admin=_admin(x_api_key, authorization)))


@router.get("/topics", response_model=TopicsResponse)
def get_topics(
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> TopicsResponse:
    return topics(accessible_library_ids(token, is_admin=_admin(x_api_key, authorization)))


@router.post("/logs/archive", response_model=dict)
def post_archive_logs() -> dict:
    return archive_completed_logs()


@router.get("/doctor", response_model=dict)
def doctor() -> dict:
    return server_doctor()


@metrics_router.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(metrics.render_prometheus(), media_type="text/plain; version=0.0.4")
