from __future__ import annotations

from app.services.api_key_encryption import encrypt_stored_key, reveal_stored_key


def test_encrypt_reveal_roundtrip():
    plaintext = "ma3k_deadbeef0123456789abcdef012345"
    ciphertext = encrypt_stored_key(plaintext)
    assert ciphertext != plaintext
    assert reveal_stored_key(ciphertext) == plaintext


def test_reveal_missing_ciphertext():
    assert reveal_stored_key(None) is None
    assert reveal_stored_key("") is None
