"""P1 usage metering unit scenarios (design/27 §2 P1 row 1, §0.1(4), §13).

Contract under test: app.services.usage_service — unit formula
max(1, ceil(records_returned/10)); only ma3_context/ma3_case with 2xx are
billable (report/feedback/validate = 0 units); the monthly admission counter
is SYNCHRONOUS and durable (amendment 4), separate from the buffered
usage_events detail logger; rollup is idempotent.

SKIPS until Composer lands `app.services.usage_service`; then must pass.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.onboarding_service import ensure_personal_org, personal_org_id
from app.storage import db
from app.storage.db import initialize_database
from tests.helpers.billing_p1 import (
    BILLABLE_TOOLS,
    NON_BILLABLE_TOOLS,
    count_usage_events,
    fetch_billing_account_for_org,
    monthly_read_units_row,
    sum_usage_event_units,
)

usage_service = pytest.importorskip(
    "app.services.usage_service",
    reason="P1 not implemented yet: app.services.usage_service (design/27 §2 P1)",
)

pytestmark = pytest.mark.billing_p1


@pytest.fixture(autouse=True)
def metering_db(tmp_path, monkeypatch):
    db_path = tmp_path / "billing-p1-metering.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    initialize_database()


@pytest.fixture()
def ba_id() -> str:
    pid = "user:p1-metering"
    db.upsert_user_principal(sso_user="p1-metering", display_name="p1-metering")
    ensure_personal_org(pid, "p1-metering")
    ba = fetch_billing_account_for_org(personal_org_id(pid))
    return str(ba["id"])


# --- BP1-U1: unit formula max(1, ceil(n/10)) ---------------------------------

@pytest.mark.parametrize(
    ("records_returned", "expected_units"),
    [
        (0, 1),    # empty result still costs 1 (max(1, ...))
        (1, 1),
        (10, 1),
        (11, 2),
        (25, 3),
        (100, 10),
        (101, 11),
    ],
)
def test_read_unit_formula(records_returned, expected_units):
    """ADR-012 / §2 P1: units = max(1, ceil(records_returned/10))."""
    assert usage_service.read_units(records_returned) == expected_units


# --- BP1-U2: only ma3_context / ma3_case are billable -------------------------

@pytest.mark.parametrize("tool_name", BILLABLE_TOOLS)
def test_billable_tools_charge_at_least_one_unit(ba_id, tool_name):
    units = usage_service.record_read_usage(
        ba_id, tool_name=tool_name, records_returned=3, status_code=200
    )
    assert units == 1
    assert usage_service.monthly_read_units(ba_id) == 1


@pytest.mark.parametrize("tool_name", NON_BILLABLE_TOOLS)
def test_write_tools_are_never_billable(ba_id, tool_name):
    """§10 P1 bullet 1: report/feedback/validate produce ZERO billable units."""
    units = usage_service.record_read_usage(
        ba_id, tool_name=tool_name, records_returned=5, status_code=200
    )
    assert units == 0
    assert usage_service.monthly_read_units(ba_id) == 0


# --- BP1-U3: non-2xx responses are not counted ---------------------------------

@pytest.mark.parametrize("status_code", [400, 404, 429, 500])
def test_non_2xx_not_billable(ba_id, status_code):
    units = usage_service.record_read_usage(
        ba_id, tool_name="ma3_context", records_returned=5, status_code=status_code
    )
    assert units == 0
    assert usage_service.monthly_read_units(ba_id) == 0


# --- BP1-U4: admission counter is synchronous + durable (§0.1(4)) --------------

def test_sync_counter_visible_without_flush(ba_id):
    """The monthly counter must be readable immediately after the call —
    it is the admission primitive, NOT the async buffer."""
    for i in range(4):
        usage_service.record_read_usage(
            ba_id, tool_name="ma3_context", records_returned=1, status_code=200
        )
        assert usage_service.monthly_read_units(ba_id) == i + 1
    # Durable: visible via raw SQL on usage_monthly, not just in memory.
    assert monthly_read_units_row(ba_id) == 4


def test_observe_mode_uses_the_same_counters(ba_id, monkeypatch):
    """§0.1(4): observe-only mode reads the same counters enforcement will use."""
    if hasattr(settings, "read_quota_enforce"):
        monkeypatch.setattr(settings, "read_quota_enforce", False)
    usage_service.record_read_usage(
        ba_id, tool_name="ma3_case", records_returned=12, status_code=200
    )
    assert usage_service.monthly_read_units(ba_id) == 2  # ceil(12/10)
    assert monthly_read_units_row(ba_id) == 2


# --- BP1-U5: async detail buffer flushes to usage_events ------------------------

def test_usage_events_buffer_flush(ba_id):
    usage_service.record_read_usage(
        ba_id, tool_name="ma3_context", records_returned=15, status_code=200
    )
    usage_service.record_read_usage(
        ba_id, tool_name="ma3_case", records_returned=1, status_code=200
    )
    usage_service.flush_usage_events()
    assert count_usage_events(ba_id, tool_name="ma3_context") == 1
    assert count_usage_events(ba_id, tool_name="ma3_case") == 1
    assert sum_usage_event_units(ba_id) == 3  # 2 + 1


# --- BP1-U6: rollup idempotency --------------------------------------------------

def test_rollup_is_idempotent(ba_id):
    """§13 test plan: rollup twice → identical usage_monthly state."""
    for _ in range(3):
        usage_service.record_read_usage(
            ba_id, tool_name="ma3_context", records_returned=1, status_code=200
        )
    usage_service.flush_usage_events()
    usage_service.rollup_usage_monthly()
    first = monthly_read_units_row(ba_id)
    usage_service.rollup_usage_monthly()
    assert monthly_read_units_row(ba_id) == first == 3


# --- BP1-U7: read_quota_state warn/exceeded thresholds ----------------------------

def test_read_quota_state_thresholds(ba_id):
    """§6 warnings row: warn at >=80%, exceeded at cap."""
    from app.services import billing_service

    billing_service.set_quota_override(ba_id, "read_units_per_month", 10, reason="p1-unit")

    for _ in range(7):
        usage_service.record_read_usage(
            ba_id, tool_name="ma3_context", records_returned=1, status_code=200
        )
    state = usage_service.read_quota_state(ba_id)
    assert state["used"] == 7
    assert state["limit"] == 10
    assert state["warn"] is False
    assert state["exceeded"] is False

    usage_service.record_read_usage(
        ba_id, tool_name="ma3_context", records_returned=1, status_code=200
    )
    state = usage_service.read_quota_state(ba_id)
    assert state["used"] == 8
    assert state["warn"] is True, "80% of quota must set warn (§6 warnings)"
    assert state["exceeded"] is False

    for _ in range(2):
        usage_service.record_read_usage(
            ba_id, tool_name="ma3_context", records_returned=1, status_code=200
        )
    state = usage_service.read_quota_state(ba_id)
    assert state["used"] == 10
    assert state["exceeded"] is True
    assert state["remaining"] == 0
