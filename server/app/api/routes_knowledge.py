from fastapi import APIRouter, Depends

from app.core.security import v3_write_library
from app.models.knowledge import KnowledgeCreate
from app.models.record import Record
from app.services.knowledge_service import create_knowledge


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("", response_model=Record)
def post_knowledge(
    payload: KnowledgeCreate,
    library_id: str | None = Depends(v3_write_library),
) -> Record:
    """Write a knowledge record using the Q&A mental model.

    Required fields:
    - **question**: What question does this answer? (retrieval anchor)
    - **summary**: What is the answer?
    - **source_type**: How do you know? (agent_verified | authority_defined | measured | derived | referenced)
    - **knowledge_kind**: What type of knowledge is this? (process_protocol | experience | measurement | ...)

    Optional but useful:
    - **scope**: Where is this knowledge valid? (e.g. "行云致理内部")
    - **visibility_scope**: public | tenant | group | private
    - **source_ref**: Document or reference title
    - **authority**: Who defined this? (for authority_defined records)
    """
    return create_knowledge(payload, library_id=library_id)
