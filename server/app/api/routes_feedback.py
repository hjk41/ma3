from fastapi import APIRouter, Depends

from app.core.security import v3_write_library
from app.models.feedback import Feedback, FeedbackCreate
from app.services.feedback_service import create_feedback


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=Feedback)
def post_feedback(
    payload: FeedbackCreate,
    _: str | None = Depends(v3_write_library),
) -> Feedback:
    return create_feedback(payload)
