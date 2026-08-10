"""Periodic billing maintenance: usage-event flush + past_due grace job.

Wired from ``app.main`` lifespan. Notifications have no mail transport yet —
they are logged so operators / a future mailer can consume them.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_billing_maintenance_once() -> dict[str, Any]:
    """Flush the in-process usage buffer and run the past_due grace job once."""
    from app.services import billing_grace_service, usage_service

    usage_service.flush_usage_events()
    grace = billing_grace_service.run_past_due_grace_job()
    for note in grace.get("notifications") or []:
        logger.info(
            "billing grace notification ba=%s kind=%s",
            note.get("billing_account_id"),
            note.get("kind"),
        )
    for row in grace.get("revoked") or []:
        logger.info(
            "billing grace revoked ba=%s library=%s key_grants=%s library_grants=%s",
            row.get("billing_account_id"),
            row.get("library_id"),
            row.get("key_grants"),
            row.get("library_grants"),
        )
    return {"flushed": True, "grace": grace}
