"""Personal library storage quotas: per-record size cap and tiered library capacity."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.services.onboarding_service import is_paid_principal
from app.storage import db

_KNOWN_STORAGE_TIERS = frozenset({"free", "100mb", "10gb", "1tb"})
_QUOTA_STATUSES = ("active", "buffered", "draft")
_MB = 1024 * 1024
_GB = 1024 * _MB
_TB = 1024 * _GB


def parse_principal_storage_tier_env(raw: str) -> dict[str, str]:
    """Parse ``MA3_PRINCIPAL_STORAGE_TIERS`` (``user:id=10gb,user:id2=1tb``)."""
    out: dict[str, str] = {}
    if not raw.strip():
        return out
    for item in raw.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        principal_id, tier = item.split("=", 1)
        principal_id = principal_id.strip()
        tier = tier.strip().lower()
        if not principal_id:
            continue
        if tier not in _KNOWN_STORAGE_TIERS:
            raise ValueError(f"unknown storage tier {tier!r} for {principal_id}; use one of: free, 100mb, 10gb, 1tb")
        out[principal_id] = tier
    return out


def tier_bytes(tier: str) -> int:
    tier = tier.lower()
    if tier == "free":
        return settings.personal_library_quota_bytes_free
    if tier == "100mb":
        return 100 * _MB
    if tier == "10gb":
        return 10 * _GB
    if tier == "1tb":
        return _TB
    raise ValueError(f"unknown storage tier: {tier}")


def resolve_personal_storage_tier(principal_id: str) -> str:
    explicit = settings.principal_storage_tiers.get(principal_id)
    if explicit:
        return explicit
    if is_paid_principal(principal_id):
        return "100mb"
    return "free"


def personal_library_quota_bytes(principal_id: str) -> int:
    return tier_bytes(resolve_personal_storage_tier(principal_id))


def record_content_bytes(
    *,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
) -> int:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        len(problem.encode("utf-8"))
        + len(outcome.encode("utf-8"))
        + len(result_summary.encode("utf-8"))
        + len(payload_json.encode("utf-8"))
    )


def personal_library_subject_to_quota(library_id: str) -> bool:
    if library_id == settings.default_library_id:
        return False
    lib = db.get_library(library_id)
    return bool(lib and lib.get("kind") == "personal")


def format_storage_bytes(value: int) -> str:
    n = max(0, int(value))
    if n >= _TB:
        return f"{n / _TB:.1f} TB"
    if n >= _GB:
        return f"{n / _GB:.1f} GB"
    if n >= _MB:
        return f"{n / _MB:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def personal_library_quota_summary(*, principal_id: str, library_id: str) -> dict[str, Any] | None:
    if not personal_library_subject_to_quota(library_id):
        return None
    lib = db.get_library(library_id)
    if not lib or str(lib.get("owner_principal_id") or "") != principal_id:
        return None
    tier = resolve_personal_storage_tier(principal_id)
    limit_bytes = tier_bytes(tier)
    used_bytes = db.sum_library_record_content_bytes(library_id)
    return {
        "library_id": library_id,
        "tier": tier,
        "limit_bytes": limit_bytes,
        "used_bytes": used_bytes,
        "remaining_bytes": max(0, limit_bytes - used_bytes),
    }


def assert_personal_library_write_allowed(
    *,
    library_id: str,
    principal_id: str,
    problem: str,
    outcome: str,
    result_summary: str,
    payload: dict[str, Any],
    exclude_record_id: str | None = None,
) -> None:
    """Raise HTTPException when a personal-library write would exceed quotas."""
    if not personal_library_subject_to_quota(library_id):
        return

    lib = db.get_library(library_id)
    if not lib:
        return
    owner = str(lib.get("owner_principal_id") or "")
    if owner and owner != principal_id:
        return

    new_bytes = record_content_bytes(
        problem=problem,
        outcome=outcome,
        result_summary=result_summary,
        payload=payload,
    )
    max_record = settings.max_record_bytes
    if new_bytes > max_record:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "record_too_large",
                "message": (
                    f"record content is {new_bytes} bytes; personal library records are limited to "
                    f"{max_record} bytes ({max_record // 1024}KB). Shorten problem, result_summary, "
                    "evidence, or actions and retry."
                ),
                "bytes": new_bytes,
                "limit_bytes": max_record,
            },
        )

    tier = resolve_personal_storage_tier(principal_id)
    limit_bytes = tier_bytes(tier)
    used_bytes = db.sum_library_record_content_bytes(library_id, exclude_record_id=exclude_record_id)
    projected = used_bytes + new_bytes
    if projected <= limit_bytes:
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": "personal_library_storage_quota_exceeded",
            "message": (
                f"personal library storage quota exceeded ({tier} tier: {limit_bytes} bytes; "
                f"used {used_bytes}, need {new_bytes} more). Delete old records or upgrade storage tier."
            ),
            "tier": tier,
            "used_bytes": used_bytes,
            "limit_bytes": limit_bytes,
            "incoming_bytes": new_bytes,
            "library_id": library_id,
        },
    )
