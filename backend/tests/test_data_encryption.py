"""
Unit tests for application-layer data encryption helpers.
"""
import base64
import os
import sys
from contextlib import contextmanager

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.security.data_encryption import (  # noqa: E402
    blind_index,
    blind_index_candidates,
    decrypt_with_fallback,
    decrypt_value,
    encrypt_value,
    reset_encryption_config_cache,
)


def _b64_key(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


@contextmanager
def _temporary_encryption_env(current: bytes, key_id: str, previous: bytes | None = None):
    tracked_keys = (
        "DATA_ENCRYPTION_KEY_CURRENT",
        "DATA_ENCRYPTION_KEY_PREVIOUS",
        "DATA_ENCRYPTION_KEY_ID",
    )
    original_values = {key: os.environ.get(key) for key in tracked_keys}

    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = _b64_key(current)
    os.environ["DATA_ENCRYPTION_KEY_ID"] = key_id
    if previous is not None:
        os.environ["DATA_ENCRYPTION_KEY_PREVIOUS"] = _b64_key(previous)
    elif "DATA_ENCRYPTION_KEY_PREVIOUS" in os.environ:
        del os.environ["DATA_ENCRYPTION_KEY_PREVIOUS"]
    reset_encryption_config_cache()

    try:
        yield
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_encryption_config_cache()


def test_roundtrip() -> None:
    with _temporary_encryption_env(b"0" * 32, "k1"):
        plaintext = "acct_12345"
        encrypted = encrypt_value(plaintext)

        assert encrypted is not None
        assert encrypted.startswith("enc:v1:k1:")
        assert decrypt_value(encrypted) == plaintext
        print("✓ roundtrip")


def test_blind_index_determinism() -> None:
    with _temporary_encryption_env(b"1" * 32, "k2"):
        value = "provider-account-id"
        one = blind_index(value)
        two = blind_index(value)

        assert one is not None
        assert one == two
        assert len(one) == 64
        print("✓ blind index determinism")


def test_key_rotation_fallback() -> None:
    old_key = b"2" * 32
    new_key = b"3" * 32

    with _temporary_encryption_env(old_key, "k-old"):
        encrypted_with_old = encrypt_value("legacy-value")
        old_hash = blind_index("legacy-value")

    with _temporary_encryption_env(new_key, "k-new", previous=old_key):
        assert decrypt_value(encrypted_with_old) == "legacy-value"

        candidates = blind_index_candidates("legacy-value")
        assert len(candidates) == 2
        assert old_hash in candidates
        print("✓ key rotation fallback")


def test_decrypt_with_fallback_on_decrypt_error() -> None:
    old_key = b"4" * 32
    new_key = b"5" * 32

    with _temporary_encryption_env(old_key, "k-old"):
        encrypted_with_old = encrypt_value("legacy-value")

    with _temporary_encryption_env(new_key, "k-new"):
        # No previous key configured; decrypt should fail and fallback to plaintext.
        assert decrypt_with_fallback(encrypted_with_old, "legacy-value") == "legacy-value"
        print("✓ decrypt fallback on error")


if __name__ == "__main__":
    test_roundtrip()
    test_blind_index_determinism()
    test_key_rotation_fallback()
    test_decrypt_with_fallback_on_decrypt_error()
    print("All data encryption tests passed.")
