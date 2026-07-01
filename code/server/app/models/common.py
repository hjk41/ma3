from pydantic import BaseModel, Field


class TargetRef(BaseModel):
    product: str
    component: str | None = None


class EnvironmentFingerprint(BaseModel):
    """All fields are optional so non-technical records (e.g. travel tips) can omit them."""
    os: str | None = None
    shell: str | None = None
    runtime: str | None = None
    sandbox: str | None = None
    workspace_boundary: str | None = None
    network_profile: str | None = None


class VersionInfo(BaseModel):
    agent: str | None = None
    target: str | None = None


class StepItem(BaseModel):
    order: int = Field(ge=1)
    action: str
    note: str | None = None


class EvidenceItem(BaseModel):
    kind: str
    summary: str
    ref: str | None = None


class ResultSummary(BaseModel):
    outcome: str
    summary: str
    details: list[str] = Field(default_factory=list)
