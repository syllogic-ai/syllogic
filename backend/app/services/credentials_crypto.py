import json
import os
from cryptography.fernet import Fernet, InvalidToken


class CredentialKeyMissing(RuntimeError):
    pass


class CredentialDecryptError(RuntimeError):
    pass


def generate_key() -> str:
    return Fernet.generate_key().decode()


def _fernet() -> Fernet:
    key = os.getenv("SYLLOGIC_SECRET_KEY")
    if not key:
        raise CredentialKeyMissing("SYLLOGIC_SECRET_KEY env var is required to encrypt/decrypt credentials")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(payload: dict) -> str:
    return _fernet().encrypt(json.dumps(payload, sort_keys=True).encode()).decode()


def decrypt(blob: str) -> dict:
    try:
        raw = _fernet().decrypt(blob.encode())
    except InvalidToken as e:
        raise CredentialDecryptError("Invalid or tampered credential blob") from e
    return json.loads(raw.decode())
