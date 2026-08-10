"""P1 rate limiter unit scenarios (design/27 §2 P1 last row, §6 rpm row, §13).

Contract under test: app.services.rate_limit_service — NEW in-process
sliding-window limiter keyed by api_key_id (no limiter exists pre-P1; the
metrics middleware already counts 429s). Per-plan rpm 60/120/300 (stub 120,
§9.1). Denials carry a positive retry_after (seconds). Disabled by default
(MA3_RATE_LIMIT_ENABLED=0, §0.1 amendment 6).

SKIPS until Composer lands `app.services.rate_limit_service`; then must pass.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.storage.db import initialize_database
from tests.helpers.billing_p1 import PLAN_RPM, plan_rpm_rows

rate_limit_service = pytest.importorskip(
    "app.services.rate_limit_service",
    reason="P1 not implemented yet: app.services.rate_limit_service (design/27 §2 P1)",
)

pytestmark = pytest.mark.billing_p1


@pytest.fixture(autouse=True)
def fresh_limiter():
    rate_limit_service.reset()
    yield
    rate_limit_service.reset()


# --- BP1-R1: per-key sliding window -------------------------------------------

def test_window_allows_rpm_then_denies_with_retry_after():
    key = "key_p1_rl_a"
    for i in range(3):
        result = rate_limit_service.check_rate_limit(key, rpm=3)
        assert result["allowed"] is True, f"request {i + 1} of rpm=3 must pass"
    denied = rate_limit_service.check_rate_limit(key, rpm=3)
    assert denied["allowed"] is False
    assert int(denied["retry_after"]) > 0, (
        "denials must carry Retry-After seconds (§2 P1 rate-limit row)"
    )
    assert int(denied["retry_after"]) <= 60, "sliding 60s window: retry within the window"


# --- BP1-R2: keys are independent ----------------------------------------------

def test_windows_are_keyed_per_api_key():
    for _ in range(3):
        assert rate_limit_service.check_rate_limit("key_p1_rl_b", rpm=3)["allowed"]
    assert rate_limit_service.check_rate_limit("key_p1_rl_b", rpm=3)["allowed"] is False
    # A different key is unaffected.
    assert rate_limit_service.check_rate_limit("key_p1_rl_c", rpm=3)["allowed"] is True


# --- BP1-R3: window slides ---------------------------------------------------------

def test_window_slides_after_a_minute():
    """check_rate_limit accepts an injectable `now` so the window is testable."""
    key = "key_p1_rl_d"
    start = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    for _ in range(2):
        assert rate_limit_service.check_rate_limit(key, rpm=2, now=start)["allowed"]
    assert rate_limit_service.check_rate_limit(key, rpm=2, now=start)["allowed"] is False
    later = start + timedelta(seconds=61)
    assert rate_limit_service.check_rate_limit(key, rpm=2, now=later)["allowed"] is True, (
        "events older than 60s must fall out of the sliding window"
    )


# --- BP1-R4: per-plan rpm seed (60/120/300; stub 120) ----------------------------

def test_plans_seed_rpm_column(tmp_path, monkeypatch):
    db_path = tmp_path / "billing-p1-rpm.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    initialize_database()
    rpm = plan_rpm_rows()
    assert {code: rpm.get(code) for code in PLAN_RPM} == PLAN_RPM, (
        "plans.rpm must be seeded free=60 pro=120 team_stub=120 team=300 "
        "(design/27 §3.1(4) + §9.1)"
    )


# --- BP1-R5: disabled by default (self-host safe) ----------------------------------

def test_rate_limit_flag_defaults_off(monkeypatch):
    """§0.1(6): MA3_RATE_LIMIT_ENABLED defaults to 0 — private deployments
    never inherit SaaS caps by default."""
    from app.core.config import Settings

    monkeypatch.delenv("MA3_RATE_LIMIT_ENABLED", raising=False)
    fresh = Settings()
    assert hasattr(fresh, "rate_limit_enabled"), (
        "P1 not implemented yet: Settings.rate_limit_enabled (design/27 §11 P1)"
    )
    assert fresh.rate_limit_enabled is False
