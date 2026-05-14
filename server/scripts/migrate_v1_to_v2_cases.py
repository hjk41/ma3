from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.time import utc_now_iso  # noqa: E402
from app.models.common import TargetRef  # noqa: E402
from app.models.enums import VerificationLevel  # noqa: E402
from app.models.record import Record  # noqa: E402
from app.models.relation import RecordRelation  # noqa: E402
from app.models.v2 import Case  # noqa: E402
from app.storage.db import _json_param, get_connection, initialize_database  # noqa: E402
from app.storage.repositories import _load_json_payload  # noqa: E402
from app.storage.v2_repositories import CaseRepository  # noqa: E402


RELATION_GROUP_TYPES = {
    "derived_from",
    "supersedes",
    "same_problem_family",
    "conflicts_with",
}

VERIFICATION_SCORE = {
    VerificationLevel.l0: 0,
    VerificationLevel.l1: 1,
    VerificationLevel.l2: 2,
    VerificationLevel.l3: 3,
    VerificationLevel.l4: 4,
}


class DSU:
    def __init__(self, ids: list[str]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, item: str) -> str:
        root = self.parent[item]
        if root != item:
            self.parent[item] = self.find(root)
        return self.parent[item]

    def union(self, a: str, b: str) -> None:
        if a not in self.parent or b not in self.parent:
            return
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _load_records() -> dict[str, Record]:
    with get_connection() as conn:
        rows = conn.execute("SELECT payload_json FROM records").fetchall()
    return {
        rec.record_id: rec
        for row in rows
        for rec in [Record.model_validate(_load_json_payload(row["payload_json"]))]
    }


def _load_relations() -> list[RecordRelation]:
    with get_connection() as conn:
        rows = conn.execute("SELECT payload_json FROM relations").fetchall()
    return [
        RecordRelation.model_validate(_load_json_payload(row["payload_json"]))
        for row in rows
    ]


def _case_id_for(record_ids: list[str]) -> str:
    digest = hashlib.sha256("\n".join(sorted(record_ids)).encode("utf-8")).hexdigest()[:20]
    return f"case_mig_{digest}"


def _group_key(record: Record) -> tuple:
    tags = tuple(sorted(t.lower() for t in record.tags))
    return (
        record.library_id or "",
        record.target.product.lower(),
        (record.target.component or "").lower(),
        record.problem_family.lower(),
        tags,
    )


def _parse_time(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return 0.0


def _canonical(records: list[Record], relations: list[RecordRelation]) -> Record:
    superseded = {
        rel.to_record_id
        for rel in relations
        if getattr(rel.relation_type, "value", rel.relation_type) == "supersedes"
    }

    def score(record: Record) -> tuple:
        outcome = record.result.outcome.lower()
        return (
            0 if record.record_id in superseded else 1,
            1 if outcome == "success" else 0,
            VERIFICATION_SCORE.get(record.verification_level, 0),
            _parse_time(record.updated_at),
            record.record_id,
        )

    return max(records, key=score)


def _title(records: list[Record]) -> str:
    canonical = records[0]
    return f"{canonical.target.product}: {canonical.problem_family or canonical.title}"[:160]


def _build_case(record_ids: list[str], records_by_id: dict[str, Record], relations: list[RecordRelation]) -> Case:
    records = [records_by_id[rid] for rid in sorted(record_ids)]
    canonical = _canonical(records, relations)
    now = utc_now_iso()
    tags = sorted({tag for rec in records for tag in rec.tags})
    latest = max((rec.updated_at for rec in records), default=now)
    return Case(
        case_id=_case_id_for(record_ids),
        library_id=canonical.library_id,
        title=_title([canonical]),
        summary=canonical.summary,
        problem_family=canonical.problem_family,
        target=TargetRef(
            product=canonical.target.product,
            component=canonical.target.component,
        ),
        state="open",
        canonical_record_id=canonical.record_id,
        tags=tags,
        created_at=min((rec.created_at for rec in records), default=now),
        updated_at=latest,
        last_record_at=latest,
        payload={
            "source": "v1_to_v2_migration",
            "record_ids": sorted(record_ids),
        },
    )


def _record_case_updates(groups: list[list[str]]) -> dict[str, str]:
    updates = {}
    for group in groups:
        cid = _case_id_for(group)
        for rid in group:
            updates[rid] = cid
    return updates


def build_groups(records_by_id: dict[str, Record], relations: list[RecordRelation]) -> list[list[str]]:
    dsu = DSU(sorted(records_by_id))
    for rel in relations:
        relation_type = getattr(rel.relation_type, "value", rel.relation_type)
        if relation_type in RELATION_GROUP_TYPES:
            dsu.union(rel.from_record_id, rel.to_record_id)

    connected: dict[str, list[str]] = defaultdict(list)
    for rid in records_by_id:
        connected[dsu.find(rid)].append(rid)

    final_groups: list[list[str]] = []
    unconnected: list[str] = []
    for group in connected.values():
        if len(group) > 1:
            final_groups.append(sorted(group))
        else:
            unconnected.extend(group)

    keyed: dict[tuple, list[str]] = defaultdict(list)
    for rid in unconnected:
        keyed[_group_key(records_by_id[rid])].append(rid)
    final_groups.extend(sorted(group) for group in keyed.values())
    final_groups.sort(key=lambda g: (g[0], len(g)))
    return final_groups


def _write_record_case_id(record: Record, case_id: str) -> None:
    payload = record.model_dump()
    payload["case_id"] = case_id
    with get_connection() as conn:
        conn.execute(
            "UPDATE records SET payload_json = ? WHERE record_id = ?",
            (_json_param(payload), record.record_id),
        )


def run_migration(*, apply: bool = False, report_path: str | None = None) -> dict[str, Any]:
    initialize_database(run_backfill=False)
    records_by_id = _load_records()
    relations = _load_relations()
    groups = build_groups(records_by_id, relations)
    updates = _record_case_updates(groups)

    cases = [_build_case(group, records_by_id, relations) for group in groups]
    already_with_case = sum(1 for record in records_by_id.values() if record.case_id)

    if apply:
        repo = CaseRepository()
        for case in cases:
            repo.insert(case)
        for rid, case_id in updates.items():
            record = records_by_id[rid]
            if record.case_id != case_id:
                _write_record_case_id(record, case_id)

    report = {
        "mode": "apply" if apply else "dry_run",
        "records_total": len(records_by_id),
        "relations_total": len(relations),
        "cases_computed": len(cases),
        "records_already_with_case": already_with_case,
        "records_assigned": len(updates),
        "orphan_records_after": 0 if apply else len(records_by_id) - len(updates),
        "cases": [
            {
                "case_id": case.case_id,
                "record_count": len(case.payload.get("record_ids", [])),
                "canonical_record_id": case.canonical_record_id,
                "title": case.title,
                "target": case.target.model_dump(),
            }
            for case in cases
        ],
    }
    if report_path:
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill v2 Case/Thread assignments from v1 ma3 data.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", required=True, help="Path to write JSON migration report.")
    args = parser.parse_args()
    report = run_migration(apply=args.apply, report_path=args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
