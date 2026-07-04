"""Encrypt API key plaintext at rest so owners can reveal it again in /ui/keys."""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _fernet_key_material() -> bytes:
    secret = (
        settings.api_key_encryption_secret.strip()
        or settings.authing_app_secret.strip()
        or "ma3-dev-insecure-key-encryption"
    )
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def encrypt_stored_key(plaintext: str) -> str:
    return Fernet(_fernet_key_material()).encrypt(plaintext.encode("utf-8")).decode("ascii")


def reveal_stored_key(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return Fernet(_fernet_key_material()).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.warning("api_key_ciphertext_decrypt_failed")
        return None
