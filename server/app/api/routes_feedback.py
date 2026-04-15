from fastapi import APIRouter, Depends

from app.core.security import require_write_library_id
from app.models.feedback import Feedback, FeedbackCreate
from app.services.feedback_service import create_feedback


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=Feedback)
def post_feedback(
    payload: FeedbackCreate,
    _: str | None = Depends(require_write_library_id),
) -> Feedback:
    return create_feedback(payload)
