from fastapi import APIRouter, Depends

from app.core.security import ResolvedPrincipal, current_principal, v3_write_library
from app.models.v2 import (
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    V2AgentContextRequest,
    V2AgentContextResponse,
    V2AgentReportRequest,
    V2AgentReportResponse,
)
from app.services.library_service import effective_library_ids
from app.services.op_log_service import write_op_log
from app.services.v2_agent_service import ingest_v2_agent_report
from app.services.v2_search_service import build_agent_context
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.storage.v2_repositories import SearchEventRepository


router = APIRouter(prefix="/v2/agent", tags=["v2-agent"])
search_router = APIRouter(prefix="/v2/search", tags=["v2-search"])


@router.post("/context", response_model=V2AgentContextResponse)
def post_context(
    payload: V2AgentContextRequest,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> V2AgentContextResponse:
    return build_agent_context(
        payload,
        effective_library_ids(principal),
        library_id=principal.library_id,
        route="/v2/agent/context",
    )


@router.post("/report", response_model=V2AgentReportResponse)
def post_report(
    payload: V2AgentReportRequest,
    library_id: str | None = Depends(v3_write_library),
    principal: ResolvedPrincipal = Depends(current_principal),
) -> V2AgentReportResponse:
    return ingest_v2_agent_report(
        payload,
        library_id=library_id,
        accessible_library_ids=effective_library_ids(principal),
    )


@search_router.post("/explain", response_model=V2AgentContextResponse)
def post_search_explain(
    payload: V2AgentContextRequest,
    principal: ResolvedPrincipal = Depends(current_principal),
) -> V2AgentContextResponse:
    return build_agent_context(
        payload.model_copy(update={"include_explain": True}),
        effective_library_ids(principal),
        library_id=principal.library_id,
        route="/v2/search/explain",
    )


@search_router.post("/feedback", response_model=SearchFeedbackResponse)
def post_search_feedback(payload: SearchFeedbackRequest) -> SearchFeedbackResponse:
    feedback_id = new_id("sf")
    SearchEventRepository().insert_feedback({
        "feedback_id": feedback_id,
        "query_hash": payload.query_hash or payload.query_id,
        "record_id": payload.record_id,
        "case_id": payload.case_id,
        "judgment": payload.judgment,
        "expected_record_id": payload.expected_record_id,
        "comment": payload.comment,
        "created_at": utc_now_iso(),
    })
    write_op_log(
        "search_feedback",
        query_hash=payload.query_hash or payload.query_id,
        record_id=payload.record_id,
        case_id=payload.case_id,
        payload_summary={"judgment": payload.judgment, "has_comment": bool(payload.comment)},
    )
    return SearchFeedbackResponse(feedback_id=feedback_id)
