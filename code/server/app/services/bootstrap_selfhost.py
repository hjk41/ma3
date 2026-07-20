"""Create the first self-host admin API key when OIDC is not configured."""
from __future__ import annotations

import hashlib
import logging
import secrets
from pathlib import Path

from app.core.config import settings
from app.services.api_key_encryption import encrypt_stored_key
from app.services.api_key_service import hash_key
from app.storage import db

logger = logging.getLogger(__name__)

_BOOTSTRAP_KEY_ID = "key_selfhost_bootstrap"


def _personal_library_id(principal_id: str) -> str:
    digest = hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:12]
    return f"lib_personal_{digest}"


def ensure_bootstrap_key(*, force_new: bool = False) -> dict[str, str] | None:
    """Idempotently ensure a writer API key for self-host bootstrap.

    Returns key metadata when a new plaintext is generated; None when skipped
    (OIDC on, bootstrap disabled, or existing key file already present).
    """
    if settings.oidc_configured:
        logger.info("OIDC configured; skipping self-host bootstrap key")
        return None
    if not settings.bootstrap_selfhost:
        logger.info("MA3_BOOTSTRAP_SELFHOST=0; skipping bootstrap key")
        return None

    key_path = Path(settings.bootstrap_key_file)
    if key_path.is_file() and not force_new:
        logger.info("bootstrap key file already exists at %s", key_path)
        return None

    principal_id = settings.bootstrap_principal_id
    if not principal_id.startswith("user:"):
        principal_id = f"user:{principal_id}"
    sso_user = principal_id.removeprefix("user:")
    library_id = _personal_library_id(principal_id)

    db.upsert_user_principal(sso_user=sso_user, display_name=settings.bootstrap_display_name)
    try:
        db.set_user_display_name(principal_id, settings.bootstrap_display_name)
    except Exception:
        logger.debug("set_user_display_name skipped", exc_info=True)

    db.ensure_library(
        library_id,
        name=f"{settings.bootstrap_display_name} personal library",
        visibility="private",
        kind="personal",
        owner_principal_id=principal_id,
    )

    existing = db.get_api_key_by_id(_BOOTSTRAP_KEY_ID)
    plaintext: str | None = None
    if existing is None or force_new:
        if force_new and existing is not None:
            db.delete_api_key(_BOOTSTRAP_KEY_ID, principal_id=principal_id)
        plaintext = f"ma3k_{secrets.token_hex(16)}"
        db.insert_api_key(
            key_id=_BOOTSTRAP_KEY_ID,
            key_hash=hash_key(plaintext),
            key_prefix=plaintext[:12],
            key_ciphertext=encrypt_stored_key(plaintext),
            principal_id=principal_id,
            label="selfhost-bootstrap",
            grants=[
                {"library_id": library_id, "role": "writer"},
                {"library_id": settings.default_library_id, "role": "writer"},
            ],
        )
    else:
        # Key row exists but file missing — cannot recover plaintext; rotate.
        plaintext = f"ma3k_{secrets.token_hex(16)}"
        db.delete_api_key(_BOOTSTRAP_KEY_ID, principal_id=principal_id)
        db.insert_api_key(
            key_id=_BOOTSTRAP_KEY_ID,
            key_hash=hash_key(plaintext),
            key_prefix=plaintext[:12],
            key_ciphertext=encrypt_stored_key(plaintext),
            principal_id=principal_id,
            label="selfhost-bootstrap",
            grants=[
                {"library_id": library_id, "role": "writer"},
                {"library_id": settings.default_library_id, "role": "writer"},
            ],
        )

    assert plaintext is not None
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(
        "\n".join(
            [
                f"# ma3 self-host bootstrap API key (keep secret)",
                f"principal_id={principal_id}",
                f"library_id={library_id}",
                f"key_id={_BOOTSTRAP_KEY_ID}",
                f"plaintext_key={plaintext}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    try:
        key_path.chmod(0o600)
    except OSError:
        pass

    logger.warning(
        "self-host bootstrap API key written to %s — use as X-API-Key; rotate if exposed",
        key_path.resolve(),
    )
    return {
        "principal_id": principal_id,
        "library_id": library_id,
        "key_id": _BOOTSTRAP_KEY_ID,
        "plaintext_key": plaintext,
        "key_file": str(key_path.resolve()),
    }
