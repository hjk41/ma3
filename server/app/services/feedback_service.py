from fastapi import HTTPException

from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.feedback import Feedback, FeedbackCreate
from app.services.redaction import redact_value
from app.storage.repositories import FeedbackRepository, RecordRepository


def create_feedback(payload: FeedbackCreate) -> Feedback:
    if RecordRepository().get(payload.record_id) is None:
        raise HTTPException(status_code=404, detail="record not found")

    sanitized = FeedbackCreate.model_validate(redact_value(payload.model_dump()))
    feedback = Feedback(
        feedback_id=new_id("fb"),
        created_at=utc_now_iso(),
        **sanitized.model_dump(),
    )
    FeedbackRepository().insert(feedback)
    return feedback
