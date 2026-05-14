from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models.feedback import Feedback
from app.models.record import Record
from app.models.relation import RecordRelation
from app.models.v2 import Case
from app.storage.db import _json_param, _upsert, get_connection, is_postgres
from app.storage.repositories import _load_json_payload


def _row_to_case(row) -> Case:
    return Case.model_validate(_load_json_payload(row["payload_json"]))


class CaseRepository:
    def insert(self, case: Case) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "cases",
                    ["case_id"],
                    [
                        "case_id",
                        "library_id",
                        "state",
                        "target_product",
                        "target_component",
                        "updated_at",
                        "payload_json",
                    ],
                ),
                (
                    case.case_id,
                    case.library_id,
                    case.state,
                    case.target.product,
                    case.target.component,
                    case.updated_at,
                    _json_param(case.model_dump()),
                ),
            )

    def get(self, case_id: str) -> Case | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        return _row_to_case(row) if row else None

    def list_accessible(
        self,
        library_ids: set[str],
        *,
        state: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Case]:
        clauses: list[str] = []
        params: list[Any] = []
        if library_ids:
            placeholders = ",".join("?" * len(library_ids))
            clauses.append(f"(library_id IS NULL OR library_id IN ({placeholders}))")
            params.extend(library_ids)
        else:
            clauses.append("library_id IS NULL")
        if state:
            clauses.append("state = ?")
            params.append(state)
        where = "WHERE " + " AND ".join(clauses)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM cases {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        return [_row_to_case(row) for row in rows]

    def list_by_ids_accessible(self, case_ids: set[str], library_ids: set[str]) -> list[Case]:
        if not case_ids:
            return []
        id_placeholders = ",".join("?" * len(case_ids))
        params: list[Any] = list(case_ids)
        if library_ids:
            lib_placeholders = ",".join("?" * len(library_ids))
            lib_clause = f"AND (library_id IS NULL OR library_id IN ({lib_placeholders}))"
            params.extend(library_ids)
        else:
            lib_clause = "AND library_id IS NULL"
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM cases WHERE case_id IN ({id_placeholders}) {lib_clause}",
                params,
            ).fetchall()
        return [_row_to_case(row) for row in rows]

    def count(self, library_ids: set[str] | None = None) -> int:
        clause = ""
        params: list[Any] = []
        if library_ids is not None:
            if library_ids:
                placeholders = ",".join("?" * len(library_ids))
                clause = f"WHERE library_id IS NULL OR library_id IN ({placeholders})"
                params.extend(library_ids)
            else:
                clause = "WHERE library_id IS NULL"
        with get_connection() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM cases {clause}", params).fetchone()
        return int(row["count"])


class V2RecordRepository:
    def records_for_cases(self, case_ids: set[str], limit_per_case: int = 10) -> dict[str, list[Record]]:
        if not case_ids:
            return {}
        result: dict[str, list[Record]] = {cid: [] for cid in case_ids}
        # v2 stores case_id inside the record payload for incremental rollout.
        with get_connection() as conn:
            rows = conn.execute("SELECT payload_json FROM records").fetchall()
        for row in rows:
            record = Record.model_validate(_load_json_payload(row["payload_json"]))
            case_id = getattr(record, "case_id", None)
            if not case_id and record.model_extra:
                case_id = record.model_extra.get("case_id")
            if case_id in result and len(result[case_id]) < limit_per_case:
                result[case_id].append(record)
        return result

    def list_accessible_with_case(self, library_ids: set[str]) -> list[Record]:
        if library_ids:
            placeholders = ",".join("?" * len(library_ids))
            sql = f"SELECT payload_json FROM records WHERE library_id IS NULL OR library_id IN ({placeholders})"
            params: list[Any] = list(library_ids)
        else:
            sql = "SELECT payload_json FROM records WHERE library_id IS NULL"
            params = []
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Record.model_validate(_load_json_payload(row["payload_json"])) for row in rows]


class V2GraphRepository:
    def feedback_by_record_ids(self, record_ids: set[str]) -> dict[str, list[Feedback]]:
        if not record_ids:
            return {}
        placeholders = ",".join("?" * len(record_ids))
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT record_id, payload_json FROM feedback WHERE record_id IN ({placeholders})",
                list(record_ids),
            ).fetchall()
        grouped: dict[str, list[Feedback]] = defaultdict(list)
        for row in rows:
            grouped[row["record_id"]].append(Feedback.model_validate(_load_json_payload(row["payload_json"])))
        return dict(grouped)

    def relations_by_record_ids(self, record_ids: set[str]) -> dict[str, list[RecordRelation]]:
        if not record_ids:
            return {}
        placeholders = ",".join("?" * len(record_ids))
        params = list(record_ids) + list(record_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT from_record_id, to_record_id, payload_json
                FROM relations
                WHERE from_record_id IN ({placeholders}) OR to_record_id IN ({placeholders})
                """,
                params,
            ).fetchall()
        grouped: dict[str, list[RecordRelation]] = defaultdict(list)
        for row in rows:
            rel = RecordRelation.model_validate(_load_json_payload(row["payload_json"]))
            grouped[row["from_record_id"]].append(rel)
            grouped[row["to_record_id"]].append(rel)
        return dict(grouped)


class SearchEventRepository:
    def insert_event(self, payload: dict) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "search_events",
                    ["event_id"],
                    [
                        "event_id",
                        "library_id",
                        "created_at",
                        "route",
                        "latency_ms",
                        "result_count",
                        "case_count",
                        "full_scan",
                        "error_type",
                        "query_hash",
                        "payload_json",
                    ],
                ),
                (
                    payload["event_id"],
                    payload.get("library_id"),
                    payload["created_at"],
                    payload["route"],
                    payload.get("latency_ms", 0),
                    payload.get("result_count", 0),
                    payload.get("case_count", 0),
                    bool(payload.get("full_scan", False)) if is_postgres() else int(bool(payload.get("full_scan", False))),
                    payload.get("error_type"),
                    payload.get("query_hash"),
                    _json_param(payload),
                ),
            )

    def insert_feedback(self, payload: dict) -> None:
        with get_connection() as conn:
            conn.execute(
                _upsert(
                    "search_feedback",
                    ["feedback_id"],
                    ["feedback_id", "query_hash", "record_id", "case_id", "judgment", "created_at", "payload_json"],
                ),
                (
                    payload["feedback_id"],
                    payload.get("query_hash"),
                    payload.get("record_id"),
                    payload.get("case_id"),
                    payload["judgment"],
                    payload["created_at"],
                    _json_param(payload),
                ),
            )

    def stats(self) -> dict:
        with get_connection() as conn:
            total = int(conn.execute("SELECT COUNT(*) AS count FROM search_events").fetchone()["count"])
            zero = int(conn.execute("SELECT COUNT(*) AS count FROM search_events WHERE result_count = 0").fetchone()["count"])
            full = int(conn.execute("SELECT COUNT(*) AS count FROM search_events WHERE full_scan = ?", (True if is_postgres() else 1,)).fetchone()["count"])
            feedback = int(conn.execute("SELECT COUNT(*) AS count FROM search_feedback").fetchone()["count"])
        return {"search_events": total, "zero_result_events": zero, "full_scan_events": full, "search_feedback": feedback}
