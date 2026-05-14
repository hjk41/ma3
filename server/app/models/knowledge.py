from pydantic import BaseModel, Field
from typing import Literal

from app.models.enums import KnowledgeKind, RecordStatus, SourceType, VisibilityScope


class KnowledgeCreate(BaseModel):
    """Simplified write model for the /knowledge endpoint.

    Anchored on a question + answer pair rather than an agent experience record.
    The three required fields mirror the contribution interface:
      1. What question does this answer?  → question
      2. What is the answer?              → summary
      3. How do you know?                 → source_type
    """

    question: str
    summary: str
    source_type: SourceType
    knowledge_kind: KnowledgeKind

    # Source provenance — semantics depend on source_type
    source_ref: str | None = None    # e.g. "费用报销制度 v2.1"
    source_uri: str | None = None    # link to the authoritative document
    authority: str | None = None     # for authority_defined: "HR 部门"

    # Scope and visibility
    scope: str | None = None                                     # e.g. "行云致理内部"
    visibility_scope: VisibilityScope = VisibilityScope.public

    # Optional title override (defaults to question)
    title: str | None = None

    status: RecordStatus = RecordStatus.active
    applicable_if: list[str] = Field(default_factory=list)
    not_applicable_if: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Measurement / environment conditions (for measured / agent_verified kinds)
    conditions: dict | None = None
    redaction_mode: Literal["auto", "contextual", "none"] = "auto"
