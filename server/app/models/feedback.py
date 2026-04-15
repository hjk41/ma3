from typing import Optional

from pydantic import BaseModel

from app.models.common import EnvironmentFingerprint, ResultSummary
from app.models.enums import FeedbackType


class FeedbackCreate(BaseModel):
    record_id: str
    feedback_type: FeedbackType
    summary: str
    environment: Optional[EnvironmentFingerprint] = None
    result: ResultSummary


class Feedback(FeedbackCreate):
    feedback_id: str
    created_at: str
