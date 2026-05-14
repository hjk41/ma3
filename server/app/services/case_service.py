from __future__ import annotations

import re

from fastapi import HTTPException

from app.core.ids import new_id
from app.core.time import utc_now_iso
from app.models.common import TargetRef
from app.models.record import Record
from app.models.v2 import Case, CaseAssignment, CaseUpdate, V2AgentReportRequest
from app.services.op_log_service import write_op_log
from app.storage.v2_repositories import CaseRepository


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "general"


def _tag_overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    left = {x.lower() for x in a}
    right = {x.lower() for x in b}
    return len(left & right) / max(1, len(left | right))


def create_case_for_report(payload: V2AgentReportRequest, library_id: str | None) -> Case:
    now = utc_now_iso()
    case = Case(
        case_id=new_id("case"),
        library_id=library_id,
        title=f"{payload.target.product}: {payload.problem[:80]}",
        summary=payload.goal,
        problem_family=slugify(payload.task_type),
        target=payload.target,
        state="open",
        tags=payload.tags,
        created_at=now,
        updated_at=now,
        last_record_at=None,
        payload={"source": "v2_auto_case"},
    )
    CaseRepository().insert(case)
    write_op_log("case_create", case_id=case.case_id, library_id=library_id, payload_summary={"title": case.title})
    return case


def update_case(case: Case, patch: CaseUpdate) -> Case:
    changes = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not changes:
        return case
    changes["updated_at"] = utc_now_iso()
    updated = case.model_copy(update=changes)
    CaseRepository().insert(updated)
    write_op_log("case_update", case_id=case.case_id, library_id=case.library_id, payload_summary={"fields": sorted(changes)})
    return updated


def touch_case_with_record(case: Case, record: Record) -> Case:
    updated = case.model_copy(update={
        "canonical_record_id": case.canonical_record_id or record.record_id,
        "updated_at": record.updated_at,
        "last_record_at": record.created_at,
    })
    CaseRepository().insert(updated)
    write_op_log("case_touch", case_id=case.case_id, record_id=record.record_id, library_id=case.library_id)
    return updated


def assert_case_writeable(case: Case, library_id: str | None) -> None:
    if library_id is not None and case.library_id != library_id:
        raise HTTPException(status_code=403, detail="no write access to this case")


def assign_case(
    payload: V2AgentReportRequest,
    library_id: str | None,
    accessible_library_ids: set[str],
    based_on_records: list[Record],
) -> CaseAssignment:
    repo = CaseRepository()

    if payload.case_id:
        case = repo.get(payload.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="case not found")
        assert_case_writeable(case, library_id)
        return CaseAssignment(
            result="explicit",
            case=case,
            confidence=1.0,
            candidates=[],
            reasons=["explicit case_id supplied by caller"],
            overridden=True,
        )

    if payload.case_assignment_mode == "none":
        return CaseAssignment(result="none", case=None, confidence=0.0, reasons=["case assignment disabled"])

    # Prefer the case of a based-on record when available.
    for record in based_on_records:
        if record.case_id:
            case = repo.get(record.case_id)
            if case is not None:
                return CaseAssignment(
                    result="auto_existing",
                    case=case,
                    confidence=0.95,
                    reasons=[f"based_on record {record.record_id} already belongs to this case"],
                )

    candidates = repo.list_accessible(accessible_library_ids, limit=100)
    scored: list[tuple[float, Case, list[str]]] = []
    problem = payload.problem.lower()
    goal = payload.goal.lower()
    for case in candidates:
        score = 0.0
        reasons: list[str] = []
        if case.target.product == payload.target.product:
            score += 0.35
            reasons.append("target product matched")
        if case.target.component and case.target.component == payload.target.component:
            score += 0.15
            reasons.append("target component matched")
        if case.problem_family == slugify(payload.task_type):
            score += 0.2
            reasons.append("problem family matched")
        overlap = _tag_overlap(case.tags, payload.tags)
        if overlap:
            score += min(0.2, overlap * 0.2)
            reasons.append("tags overlapped")
        haystack = f"{case.title} {case.summary}".lower()
        terms = [t for t in re.split(r"\\W+", problem + " " + goal) if len(t) > 3]
        hits = [t for t in terms[:12] if t in haystack]
        if hits:
            score += min(0.2, len(set(hits)) * 0.04)
            reasons.append("case text overlapped")
        if score > 0:
            scored.append((round(score, 3), case, reasons))

    scored.sort(key=lambda item: item[0], reverse=True)
    candidate_payload = [
        {"case_id": c.case_id, "title": c.title, "confidence": s, "reasons": r}
        for s, c, r in scored[:5]
    ]
    if scored and scored[0][0] >= 0.55 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15):
        return CaseAssignment(
            result="auto_existing",
            case=scored[0][1],
            confidence=scored[0][0],
            candidates=candidate_payload,
            reasons=scored[0][2],
        )

    case = create_case_for_report(payload, library_id)
    return CaseAssignment(
        result="auto_new" if not scored else "ambiguous_new",
        case=case,
        confidence=scored[0][0] if scored else 0.0,
        candidates=candidate_payload,
        reasons=["no existing case crossed auto-assignment threshold"],
    )
