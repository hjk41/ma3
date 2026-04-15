from pydantic import BaseModel, Field

from app.models.common import EnvironmentFingerprint, TargetRef, VersionInfo


class SearchQuery(BaseModel):
    problem: str
    query_intent: str
    task_type: str
    target: TargetRef
    goal: str
    environment: EnvironmentFingerprint | None = None
    versions: VersionInfo | None = None
    observations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    config_excerpt: str | None = None
    max_primary: int = Field(default=3, ge=1, le=20)
    max_contrasting: int = Field(default=2, ge=0, le=10)
