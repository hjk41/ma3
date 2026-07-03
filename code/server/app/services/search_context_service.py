from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchContext:
    task_type: str | None = None
    target_product: str | None = None
    target_component: str | None = None
    tags: list[str] = field(default_factory=list)
    environment: dict[str, Any] | None = None


def context_boost(payload: dict[str, Any], ctx: SearchContext | None) -> float:
    if ctx is None:
        return 1.0
    boost = 1.0
    if ctx.task_type and payload.get("task_type") == ctx.task_type:
        boost *= 1.1
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    if ctx.target_product:
        if payload.get("target_product") == ctx.target_product or target.get("product") == ctx.target_product:
            boost *= 1.15
    if ctx.target_component:
        if payload.get("target_component") == ctx.target_component or target.get("component") == ctx.target_component:
            boost *= 1.1
    query_tags = {str(t).lower() for t in ctx.tags if t}
    record_tags = {str(t).lower() for t in (payload.get("tags") or []) if t}
    if query_tags and record_tags and query_tags & record_tags:
        boost *= 1.1
    if ctx.environment:
        env_text = " ".join(f"{k}={v}" for k, v in sorted(ctx.environment.items()) if v is not None).lower()
        for rule in payload.get("applicable_if") or []:
            rule_s = str(rule).strip().lower()
            if rule_s and (rule_s in env_text or rule_s.replace(" ", "") in env_text.replace(" ", "")):
                boost *= 1.1
                break
        for rule in payload.get("not_applicable_if") or []:
            rule_s = str(rule).strip().lower()
            if rule_s and (rule_s in env_text or rule_s.replace(" ", "") in env_text.replace(" ", "")):
                boost *= 0.5
                break
    return boost
