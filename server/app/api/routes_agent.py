from fastapi import APIRouter, Depends

from app.core.security import v3_write_library
from app.models.agent import AgentIngestRequest, AgentIngestResponse
from app.services.agent_service import ingest_agent_report


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ingest", response_model=AgentIngestResponse)
def post_agent_ingest(
    payload: AgentIngestRequest,
    library_id: str | None = Depends(v3_write_library),
) -> AgentIngestResponse:
    return ingest_agent_report(payload, library_id=library_id)
