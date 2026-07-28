"""Self-host first-run setup state (local auth, no OIDC)."""
from __future__ import annotations

from typing import Any, Literal

from app.core.config import settings
from app.storage import db

SetupState = Literal["needs_owner", "guided_ramp", "steady"]

SETTING_SETUP_COMPLETE = "setup_complete"
SETTING_REGISTRATION_ACK = "setup_registration_ack"
SETTING_REGISTRATION_OPEN = "local_registration_open"
_BOOTSTRAP_KEY_ID = "key_selfhost_bootstrap"


def setup_applicable() -> bool:
    return bool(settings.local_auth_enabled)


def setup_needs_owner() -> bool:
    return setup_applicable() and db.count_local_accounts() == 0


def registration_policy_handled() -> bool:
    """C4: registration closed, or admin explicitly kept open."""
    from app.services.local_auth_service import is_registration_open

    if not is_registration_open():
        return True
    ack = db.get_instance_setting(SETTING_REGISTRATION_ACK)
    return ack == "keep_open"


def admin_has_non_bootstrap_api_key() -> bool:
    """C3: at least one non-bootstrap API key on an admin local principal."""
    bootstrap_pid = settings.bootstrap_principal_id
    for acc in db.list_local_accounts(limit=500):
        if not int(acc.get("is_admin") or 0):
            continue
        pid = str(acc["principal_id"])
        if pid == bootstrap_pid:
            continue
        for key in db.list_api_keys_for_principal(pid):
            if key.get("revoked_at"):
                continue
            if str(key.get("key_id") or "") == _BOOTSTRAP_KEY_ID:
                continue
            return True
    return False


def setup_complete() -> bool:
    """True only after admin explicitly finishes (or local auth N/A)."""
    if not setup_applicable():
        return True
    return db.get_instance_setting(SETTING_SETUP_COMPLETE) == "1"


def checklist_ready_to_finish() -> bool:
    """C3 + C4 satisfied — enables the Finish button."""
    return admin_has_non_bootstrap_api_key() and registration_policy_handled()


def setup_in_progress() -> bool:
    return setup_applicable() and db.count_local_accounts() >= 1 and not setup_complete()


def setup_state() -> SetupState:
    if not setup_applicable():
        return "steady"
    if setup_needs_owner():
        return "needs_owner"
    if setup_in_progress():
        return "guided_ramp"
    return "steady"


def checklist_status() -> dict[str, Any]:
    from app.services.local_auth_service import is_registration_open

    return {
        "state": setup_state(),
        "admin_exists": db.count_local_accounts() >= 1,
        "has_admin_key": admin_has_non_bootstrap_api_key(),
        "registration_open": is_registration_open(),
        "registration_ack": db.get_instance_setting(SETTING_REGISTRATION_ACK),
        "registration_handled": registration_policy_handled(),
        "checklist_ready": checklist_ready_to_finish(),
        "setup_complete": setup_complete(),
    }


def mark_setup_complete() -> None:
    db.set_instance_setting(SETTING_SETUP_COMPLETE, "1")


def ack_registration_keep_open() -> None:
    db.set_instance_setting(SETTING_REGISTRATION_ACK, "keep_open")


def set_registration_open(open_: bool) -> None:
    db.set_instance_setting(SETTING_REGISTRATION_OPEN, "true" if open_ else "false")
    if not open_:
        # Closing registration satisfies C4; clear keep_open ack if any.
        ack = db.get_instance_setting(SETTING_REGISTRATION_ACK)
        if ack == "keep_open":
            db.delete_instance_setting(SETTING_REGISTRATION_ACK)
