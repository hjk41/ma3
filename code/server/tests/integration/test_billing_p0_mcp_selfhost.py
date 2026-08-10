"""P0 MCP surface + self-host parity scenarios (design/27 §8.5, §0.1(6), §10 P0).

Contract encoded here:
- ``ma3_whoami`` gains a ``plan`` block: plan_code, status, seats and
  library/storage quota summaries — extending (not replacing) the shipped
  ``storage_quota`` block (§8.5).
- ``ma3_doctor`` reports ``billing_schema_ok`` (§10 P0 bullet 6).
- Self-host bootstrap (local auth, no Authing, MA3_BILLING_PROVIDER unset →
  none) gets a working default BA with **no Stripe dependency**: no stripe
  SDK import, Stripe webhook route absent (§0.1(6), G7).

whoami ``plan`` block shape asserted (Composer implements this shape):
    {
      "plan_code": "free",
      "status": "active",
      "seats": {"used": 1, "included_seats": 1},
      "libraries": {"used": <int>, "limit": <int>},
      "storage": {...}        # bytes summary, same family as storage_quota
    }
"""
from __future__ import annotations

import sys

import pytest

from tests.helpers.billing_p0 import (
    enable_local_auth,
    personal_org_row,
    register_user,
)
from tests.helpers.mcp_client import McpClient

pytestmark = pytest.mark.billing_p0


@pytest.fixture()
def selfhost_user(isolated_client, monkeypatch):
    enable_local_auth(monkeypatch)
    client = isolated_client
    register_user(client, "mcpprodadmin")  # absorb the product-admin first slot
    user = register_user(client, "mcpbillinguser")
    return {"client": client, "user": user}


# --- BP0-M1: whoami plan block -------------------------------------------------

def test_whoami_returns_plan_and_quota_summary(selfhost_user):
    """§10 P0 bullet 5: ma3_whoami returns plan, seats, library and storage
    quota summary for a DB-key caller."""
    mcp = McpClient(selfhost_user["client"], api_key=selfhost_user["user"]["api_key"])
    structured = mcp.structured("ma3_whoami")

    assert "plan" in structured, (
        "ma3_whoami must gain a `plan` block in P0 (design/27 §8.5); "
        f"got keys: {sorted(structured.keys())}"
    )
    plan = structured["plan"]
    assert plan["plan_code"] == "free"
    assert plan["status"] == "active"

    seats = plan["seats"]
    assert seats["included_seats"] == 1  # personal org stays hard-1 (§6)
    assert seats["used"] == 1

    libraries = plan["libraries"]
    assert int(libraries["limit"]) == 1  # free plan library cap
    assert int(libraries["used"]) >= 1  # personal library provisioned at signup

    assert "storage" in plan

    # The shipped storage_quota block must survive the P0 rewire (§13 hard rule).
    assert "storage_quota" in structured


def test_whoami_plan_reflects_plan_change(selfhost_user):
    """Flipping the BA plan through billing_service is visible in whoami."""
    billing_service = pytest.importorskip(
        "app.services.billing_service",
        reason="P0 not implemented yet: app.services.billing_service (design/27 §2 P0)",
    )
    client = selfhost_user["client"]
    user = selfhost_user["user"]
    personal = personal_org_row(client, user["api_key"])
    ba_id = str(personal.get("billing_account_id") or "")
    assert ba_id.startswith("ba_"), personal
    billing_service.set_billing_account_plan(ba_id, plan_code="pro")

    mcp = McpClient(client, api_key=user["api_key"])
    plan = mcp.structured("ma3_whoami")["plan"]
    assert plan["plan_code"] == "pro"


# --- BP0-M2: doctor billing_schema_ok -------------------------------------------

def test_doctor_reports_billing_schema_ok(isolated_client):
    mcp = McpClient(isolated_client, api_key="ma3dev")
    doctor = mcp.structured("ma3_doctor")
    assert doctor.get("billing_schema_ok") is True, (
        "ma3_doctor must report billing_schema_ok once the P0 tables exist "
        f"(§10 P0 bullet 6); got keys: {sorted(doctor.keys())}"
    )


# --- BP0-M3: self-host bootstrap needs no Stripe ---------------------------------

def test_selfhost_bootstrap_gets_default_ba_without_stripe(selfhost_user):
    """§10 P0 bullet 6 + §0.1(6): provider=none (default) — working default BA,
    no Stripe SDK import, no Stripe routes."""
    client = selfhost_user["client"]
    personal = personal_org_row(client, selfhost_user["user"]["api_key"])
    ba_id = str(personal.get("billing_account_id") or "")
    assert ba_id.startswith("ba_"), (
        "self-host registration bootstrap must create a real default billing "
        f"account; got billing_account_id={ba_id!r}"
    )

    # No Stripe SDK import on the none path (G7 / P2 acceptance guarded early).
    assert "stripe" not in sys.modules

    # Webhook and checkout surfaces do not exist when provider=none.
    webhook = client.post("/webhooks/stripe", json={})
    assert webhook.status_code == 404
