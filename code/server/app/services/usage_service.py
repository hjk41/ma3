"""Durable read-unit admission counters and buffered usage-event audit rows."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.services import billing_service
from app.storage import db

BILLABLE_READ_TOOLS = {"ma3_context", "ma3_case"}
_buffer: list[dict[str, Any]] = []
_lock = Lock()


def _period(now: datetime | None = None) -> tuple[str, str]:
    value = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.isoformat(), end.isoformat()


def read_units(records_returned: int) -> int:
    return max(1, math.ceil(max(0, int(records_returned)) / 10))


def record_read_usage(billing_account_id: str, *, tool_name: str, records_returned: int, status_code: int = 200) -> int:
    if tool_name not in BILLABLE_READ_TOOLS or not 200 <= int(status_code) < 300:
        return 0
    units = read_units(records_returned)
    period_start, _ = _period()
    with db.connect() as conn:
        sql = """
            INSERT INTO usage_monthly (billing_account_id, period_start, read_units)
            VALUES (?, ?, ?)
            ON CONFLICT(billing_account_id, period_start)
            DO UPDATE SET read_units = usage_monthly.read_units + excluded.read_units
        """
        if db.is_postgres():
            sql = sql.replace("ON CONFLICT(billing_account_id, period_start)", "ON CONFLICT (billing_account_id, period_start)").replace("excluded.read_units", "EXCLUDED.read_units")
        db._execute(conn, sql, (billing_account_id, period_start, units))
    with _lock:
        _buffer.append({"id": db.new_id("ue"), "billing_account_id": billing_account_id, "tool_name": tool_name, "units": units, "records_returned": int(records_returned), "status_code": int(status_code), "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()})
    return units


def monthly_read_units(billing_account_id: str) -> int:
    start, _ = _period()
    with db.connect() as conn:
        row = db._fetchone(conn, "SELECT COALESCE(SUM(read_units), 0) AS units FROM usage_monthly WHERE billing_account_id = ? AND period_start = ?", (billing_account_id, start))
    return int(row["units"]) if row else 0


def read_quota_state(billing_account_id: str) -> dict[str, Any]:
    start, end = _period()
    used = monthly_read_units(billing_account_id)
    limit = billing_service.effective_quota(billing_account_id, "read_units_per_month")
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "warn": bool(limit and used >= limit * 0.8), "exceeded": used >= limit, "period_start": start, "period_end": end}


def flush_usage_events() -> None:
    with _lock:
        events = list(_buffer)
        _buffer.clear()
    with db.connect() as conn:
        for event in events:
            db._execute(conn, "INSERT INTO usage_events (id, billing_account_id, tool_name, units, records_returned, status_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (event["id"], event["billing_account_id"], event["tool_name"], event["units"], event["records_returned"], event["status_code"], event["created_at"]))


def rollup_usage_monthly() -> dict[str, int]:
    flush_usage_events()
    return {"rolled_up": 0}
