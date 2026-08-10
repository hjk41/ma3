"""Past-due grace notifications and private/org read-grant revocation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.storage import db

GRACE_DAYS = 30


def _as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def run_past_due_grace_job(now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    revoked: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []
    with db.connect() as conn:
        accounts = db._fetchall(conn, "SELECT * FROM billing_accounts WHERE status = 'past_due'")
        for account in accounts:
            ba_id = str(account["id"])
            event = db._fetchone(conn, "SELECT created_at FROM billing_events WHERE billing_account_id = ? AND type = 'admin_plan_change' ORDER BY created_at DESC LIMIT 1", (ba_id,))
            started = _as_utc(str(event["created_at"])) if event else _as_utc(str(account["created_at"]))
            days = (current.date() - started.date()).days
            for offset, kind in ((GRACE_DAYS - 7, "T-7"), (GRACE_DAYS - 1, "T-1"), (GRACE_DAYS, "T-0")):
                if days != offset:
                    continue
                marker = current.date().isoformat()
                try:
                    db._execute(conn, "INSERT INTO billing_grace_notifications (billing_account_id, kind, grace_day, created_at) VALUES (?, ?, ?, ?)", (ba_id, kind, marker, current.replace(microsecond=0).isoformat()))
                except Exception:
                    continue
                notifications.append({"billing_account_id": ba_id, "kind": kind})
            if days < GRACE_DAYS:
                continue
            libraries = db._fetchall(
                conn,
                """
                SELECT l.id FROM libraries l
                LEFT JOIN organizations o ON o.id = l.org_id
                JOIN organizations owner_org ON owner_org.billing_account_id = ?
                WHERE l.id <> ? AND l.visibility IN ('private', 'org')
                  AND (o.billing_account_id = ? OR l.owner_principal_id = owner_org.owner_principal_id)
                """,
                (ba_id, settings.default_library_id, ba_id),
            )
            for library in libraries:
                library_id = str(library["id"])
                key_rows = db._fetchall(conn, "SELECT key_id FROM api_key_grants WHERE library_id = ? AND role = 'reader'", (library_id,))
                grant_rows = db._fetchall(conn, "SELECT principal_id FROM library_grants WHERE library_id = ? AND role = 'reader'", (library_id,))
                if not key_rows and not grant_rows:
                    continue
                db._execute(conn, "DELETE FROM api_key_grants WHERE library_id = ? AND role = 'reader'", (library_id,))
                db._execute(conn, "DELETE FROM library_grants WHERE library_id = ? AND role = 'reader'", (library_id,))
                revoked.append({"billing_account_id": ba_id, "library_id": library_id, "key_grants": len(key_rows), "library_grants": len(grant_rows)})
    return {"revoked": revoked, "notifications": notifications}
