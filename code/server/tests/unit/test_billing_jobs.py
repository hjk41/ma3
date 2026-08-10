"""Billing maintenance job wiring (D9)."""
from __future__ import annotations

from app.services import usage_service
from app.services.billing_jobs import run_billing_maintenance_once
from app.storage import db
from app.storage.db import initialize_database


def test_billing_maintenance_flushes_usage_events(tmp_path, monkeypatch):
    db_path = tmp_path / "billing-jobs.db"
    monkeypatch.setenv("MA3_DATABASE_URL", f"sqlite:///{db_path}")
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    initialize_database()

    from app.services.onboarding_service import ensure_personal_org, personal_org_id
    from app.services import billing_service

    pid = "user:billing-jobs"
    db.upsert_user_principal(sso_user="billing-jobs", display_name="billing-jobs")
    ensure_personal_org(pid, "billing-jobs")
    ba = billing_service.get_billing_account_for_org(personal_org_id(pid))
    assert ba is not None
    usage_service.record_read_usage(
        str(ba["id"]), tool_name="ma3_context", records_returned=1, status_code=200
    )
    with db.connect() as conn:
        before = db._fetchone(conn, "SELECT COUNT(*) AS c FROM usage_events")
    assert int(before["c"]) == 0

    result = run_billing_maintenance_once()
    assert result["flushed"] is True
    with db.connect() as conn:
        after = db._fetchone(conn, "SELECT COUNT(*) AS c FROM usage_events")
    assert int(after["c"]) == 1
