from fastapi import APIRouter, Depends, Header

from app.core.security import resolve_optional_token, ResolvedToken, _extract_raw, _is_admin_key
from app.models.query import SearchQuery
from app.models.result import SearchResponse
from app.services.library_service import accessible_library_ids
from app.services.search_service import search_records


router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def post_search(
    payload: SearchQuery,
    token: ResolvedToken | None = Depends(resolve_optional_token),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> SearchResponse:
    raw = _extract_raw(x_api_key, authorization)
    is_admin = bool(raw and _is_admin_key(raw))
    return search_records(payload, accessible_library_ids(token, is_admin=is_admin))
