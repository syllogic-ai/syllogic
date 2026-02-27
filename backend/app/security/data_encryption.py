"""
Application-layer field encryption helpers.

Envelope format:
    enc:v1:<keyId>:<base64url(nonce + ciphertext)>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_ENVELOPE_PREFIX = "enc:v1"


@dataclass(frozen=True)
class _EncryptionConfig:
    current_key: Optional[bytes]
    previous_key: Optional[bytes]
    key_id: str

    @property
    def enabled(self) -> bool:
        return self.current_key is not None


def _parse_key(raw: str) -> bytes:
    candidate = raw.strip()
    if not candidate:
        raise ValueError("Encryption key cannot be empty.")

    # Support hex keys for operational convenience.
    if all(ch in "0123456789abcdefABCDEF" for ch in candidate) and len(candidate) % 2 == 0:
        decoded = bytes.fromhex(candidate)
        if len(decoded) == 32:
            return decoded

    padded = candidate + ("=" * ((4 - len(candidate) % 4) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
        if len(decoded) == 32:
            return decoded
    except Exception as exc:  # pragma: no cover - explicit error below
        raise ValueError("Invalid base64 data encryption key.") from exc

    raise ValueError("Data encryption key must decode to exactly 32 bytes.")


@lru_cache(maxsize=1)
def _load_config() -> _EncryptionConfig:
    current_raw = os.getenv("DATA_ENCRYPTION_KEY_CURRENT", "").strip()
    previous_raw = os.getenv("DATA_ENCRYPTION_KEY_PREVIOUS", "").strip()
    key_id = os.getenv("DATA_ENCRYPTION_KEY_ID", "k1").strip() or "k1"

    current_key = _parse_key(current_raw) if current_raw else None
    previous_key = _parse_key(previous_raw) if previous_raw else None

    return _EncryptionConfig(
        current_key=current_key,
        previous_key=previous_key,
        key_id=key_id,
    )


def is_data_encryption_enabled() -> bool:
    return _load_config().enabled


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(raw: str) -> bytes:
    padded = raw + ("=" * ((4 - len(raw) % 4) % 4))
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None

    config = _load_config()
    if not config.enabled:
        return None

    nonce = os.urandom(12)
    ciphertext = AESGCM(config.current_key).encrypt(
        nonce=nonce,
        data=plaintext.encode("utf-8"),
        associated_data=None,
    )
    payload = _urlsafe_b64encode(nonce + ciphertext)
    return f"{_ENVELOPE_PREFIX}:{config.key_id}:{payload}"


def decrypt_value(ciphertext: Optional[str]) -> Optional[str]:
    if ciphertext is None:
        return None

    if not ciphertext.startswith(f"{_ENVELOPE_PREFIX}:"):
        # Backward compatibility with plaintext rows.
        return ciphertext

    parts = ciphertext.split(":", 3)
    if len(parts) != 4:
        raise ValueError("Invalid encrypted value format.")

    _enc, _version, embedded_key_id, payload = parts
    blob = _urlsafe_b64decode(payload)
    if len(blob) < 13:
        raise ValueError("Encrypted payload is too short.")

    nonce = blob[:12]
    encrypted = blob[12:]

    config = _load_config()
    if not config.enabled:
        raise ValueError("Encrypted data found but DATA_ENCRYPTION_KEY_CURRENT is not configured.")

    candidate_keys = []
    if embedded_key_id == config.key_id:
        candidate_keys.append(config.current_key)
        if config.previous_key:
            candidate_keys.append(config.previous_key)
    else:
        if config.previous_key:
            candidate_keys.append(config.previous_key)
        candidate_keys.append(config.current_key)

    last_error = None
    for key in candidate_keys:
        try:
            plaintext = AESGCM(key).decrypt(
                nonce=nonce,
                data=encrypted,
                associated_data=None,
            )
            return plaintext.decode("utf-8")
        except Exception as exc:  # pragma: no cover - final error below
            last_error = exc

    raise ValueError("Failed to decrypt encrypted value with configured keys.") from last_error


def decrypt_with_fallback(ciphertext: Optional[str], plaintext_fallback: Optional[str]) -> Optional[str]:
    if ciphertext:
        return decrypt_value(ciphertext)
    return plaintext_fallback


def _blind_index_key(raw_key: bytes) -> bytes:
    return hmac.new(raw_key, b"blind-index:v1", hashlib.sha256).digest()


def blind_index(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    config = _load_config()
    if not config.enabled:
        return None

    key = _blind_index_key(config.current_key)
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def blind_index_candidates(value: Optional[str]) -> list[str]:
    if value is None:
        return []

    config = _load_config()
    if not config.enabled:
        return []

    candidates: list[str] = []
    current = hmac.new(
        _blind_index_key(config.current_key),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    candidates.append(current)

    if config.previous_key:
        previous = hmac.new(
            _blind_index_key(config.previous_key),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if previous != current:
            candidates.append(previous)

    return candidates


def reset_encryption_config_cache() -> None:
    _load_config.cache_clear()
