from pydantic import BaseModel


class AgentAction(BaseModel):
    action: str
    rationale: str | None = None
    ref: str | None = None
    note: str | None = None

    model_config = {"extra": "forbid"}
