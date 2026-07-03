from __future__ import annotations

from typing import Any

from app.services.redaction_service import redact_payload, redact_text

_TRUST_FIELDS = (
    "task_type",
    "goal",
    "target",
    "target_product",
    "target_component",
    "environment",
    "versions",
    "tags",
    "applicable_if",
    "not_applicable_if",
    "based_on_record_ids",
    "relation_type",
    "observations",
)


def _parse_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    if isinstance(payload, dict):
        return payload
    return {}


def _trust_projection(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _TRUST_FIELDS:
        if key in payload and payload[key] not in (None, [], {}):
            out[key] = payload[key]
    return out


def format_record_for_read(
    record: dict[str, Any],
    *,
    include_full_json: bool = False,
    relations: dict[str, list[dict[str, Any]]] | None = None,
    redact_on_read: bool = True,
) -> dict[str, Any]:
    source = dict(record)
    row = {k: source[k] for k in ("id", "library_id", "case_id", "status", "problem", "outcome", "result_summary", "created_by", "created_at") if k in source}
    if redact_on_read:
        for key in ("problem", "outcome", "result_summary"):
            if key in row and isinstance(row[key], str):
                row[key] = redact_text(row[key])
    if "feedback" in source:
        row["feedback"] = source["feedback"]
    if source.get("_rank"):
        row["rank"] = source["_rank"]

    payload = _parse_payload(source)
    if redact_on_read and payload:
        payload = redact_payload(payload)
    trust = _trust_projection(payload)
    if trust:
        row["trust"] = trust

    rid = str(source.get("id", ""))
    if relations and rid in relations:
        row["relations"] = relations[rid]

    if include_full_json:
        row["actions"] = payload.get("actions") or []
        row["evidence"] = payload.get("evidence") or []
        if payload.get("observations") and "observations" not in row.get("trust", {}):
            row["observations"] = payload["observations"]

    return row


def format_records_for_read(
    records: list[dict[str, Any]],
    *,
    include_full_json: bool = False,
    relations: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    return [
        format_record_for_read(
            record,
            include_full_json=include_full_json,
            relations=relations,
        )
        for record in records
    ]


def applicability_warnings(
    records: list[dict[str, Any]],
    environment: dict[str, Any] | None,
) -> list[str]:
    if not environment:
        return []
    warnings: list[str] = []
    env_text = " ".join(f"{k}={v}" for k, v in sorted(environment.items()) if v is not None)
    for record in records:
        payload = _parse_payload(record)
        not_if = payload.get("not_applicable_if") or []
        applicable_if = payload.get("applicable_if") or []
        rid = record.get("id", "?")
        for rule in not_if:
            if _rule_matches(rule, env_text):
                warnings.append(f"record {rid} may not apply: not_applicable_if contains {rule!r}")
        if applicable_if and not any(_rule_matches(rule, env_text) for rule in applicable_if):
            warnings.append(f"record {rid} may not apply: applicable_if not satisfied")
    return warnings


def lineage_warnings(records: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for record in records:
        payload = _parse_payload(record)
        rid = record.get("id", "?")
        for ref_id in payload.get("based_on_record_ids") or []:
            from app.storage import db as storage_db

            ref = storage_db.get_record(str(ref_id))
            if ref is None:
                tomb = storage_db.get_record_deletion(str(ref_id))
                if tomb:
                    warnings.append(f"record {rid} builds on {ref_id} which was deleted by owner")
                else:
                    warnings.append(f"record {rid} references missing record {ref_id}")
            elif ref.get("status") == "trashed":
                warnings.append(f"record {rid} builds on {ref_id} which was deleted by owner")
            elif ref.get("status") != "active":
                warnings.append(f"record {rid} builds on {ref_id} which is {ref.get('status')}")
            elif storage_db.relation_source_deleted(source_id=str(rid), target_id=str(ref_id)):
                warnings.append(f"record {rid} builds on {ref_id} which was deleted by owner")
    return warnings


def _rule_matches(rule: str, env_text: str) -> bool:
    rule = str(rule).strip().lower()
    if not rule:
        return False
    return rule.replace(" ", "") in env_text.replace(" ", "").lower() or rule in env_text.lower()
