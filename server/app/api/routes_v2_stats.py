from fastapi import APIRouter, Depends, Response

from app.core.security import ResolvedPrincipal, current_principal
from app.services.doctor_service import server_doctor
from app.services.library_service import effective_library_ids
from app.services.metrics_service import metrics
from app.services.op_log_service import archive_completed_logs
from app.services.v2_stats_service import knowledge_quality, overview, quality_actions, search_stats, topics
from app.models.v2 import TopicsResponse


router = APIRouter(prefix="/v2", tags=["v2-stats"])
metrics_router = APIRouter(tags=["metrics"])



@router.get("/stats/overview", response_model=dict)
def stats_overview(
    principal: ResolvedPrincipal = Depends(current_principal),
) -> dict:
    return overview(effective_library_ids(principal))


@router.get("/stats/search", response_model=dict)
def stats_search() -> dict:
    return search_stats()


@router.get("/stats/knowledge-quality", response_model=dict)
def stats_knowledge_quality(
    principal: ResolvedPrincipal = Depends(current_principal),
) -> dict:
    return knowledge_quality(effective_library_ids(principal))


@router.get("/stats/quality-actions", response_model=dict)
def stats_quality_actions(
    principal: ResolvedPrincipal = Depends(current_principal),
) -> dict:
    return quality_actions(effective_library_ids(principal))


@router.get("/topics", response_model=TopicsResponse)
def get_topics(
    principal: ResolvedPrincipal = Depends(current_principal),
) -> TopicsResponse:
    return topics(effective_library_ids(principal))


@router.post("/logs/archive", response_model=dict)
def post_archive_logs() -> dict:
    return archive_completed_logs()


@router.get("/doctor", response_model=dict)
def doctor() -> dict:
    return server_doctor()


@metrics_router.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(metrics.render_prometheus(), media_type="text/plain; version=0.0.4")
