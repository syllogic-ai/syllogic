import os
import json
import pytest
from app.services import credentials_crypto


def test_round_trip_encrypts_and_decrypts(monkeypatch):
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    payload = {"flex_token": "abc", "query_id_positions": "111"}
    blob = credentials_crypto.encrypt(payload)
    assert isinstance(blob, str)
    assert "abc" not in blob
    assert credentials_crypto.decrypt(blob) == payload


def test_decrypt_rejects_tampered_blob(monkeypatch):
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    blob = credentials_crypto.encrypt({"a": "b"})
    tampered = blob[:-2] + ("AA" if blob[-2:] != "AA" else "BB")
    with pytest.raises(credentials_crypto.CredentialDecryptError):
        credentials_crypto.decrypt(tampered)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("SYLLOGIC_SECRET_KEY", raising=False)
    with pytest.raises(credentials_crypto.CredentialKeyMissing):
        credentials_crypto.encrypt({"x": 1})
