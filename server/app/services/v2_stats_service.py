from __future__ import annotations

from collections import Counter

from app.models.enums import RecordStatus
from app.storage.repositories import LibraryRepository, RecordRepository, RelationRepository
from app.storage.v2_repositories import CaseRepository, SearchEventRepository, V2RecordRepository
from app.models.v2 import TopicBucket, TopicsResponse


def overview(accessible_library_ids: set[str]) -> dict:
    records = RecordRepository().list_accessible(accessible_library_ids)
    cases_total = CaseRepository().count(accessible_library_ids)
    status_counts = Counter(str(r.status.value if hasattr(r.status, "value") else r.status) for r in records)
    with_case = sum(1 for r in records if r.case_id)
    return {
        "records_total": len(records),
        "cases_total": cases_total,
        "libraries_total": len(LibraryRepository().list_all()),
        "record_status": dict(status_counts),
        "case_coverage": {
            "records_with_case": with_case,
            "records_without_case": len(records) - with_case,
            "percentage": round((with_case / len(records)) * 100, 2) if records else 0.0,
        },
    }


def search_stats() -> dict:
    return SearchEventRepository().stats()


def knowledge_quality(accessible_library_ids: set[str]) -> dict:
    records = RecordRepository().list_accessible(accessible_library_ids)
    cases = CaseRepository().list_accessible(accessible_library_ids, limit=1000)
    orphan_records = [r.record_id for r in records if not r.case_id]
    cases_without_canonical = [c.case_id for c in cases if not c.canonical_record_id]
    stale_records = [r.record_id for r in records if r.status == RecordStatus.stale]
    return {
        "orphan_records": orphan_records[:100],
        "orphan_records_total": len(orphan_records),
        "cases_without_canonical_record": cases_without_canonical[:100],
        "cases_without_canonical_record_total": len(cases_without_canonical),
        "stale_records": stale_records[:100],
        "stale_records_total": len(stale_records),
    }


def quality_actions(accessible_library_ids: set[str]) -> dict:
    quality = knowledge_quality(accessible_library_ids)
    actions = []
    for rid in quality["orphan_records"][:20]:
        actions.append({
            "kind": "orphan_record",
            "severity": "medium",
            "record_id": rid,
            "reason": "record has no v2 case assignment",
            "suggested_action": "assign to an existing case or create a new case",
        })
    for cid in quality["cases_without_canonical_record"][:20]:
        actions.append({
            "kind": "case_without_canonical_record",
            "severity": "low",
            "case_id": cid,
            "reason": "case has no canonical record",
            "suggested_action": "select the best current record as canonical",
        })
    return {"actions": actions, "total": len(actions)}


def topics(accessible_library_ids: set[str]) -> TopicsResponse:
    records = RecordRepository().list_accessible(accessible_library_ids)
    cases = CaseRepository().list_accessible(accessible_library_ids, limit=10000)
    products: Counter[str] = Counter()
    components: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    families: Counter[str] = Counter()

    for record in records:
        if record.target.product:
            products[record.target.product] += 1
        if record.target.component:
            components[f"{record.target.product}/{record.target.component}"] += 1
        if record.problem_family:
            families[record.problem_family] += 1
        for tag in record.tags:
            tags[tag] += 1

    def buckets(counter: Counter[str], kind: str) -> list[TopicBucket]:
        return [
            TopicBucket(name=name, count=count, kind=kind)
            for name, count in counter.most_common(50)
        ]

    return TopicsResponse(
        products=buckets(products, "product"),
        components=buckets(components, "component"),
        tags=buckets(tags, "tag"),
        problem_families=buckets(families, "problem_family"),
        totals={
            "records": len(records),
            "cases": len(cases),
            "records_with_case": sum(1 for r in records if r.case_id),
        },
    )
