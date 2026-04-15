from fastapi import APIRouter, Depends

from app.core.security import require_write_library_id
from app.models.agent import AgentIngestRequest, AgentIngestResponse
from app.services.agent_service import ingest_agent_report


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ingest", response_model=AgentIngestResponse)
def post_agent_ingest(
    payload: AgentIngestRequest,
    library_id: str | None = Depends(require_write_library_id),
) -> AgentIngestResponse:
    return ingest_agent_report(payload, library_id=library_id)
