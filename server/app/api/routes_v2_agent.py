from fastapi import APIRouter, Depends, Header

from app.core.security import _extract_raw, _is_admin_key, require_write_library_id, resolve_optional_token, ResolvedToken
from app.models.v2 import (
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    V2AgentContextRequest,
    V2AgentContextResponse,
    V2AgentReportRequest,
    V2AgentReportResponse,
)
from app.services.library_service import accessible_library_ids
from app.services.op_log_service import write_op_log
from app.services.v2_agent_service import ingest_v2_agent_report
from app.services.v2_search_service import build_agent_context
from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.storage.v2_repositories import SearchEventRepository


router = APIRouter(prefix="/v2/agent", tags=["v2-agent"])
search_router = APIRouter(prefix="/v2/search", tags=["v2-search"])


def _is_admin(x_api_key: str | None, authorization: str | None) -> bool:
    raw = _extract_raw(x_api_key, authorization)
    return bool(raw and _is_admin_key(raw))


@router.post("/context", response_model=V2AgentContextResponse)
def post_context(
    payload: V2AgentContextRequest,
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> V2AgentContextResponse:
    return build_agent_context(
        payload,
        accessible_library_ids(token, is_admin=_is_admin(x_api_key, authorization)),
        library_id=token.library_id if token else None,
        route="/v2/agent/context",
    )


@router.post("/report", response_model=V2AgentReportResponse)
def post_report(
    payload: V2AgentReportRequest,
    library_id: str | None = Depends(require_write_library_id),
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> V2AgentReportResponse:
    return ingest_v2_agent_report(
        payload,
        library_id=library_id,
        accessible_library_ids=accessible_library_ids(token, is_admin=_is_admin(x_api_key, authorization)),
    )


@search_router.post("/explain", response_model=V2AgentContextResponse)
def post_search_explain(
    payload: V2AgentContextRequest,
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> V2AgentContextResponse:
    return build_agent_context(
        payload.model_copy(update={"include_explain": True}),
        accessible_library_ids(token, is_admin=_is_admin(x_api_key, authorization)),
        library_id=token.library_id if token else None,
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
