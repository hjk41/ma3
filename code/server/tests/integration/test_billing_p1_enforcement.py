"""P1 end-to-end enforcement scenarios — the §6 matrix (design/27 §2 P1,
§6, §0.1 amendments 4+6+7, §9 Decision 7, §10 P1 acceptance, §13
`test_billing_enforcement.py`).

Contract encoded here (see tests/helpers/billing_p1.py docstring):
- Metering: 10 successful ma3_context calls → usage_monthly.read_units == 10
  for the key's BA; write tools bill 0; failed reads bill 0 (2xx only).
- Observe default (MA3_READ_QUOTA_ENFORCE=0): over-cap reads keep working,
  the same counters fill, warnings still emitted (Decision 7 / §0.1(4)(6)).
- Enforce ON: over cap → HTTP 429 on /mcp with Retry-After; writes
  (ma3_report) still succeed (contribution-first, §10 P1 bullet 2).
- ≥80% of read quota → structuredContent.quota.warnings on data responses.
- Team pooled storage (bytes) on org libraries: soft-warn when
  MA3_ORG_STORAGE_QUOTA_ENFORCE=0 (Decision 7), 403 org_storage_quota_exceeded
  when 1; reads unaffected; libraries.storage_bytes counter matches
  sum_library_record_content_bytes.
- past_due: ma3_report 403 billing_past_due, org invite 403, reads fine.
- Rate limiter (MA3_RATE_LIMIT_ENABLED=1): over rpm → HTTP 429 + Retry-After.
- Self-host defaults: provider=none → both enforce flags default OFF.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.storage import db
from tests.helpers.billing_p1 import (
    READ_QUOTA_KEY,
    auth_headers,
    context_payload,
    create_org_library_via_api,
    create_team_org_via_api,
    enable_local_auth,
    library_counters,
    monthly_read_units_row,
    org_ba_id,
    personal_ba_id,
    quota_warnings,
    register_user,
    report_payload,
    require_settings_flag,
    seed_writer_key,
    set_ba_status,
    set_read_quota,
    set_rpm,
    set_storage_pool,
)
from tests.helpers.mcp_client import McpClient

usage_service = pytest.importorskip(
    "app.services.usage_service",
    reason="P1 not implemented yet: app.services.usage_service (design/27 §2 P1)",
)

pytestmark = pytest.mark.billing_p1


@pytest.fixture()
def metered_user(isolated_client, monkeypatch):
    """Local-auth user whose registration key is billed to the personal BA
    (P0 backfill: api_keys.billing_account_id → owner personal BA)."""
    enable_local_auth(monkeypatch)
    client = isolated_client
    register_user(client, "p1prodadmin")  # absorb the product-admin first slot
    user = register_user(client, "p1meteruser")
    ba_id = personal_ba_id(client, user["api_key"])
    mcp = McpClient(client, api_key=user["api_key"])
    return {"client": client, "user": user, "ba_id": ba_id, "mcp": mcp}


def _mcp_error_code(err: dict) -> str | None:
    detail = ((err.get("data") or {}).get("detail")) or {}
    return detail.get("error") if isinstance(detail, dict) else None


def _raw_mcp_post(client, api_key: str, name: str, arguments: dict, rid: int = 999):
    """Raw POST /mcp so HTTP status + headers (Retry-After) are observable."""
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers={"X-API-Key": api_key},
    )


# --- BP1-E1: reads bill, writes do not (§10 P1 bullet 1) ------------------------

def test_ten_context_calls_bill_ten_units(metered_user):
    env = metered_user
    for i in range(10):
        env["mcp"].structured("ma3_context", context_payload(f"p1 read {i}"))
    assert monthly_read_units_row(env["ba_id"]) == 10, (
        "10 successful ma3_context calls (≤10 records each) must bill exactly "
        "10 read units to the key's BA (§10 P1 bullet 1)"
    )


def test_write_tools_bill_zero_units(metered_user):
    env = metered_user
    baseline = monthly_read_units_row(env["ba_id"])

    report = env["mcp"].structured("ma3_report", report_payload("p1 zero-unit write"))
    assert report["record_id"]

    validate = env["mcp"].structured(
        "ma3_validate",
        {"tool_name": "ma3_report", "arguments": report_payload("p1 validate probe")},
    )
    assert validate is not None

    env["mcp"].structured("ma3_feedback", {"record_id": report["record_id"], "vote": "up"})

    assert monthly_read_units_row(env["ba_id"]) == baseline, (
        "ma3_report / ma3_validate / ma3_feedback must produce ZERO billable units"
    )


def test_failed_reads_bill_zero_units(metered_user):
    """Only 2xx responses are billable — an errored ma3_case charges nothing."""
    env = metered_user
    baseline = monthly_read_units_row(env["ba_id"])
    env["mcp"].call("ma3_case", {"case_id": "cs_does_not_exist_p1"}, expect_error=True)
    assert monthly_read_units_row(env["ba_id"]) == baseline


def test_ma3_case_success_bills_by_formula(metered_user):
    env = metered_user
    report = env["mcp"].structured("ma3_report", report_payload("p1 case source"))
    baseline = monthly_read_units_row(env["ba_id"])
    env["mcp"].structured("ma3_case", {"case_id": report["case_id"]})
    assert monthly_read_units_row(env["ba_id"]) == baseline + 1  # ≤10 records → 1 unit


# --- BP1-E2: observe default — no 429, same counters (Decision 7) ----------------

def test_observe_mode_never_429s_but_counts(metered_user):
    env = metered_user
    require_settings_flag("read_quota_enforce")
    assert settings.read_quota_enforce is False, (
        "MA3_READ_QUOTA_ENFORCE must default to 0 (observe) — §0.1(6)/§11"
    )
    set_read_quota(env["ba_id"], 3)
    for i in range(5):
        response = _raw_mcp_post(
            env["client"], env["user"]["api_key"], "ma3_context",
            context_payload(f"observe read {i}"), rid=100 + i,
        )
        assert response.status_code == 200, (
            f"observe mode must never 429 (read {i + 1}/5): {response.status_code}"
        )
    assert monthly_read_units_row(env["ba_id"]) == 5, (
        "observe mode must fill the SAME durable counters enforcement uses (§0.1(4))"
    )


# --- BP1-E3: enforce ON — 429 + Retry-After; writes unaffected --------------------

def test_enforce_on_over_cap_429_with_retry_after(metered_user, monkeypatch):
    env = metered_user
    require_settings_flag("read_quota_enforce")
    monkeypatch.setattr(settings, "read_quota_enforce", True)
    set_read_quota(env["ba_id"], 2)

    for i in range(2):
        ok = _raw_mcp_post(
            env["client"], env["user"]["api_key"], "ma3_context",
            context_payload(f"enforce read {i}"), rid=200 + i,
        )
        assert ok.status_code == 200, ok.text

    blocked = _raw_mcp_post(
        env["client"], env["user"]["api_key"], "ma3_context",
        context_payload("enforce read over cap"), rid=210,
    )
    assert blocked.status_code == 429, (
        f"over monthly read cap with enforce=1 must be HTTP 429, got {blocked.status_code}"
    )
    assert blocked.headers.get("Retry-After"), "429 must carry a Retry-After header (§2 P1)"
    assert "read_quota_exceeded" in blocked.text

    # Writes still succeed at the read cap (contribution-first, §10 P1 bullet 2).
    report = env["mcp"].structured("ma3_report", report_payload("write past read cap"))
    assert report["record_id"]


# --- BP1-E4: 80% warnings via structuredContent.quota ------------------------------

def test_quota_warnings_at_80_percent(metered_user):
    env = metered_user
    set_read_quota(env["ba_id"], 10)
    for i in range(7):
        env["mcp"].structured("ma3_context", context_payload(f"warn ramp {i}"))

    result = env["mcp"].call("ma3_context", context_payload("crosses 80%"))
    assert quota_warnings(result), (
        "at ≥80% of the monthly read quota every MCP data response must carry "
        "structuredContent.quota.warnings (§6 warnings row, §10 P1 bullet 3); "
        f"structuredContent keys: {sorted((result.get('structuredContent') or {}).keys())}"
    )


# --- BP1-E5/E6: team pooled storage (bytes) on org libraries -----------------------

@pytest.fixture()
def org_storage_env(isolated_client, monkeypatch):
    enable_local_auth(monkeypatch)
    monkeypatch.setattr(settings, "max_record_bytes", 102400)
    client = isolated_client
    register_user(client, "p1storadmin")
    creator = register_user(client, "p1storcreator")
    monkeypatch.setattr(settings, "paid_principal_ids", (creator["principal_id"],))
    org_id = create_team_org_via_api(client, creator["api_key"], name="P1 Storage Team")
    lib_id = create_org_library_via_api(client, creator["api_key"], org_id, name="P1 Pool Lib")
    key = seed_writer_key(creator["principal_id"], lib_id)
    return {
        "client": client,
        "creator": creator,
        "org_id": org_id,
        "lib_id": lib_id,
        "ba_id": org_ba_id(org_id),
        "mcp": McpClient(client, api_key=key),
    }


def _big_report(lib_id: str, tag: str) -> dict:
    payload = report_payload(f"pooled storage {tag}", library_id=lib_id)
    payload["evidence"] = [{"kind": "test", "summary": "y" * 400}]
    return payload


def test_pooled_storage_soft_when_enforce_off(org_storage_env):
    """Decision 7: stub/team storage caps stay observe/soft on SaaS until
    Checkout — over-pool write succeeds but carries a quota warning."""
    env = org_storage_env
    require_settings_flag("org_storage_quota_enforce")
    assert settings.org_storage_quota_enforce is False, (
        "MA3_ORG_STORAGE_QUOTA_ENFORCE must default to 0 (soft) — Decision 7"
    )
    set_storage_pool(env["ba_id"], 300)
    result = env["mcp"].call("ma3_report", _big_report(env["lib_id"], "soft overflow"))
    assert "error" not in result or result.get("result"), result
    assert quota_warnings(result), (
        "soft mode: over-pool org write must succeed WITH a quota warning (Decision 7)"
    )


def test_pooled_storage_403_when_enforce_on(org_storage_env, monkeypatch):
    env = org_storage_env
    require_settings_flag("org_storage_quota_enforce")

    first = env["mcp"].structured("ma3_report", report_payload("fits in pool", library_id=env["lib_id"]))
    assert first["record_id"]

    monkeypatch.setattr(settings, "org_storage_quota_enforce", True)
    set_storage_pool(env["ba_id"], 300)
    err = env["mcp"].call("ma3_report", _big_report(env["lib_id"], "hard overflow"), expect_error=True)
    assert _mcp_error_code(err) == "org_storage_quota_exceeded" or (
        "org_storage_quota_exceeded" in str(err)
    ), err

    # Reads on the same library are unaffected (§6 storage row).
    case = env["mcp"].structured("ma3_case", {"case_id": first["case_id"]})
    assert case["records"]


def test_library_storage_counter_matches_source_of_truth(org_storage_env):
    """§3.2 + §10 P1 bullet 4: libraries.storage_bytes / active_record_count
    maintained counters match sum_library_record_content_bytes."""
    env = org_storage_env
    for i in range(2):
        env["mcp"].structured(
            "ma3_report", report_payload(f"counter write {i}", library_id=env["lib_id"])
        )
    counters = library_counters(env["lib_id"])
    assert counters["active_record_count"] == 2
    assert counters["storage_bytes"] == db.sum_library_record_content_bytes(env["lib_id"]), (
        "maintained storage_bytes counter must equal the byte-sum source of truth"
    )
    assert counters["storage_bytes"] > 0


# --- BP1-E7: past_due — writes/invites blocked, reads fine -------------------------

def test_past_due_blocks_writes_keeps_reads(metered_user):
    env = metered_user
    set_ba_status(env["ba_id"], "past_due")

    err = env["mcp"].call("ma3_report", report_payload("past due write"), expect_error=True)
    assert _mcp_error_code(err) == "billing_past_due" or "billing_past_due" in str(err), (
        f"past_due BA: ma3_report to an owned library must fail billing_past_due, got {err}"
    )

    ctx = env["mcp"].structured("ma3_context", context_payload("past due read"))
    assert ctx is not None, "past_due: reads always keep working (§5/§10 P1 bullet 5)"


def test_past_due_org_blocks_invites(isolated_client, monkeypatch):
    enable_local_auth(monkeypatch)
    client = isolated_client
    register_user(client, "p1pdadmin")
    creator = register_user(client, "p1pdcreator")
    monkeypatch.setattr(settings, "paid_principal_ids", (creator["principal_id"],))
    org_id = create_team_org_via_api(client, creator["api_key"], name="P1 PastDue Team")
    set_ba_status(org_ba_id(org_id), "past_due")

    response = client.post(
        f"/api/orgs/{org_id}/invites",
        headers=auth_headers(creator["api_key"]),
        json={"role": "member", "max_uses": 1},
    )
    assert response.status_code == 403, (
        f"past_due org BA must block invite creation (§6 seats row): "
        f"{response.status_code} {response.text}"
    )
    assert "billing_past_due" in response.text


# --- BP1-E8: rate limiter on /mcp (flag-gated) --------------------------------------

def test_rate_limiter_429_when_enabled(metered_user, monkeypatch):
    pytest.importorskip(
        "app.services.rate_limit_service",
        reason="P1 not implemented yet: app.services.rate_limit_service",
    )
    env = metered_user
    require_settings_flag("rate_limit_enabled")
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    set_rpm(env["ba_id"], 3)

    statuses = []
    last = None
    for i in range(4):
        last = _raw_mcp_post(
            env["client"], env["user"]["api_key"], "ma3_context",
            context_payload(f"rpm probe {i}"), rid=300 + i,
        )
        statuses.append(last.status_code)
    assert statuses[:3] == [200, 200, 200], statuses
    assert statuses[3] == 429, f"4th request within the minute must be 429, got {statuses}"
    assert last.headers.get("Retry-After"), "rate-limit 429 must carry Retry-After (§2 P1)"
    assert "rate_limited" in last.text


def test_rate_limiter_off_by_default(metered_user):
    env = metered_user
    require_settings_flag("rate_limit_enabled")
    assert settings.rate_limit_enabled is False
    set_rpm(env["ba_id"], 1)
    for i in range(3):
        response = _raw_mcp_post(
            env["client"], env["user"]["api_key"], "ma3_context",
            context_payload(f"no-limit probe {i}"), rid=400 + i,
        )
        assert response.status_code == 200, (
            "with MA3_RATE_LIMIT_ENABLED=0 (default) the limiter must be inert"
        )


# --- BP1-E9: self-host defaults (§0.1 amendment 6) -----------------------------------

def test_selfhost_provider_none_defaults_all_enforcement_off(monkeypatch):
    """provider=none (default): read-quota enforcement, org-storage enforcement
    and the rate limiter all default OFF. SaaS compose enables them explicitly."""
    from app.core.config import Settings

    for env_name in (
        "MA3_BILLING_PROVIDER",
        "MA3_READ_QUOTA_ENFORCE",
        "MA3_RATE_LIMIT_ENABLED",
        "MA3_ORG_STORAGE_QUOTA_ENFORCE",
    ):
        monkeypatch.delenv(env_name, raising=False)
    fresh = Settings()
    for attr in ("billing_provider", "read_quota_enforce", "rate_limit_enabled",
                 "org_storage_quota_enforce"):
        assert hasattr(fresh, attr), (
            f"P1 not implemented yet: Settings.{attr} (design/27 §0.1(6))"
        )
    assert fresh.billing_provider == "none"
    assert fresh.read_quota_enforce is False
    assert fresh.rate_limit_enabled is False
    assert fresh.org_storage_quota_enforce is False
