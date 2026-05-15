from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models.feedback import Feedback
from datetime import datetime, timezone, timedelta
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
        fetch_limit: int | None = None,
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
        effective_limit = fetch_limit if fetch_limit is not None else limit
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM cases {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                params + [effective_limit, offset],
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


def _norm_topic(value: str | None) -> str:
    return (value or "").strip().lower()

def _case_matches_topic(case: Case, records: list[Record], topic_kind: str, topic: str) -> bool:
    wanted = _norm_topic(topic)
    if not wanted:
        return True

    def component_value(product: str | None, component: str | None) -> str:
        return f"{product or ''}/{component or ''}"

    candidates: list[str] = []
    if topic_kind == "product":
        candidates.append(case.target.product)
        candidates.extend(record.target.product for record in records)
    elif topic_kind == "component":
        candidates.append(component_value(case.target.product, case.target.component))
        candidates.append(case.target.component or "")
        for record in records:
            candidates.append(component_value(record.target.product, record.target.component))
            candidates.append(record.target.component or "")
    elif topic_kind == "tag":
        candidates.extend(case.tags)
        for record in records:
            candidates.extend(record.tags)
    elif topic_kind == "problem_family":
        candidates.append(case.problem_family)
        candidates.extend(record.problem_family for record in records)
    else:
        return True
    return any(_norm_topic(candidate) == wanted for candidate in candidates)

def filter_cases_by_topic(
    cases: list[Case],
    *,
    topic_kind: str | None,
    topic: str | None,
    offset: int,
    limit: int,
) -> list[Case]:
    if not topic_kind or not topic:
        return cases[offset: offset + limit]
    allowed = {"product", "component", "tag", "problem_family"}
    if topic_kind not in allowed:
        return cases[offset: offset + limit]
    records_by_case = V2RecordRepository().records_for_cases({case.case_id for case in cases}, limit_per_case=1000)
    matched = [
        case for case in cases
        if _case_matches_topic(case, records_by_case.get(case.case_id, []), topic_kind, topic)
    ]
    return matched[offset: offset + limit]


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
            rows = conn.execute(
                "SELECT created_at, route, latency_ms, result_count, full_scan FROM search_events ORDER BY created_at ASC"
            ).fetchall()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        buckets: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            try:
                dt = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if dt < cutoff:
                continue
            hour = dt.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
            key = (hour, row["route"])
            buckets.setdefault(key, []).append({
                "latency_ms": float(row["latency_ms"] or 0),
                "result_count": int(row["result_count"] or 0),
                "full_scan": bool(row["full_scan"]),
            })

        def pct(values: list[float], percentile: float) -> float:
            if not values:
                return 0.0
            ordered = sorted(values)
            idx = round((len(ordered) - 1) * percentile)
            return ordered[idx]

        by_hour = []
        for (hour, route), items in sorted(buckets.items()):
            latencies = [item["latency_ms"] for item in items]
            by_hour.append({
                "hour": hour,
                "route": route,
                "count": len(items),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
                "p50_latency_ms": round(pct(latencies, 0.50), 3),
                "p95_latency_ms": round(pct(latencies, 0.95), 3),
                "max_latency_ms": round(max(latencies), 3) if latencies else 0.0,
                "zero_results": sum(1 for item in items if item["result_count"] == 0),
                "full_scan": sum(1 for item in items if item["full_scan"]),
            })

        return {
            "search_events": total,
            "zero_result_events": zero,
            "full_scan_events": full,
            "search_feedback": feedback,
            "window_hours": 48,
            "by_hour": by_hour,
        }
