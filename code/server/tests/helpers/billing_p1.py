"""Shared helpers for org+billing P1 acceptance tests (tests-first).

Encodes the public contract Composer implements against
(design/27 `27-org-billing-implementation-fable.md` §0.1 amendments 4+6+7,
§2 P1 table, §6 matrix, §7 UX, §8 API, §9 Decision 7/8, §10 P1, §13):

Expected NEW symbols (P1)
=========================

``app.services.usage_service`` (metering, §2 P1 row 1 + §0.1 amendment 4):
    read_units(records_returned: int) -> int
        # ADR-012 formula: max(1, ceil(records_returned / 10))
    BILLABLE_READ_TOOLS: set[str]            # {"ma3_context", "ma3_case"}
    record_read_usage(billing_account_id, *, tool_name, records_returned,
                      status_code=200) -> int
        # SYNCHRONOUS + DURABLE admission counter (amendment 4): atomically
        # increments usage_monthly for the BA's current period BEFORE the
        # billable response returns. Returns units billed (0 when the tool
        # is not billable or status_code is not 2xx). The async buffered
        # usage_events logger is detail/audit only.
    monthly_read_units(billing_account_id) -> int
        # Current-period counter, read from the same durable counter
        # enforcement uses (observe mode reads the SAME counters).
    read_quota_state(billing_account_id) -> dict
        # {"used", "limit", "remaining", "warn": bool (used >= 80% limit),
        #  "exceeded": bool, "period_start", "period_end"}
    flush_usage_events() -> None             # flush the async detail buffer
    rollup_usage_monthly() -> dict           # idempotent rollup job

``app.services.rate_limit_service`` (§2 P1 last row):
    check_rate_limit(api_key_id: str, *, rpm: int, now=None) -> dict
        # {"allowed": bool, "retry_after": int (seconds, >0 when denied)}
        # in-process sliding window keyed by api_key_id
    reset() -> None                          # clear all windows (test hook)

``app.services.billing_grace_service`` (past_due lifecycle, Decision 8-A):
    GRACE_DAYS = 30
    run_past_due_grace_job(now=None) -> dict
        # {"revoked": [ {billing_account_id, library_id, ...}, ... ],
        #  "notifications": [ {billing_account_id, kind: "T-7"|"T-1"|"T-0",
        #                      ...}, ... ]}
        # Grace clock starts when billing_accounts.status flips to
        # 'past_due' (audit row in billing_events). At T-0 (+30d) revokes
        # RO key grants / RO library grants on PRIVATE/ORG libraries.
        # NEVER escalates RO->RW; NEVER touches Community lib_default;
        # idempotent (second run revokes nothing new); BA back to 'active'
        # before T-0 cancels the revoke.

New tables (created by ``initialize_database``, §3 pattern):
    usage_events   (append-only: billing_account_id, tool_name, units,
                    records_returned, status_code, created_at, ...)
    usage_monthly  (billing_account_id, period_start, read_units, ...;
                    one row per BA per UTC calendar month)

New maintained counters on ``libraries`` (§3.2):
    active_record_count INTEGER, storage_bytes INTEGER
    (backfilled from sum_library_record_content_bytes)

New Settings fields (env-driven, §0.1 amendment 6 self-host defaults):
    settings.read_quota_enforce        MA3_READ_QUOTA_ENFORCE        default False
    settings.rate_limit_enabled        MA3_RATE_LIMIT_ENABLED        default False
    settings.org_storage_quota_enforce MA3_ORG_STORAGE_QUOTA_ENFORCE default False
    settings.billing_provider          MA3_BILLING_PROVIDER          default "none"

Quota keys resolved via ``billing_service.effective_quota`` (P0 shipped):
    "read_units_per_month"  free 10_000 / pro 100_000 / team_stub 50_000 / team 500_000
    "storage_bytes_total"   pooled bytes for org BAs (stub 1 GB / team 10 GB)
    "rpm"                   free 60 / pro 120 / team_stub 120 / team 300

Enforcement semantics (§6 + Decision 7 observe/soft):
    - Over read cap, enforce ON : HTTP 429 on /mcp + ``Retry-After`` header,
      error code "read_quota_exceeded"; writes (ma3_report) still succeed.
    - Over read cap, enforce OFF (default): reads keep succeeding, the same
      counters still fill, warnings still emitted (observe mode).
    - >= 80% of read or storage quota: every MCP data response carries
      ``structuredContent.quota`` with a non-empty ``warnings`` list, e.g.
      {"read_units": {"used", "limit", "remaining"}, "warnings": [ ... ]}.
    - Org pooled storage over cap, enforce ON : 403 "org_storage_quota_exceeded"
      on the write; reads unaffected. Enforce OFF: write succeeds (soft) but
      the response carries a quota warning.
    - past_due (admin-set in P1): ma3_report to owned/org library -> 403
      "billing_past_due"; org invite create -> 403; reads (ma3_context) fine.
    - Rate limiter enabled + window exceeded: HTTP 429 + Retry-After,
      error code "rate_limited".

New routes (§8.2/§8.3):
    GET /api/me/billing               # {"plan_code", "status", "read_units":
                                      #  {"used","limit"}, "storage": {...},
                                      #  "seats": {...}, "keys": {...}, ...}
    GET /api/orgs/{org_id}/billing    # same shape; org ADMIN only, member -> 404
    GET /ui/billing/                  # personal billing page (session)
    GET /ui/orgs/{org_id}/billing/    # org billing page (org admin; member -> 404)
    POST /ui/billing/upgrade          # DOES NOT EXIST in P1 (404) — Checkout is
                                      # P2; SaaS CTA hidden/disabled (Decision 7),
                                      # page shows "coming soon" copy; self-host
                                      # may show admin-contact copy instead.

UI contract markers (kept deliberately minimal):
    - past_due grace banner: element with ``id="past-due-banner"`` on
      /ui/billing/ (and org billing) while status='past_due'.
    - i18n: both zh-CN and en-US catalogs contain the SAME non-empty set of
      ``billing.*`` keys (exact key names are Composer's choice).

Key-creation billing picker (§2 P1 row 2, §8.2):
    POST /api/keys body gains REQUIRED ``billing_org_id`` (personal org id or
    a team org id). Missing -> 400 "billing_context_required". Team org where
    the caller is not an active member -> 403. Sets
    ``api_keys.billing_account_id`` to the chosen org's BA. The registration
    bootstrap key defaults to the owner's personal BA (server-side path).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.ui_i18n import catalog
from app.core.config import settings
from app.storage import db

# Re-exported P0 helpers so P1 tests import from one place.
from tests.helpers.billing_p0 import (  # noqa: F401
    auth_headers,
    create_team_org_via_api,
    enable_local_auth,
    error_code,
    fetch_billing_account_for_org,
    personal_org_row,
    register_user,
)

# --- Locked plan numbers (design/27 §3.1(4) + §9.1) --------------------------

PLAN_READ_UNITS = {"free": 10_000, "pro": 100_000, "team_stub": 50_000, "team": 500_000}
PLAN_RPM = {"free": 60, "pro": 120, "team_stub": 120, "team": 300}

READ_QUOTA_KEY = "read_units_per_month"
STORAGE_POOL_KEY = "storage_bytes_total"
RPM_QUOTA_KEY = "rpm"

BILLABLE_TOOLS = ("ma3_context", "ma3_case")
NON_BILLABLE_TOOLS = ("ma3_report", "ma3_feedback", "ma3_validate")

GRACE_DAYS = 30

_EVIDENCE = [{"kind": "test", "summary": "billing p1 scenario"}]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def require_settings_flag(name: str) -> None:
    """Fail with a clear pre-implementation message when a P1 flag is missing."""
    assert hasattr(settings, name), (
        f"P1 not implemented yet: Settings.{name} "
        "(design/27 §0.1 amendment 6 / §11 P1 rollout flags)"
    )


def personal_ba_id(client, api_key: str) -> str:
    """Personal-org billing account id for a registered user (P0 bootstrap)."""
    personal = personal_org_row(client, api_key)
    ba_id = str(personal.get("billing_account_id") or "")
    assert ba_id.startswith("ba_"), (
        f"P0 bootstrap must link the personal org to a real BA, got {ba_id!r}"
    )
    return ba_id


def org_ba_id(org_id: str) -> str:
    ba = fetch_billing_account_for_org(org_id)
    assert ba is not None, f"no billing account for org {org_id}"
    return str(ba["id"])


# ---------------------------------------------------------------------------
# Raw access to the NEW P1 tables/columns. Deliberately raw SQL: these fail
# loudly ("no such table: usage_monthly") until the P1 migration lands,
# which is the intended pre-implementation signal.
# ---------------------------------------------------------------------------

def monthly_read_units_row(ba_id: str) -> int:
    """Durable sync admission counter for the current UTC calendar month."""
    month = now_utc().strftime("%Y-%m")
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT COALESCE(SUM(read_units), 0) AS units FROM usage_monthly "
            "WHERE billing_account_id = ? AND period_start LIKE ?",
            (ba_id, f"{month}%"),
        )
    return int(row["units"]) if row else 0


def count_usage_events(ba_id: str, *, tool_name: str | None = None) -> int:
    query = "SELECT COUNT(*) AS c FROM usage_events WHERE billing_account_id = ?"
    params: list[Any] = [ba_id]
    if tool_name is not None:
        query += " AND tool_name = ?"
        params.append(tool_name)
    with db.connect() as conn:
        row = db._fetchone(conn, query, tuple(params))
    return int(row["c"]) if row else 0


def sum_usage_event_units(ba_id: str, *, tool_name: str | None = None) -> int:
    query = "SELECT COALESCE(SUM(units), 0) AS u FROM usage_events WHERE billing_account_id = ?"
    params: list[Any] = [ba_id]
    if tool_name is not None:
        query += " AND tool_name = ?"
        params.append(tool_name)
    with db.connect() as conn:
        row = db._fetchone(conn, query, tuple(params))
    return int(row["u"]) if row else 0


def library_counters(library_id: str) -> dict[str, int]:
    """Maintained counters on libraries (§3.2): fails until columns exist."""
    with db.connect() as conn:
        row = db._fetchone(
            conn,
            "SELECT active_record_count, storage_bytes FROM libraries WHERE id = ?",
            (library_id,),
        )
    assert row is not None, f"library not found: {library_id}"
    return {
        "active_record_count": int(row["active_record_count"] or 0),
        "storage_bytes": int(row["storage_bytes"] or 0),
    }


def plan_rpm_rows() -> dict[str, int]:
    """rpm column on plans (fails until the P1 column/seed lands)."""
    with db.connect() as conn:
        rows = db._fetchall(conn, "SELECT code, rpm FROM plans")
    return {str(r["code"]): int(r["rpm"]) for r in rows if r["rpm"] is not None}


# --- Quota knobs (via shipped P0 billing_service) ----------------------------

def set_read_quota(ba_id: str, limit: int) -> None:
    from app.services import billing_service

    billing_service.set_quota_override(ba_id, READ_QUOTA_KEY, limit, reason="p1-test")


def set_storage_pool(ba_id: str, limit_bytes: int) -> None:
    from app.services import billing_service

    billing_service.set_quota_override(ba_id, STORAGE_POOL_KEY, limit_bytes, reason="p1-test")


def set_rpm(ba_id: str, rpm: int) -> None:
    from app.services import billing_service

    billing_service.set_quota_override(ba_id, RPM_QUOTA_KEY, rpm, reason="p1-test")


def set_ba_status(ba_id: str, status: str) -> None:
    from app.services import billing_service

    billing_service.set_billing_account_plan(ba_id, status=status)


# --- MCP payload builders -----------------------------------------------------

def report_payload(problem: str, *, library_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "problem": problem,
        "outcome": "resolved",
        "result_summary": f"{problem} — resolved in billing p1 test",
        "based_on_record_ids": [],
        "evidence": _EVIDENCE,
    }
    if library_id is not None:
        payload["library_id"] = library_id
    return payload


def context_payload(problem: str = "billing p1 read") -> dict[str, Any]:
    return {"problem": problem}


# --- Org library seeding --------------------------------------------------------

def create_org_library_via_api(client, api_key: str, org_id: str, name: str = "P1 Org Lib") -> str:
    response = client.post(
        f"/api/orgs/{org_id}/libraries",
        headers=auth_headers(api_key),
        json={"name": name, "visibility": "org", "confirm_org_visibility": True},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def seed_writer_key(principal_id: str, *library_ids: str) -> str:
    """DB-seeded API key with writer grants (mirrors test_storage_quota)."""
    import secrets

    from app.services.api_key_service import hash_key

    plaintext = f"ma3k_{secrets.token_hex(16)}"
    db.insert_api_key(
        key_id=f"key_{secrets.token_hex(6)}",
        key_hash=hash_key(plaintext),
        principal_id=principal_id,
        label="billing-p1-seeded",
        grants=[{"library_id": lib, "role": "writer"} for lib in library_ids],
    )
    return plaintext


# --- MCP response inspection ----------------------------------------------------

def quota_block(call_result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract structuredContent.quota from a tools/call result (§8.5)."""
    structured = call_result.get("structuredContent") or {}
    quota = structured.get("quota")
    return quota if isinstance(quota, dict) else None


def quota_warnings(call_result: dict[str, Any]) -> list[Any]:
    quota = quota_block(call_result) or {}
    warnings = quota.get("warnings")
    return list(warnings) if isinstance(warnings, list) else []


# --- i18n --------------------------------------------------------------------------

def _flatten_keys(tree: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(tree, dict):
        for name, value in tree.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            if isinstance(value, dict):
                keys |= _flatten_keys(value, path)
            else:
                keys.add(path)
    return keys


def billing_i18n_keys(locale: str) -> set[str]:
    return {k for k in _flatten_keys(catalog(locale)) if k.startswith("billing.")}
