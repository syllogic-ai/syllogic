"""Unit tests for the backend receipt storage boundary (Phase 1 of the
receipt-ingestion rework -- see docs/specs/receipt-ingestion-implementation.md
1.2 and its "Phase 1 tests" section)."""

import hashlib
import uuid

import pytest

from app.security.data_encryption import decrypt_value
from app.services import receipt_storage


@pytest.fixture(autouse=True)
def _isolated_storage_root(tmp_path, monkeypatch):
    """Point the module at a scratch directory so tests never touch a real
    uploads tree and never collide with each other."""
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    yield tmp_path


def test_put_get_round_trip():
    data = b"fake-receipt-image-bytes"
    stored = receipt_storage.put("user-1", data, "image/png")
    assert receipt_storage.get(stored.file_path) == data


def test_path_contains_user_id_and_a_uuid_never_a_supplied_filename():
    stored = receipt_storage.put("user-42", b"data", "image/jpeg")

    assert stored.file_path.startswith("receipt-scans/user-42/")

    filename = stored.file_path.rsplit("/", 1)[-1]
    name, ext = filename.rsplit(".", 1)
    # `put` takes no filename argument at all -- the only thing that can end
    # up in the path besides the user id is a freshly generated uuid.
    uuid.UUID(name)
    assert ext == "jpg"


def test_unknown_content_type_falls_back_to_jpg():
    stored = receipt_storage.put("user-1", b"data", "application/pdf")
    assert stored.file_path.endswith(".jpg")


def test_file_path_ciphertext_decrypts_back_to_file_path():
    stored = receipt_storage.put("user-1", b"data", "image/png")
    assert stored.file_path_ciphertext is not None
    assert decrypt_value(stored.file_path_ciphertext) == stored.file_path


def test_put_returns_sha256_of_the_bytes():
    data = b"some receipt bytes to hash"
    stored = receipt_storage.put("user-1", data, "image/png")
    assert stored.sha256 == hashlib.sha256(data).hexdigest()


def test_delete_removes_the_file():
    stored = receipt_storage.put("user-1", b"data", "image/png")
    receipt_storage.delete(stored.file_path)
    with pytest.raises(FileNotFoundError):
        receipt_storage.get(stored.file_path)


def test_delete_is_a_no_op_for_a_missing_file():
    # Deleting a scan whose blob was already removed (or never written)
    # should not raise.
    receipt_storage.delete("receipt-scans/user-1/does-not-exist.jpg")


def test_get_rejects_a_path_escaping_the_storage_root():
    with pytest.raises(ValueError):
        receipt_storage.get("../../etc/passwd")


def test_content_type_for_path_uses_the_extension():
    assert receipt_storage.content_type_for_path("receipt-scans/u/x.jpg") == "image/jpeg"
    assert receipt_storage.content_type_for_path("receipt-scans/u/x.png") == "image/png"
    assert receipt_storage.content_type_for_path("receipt-scans/u/x.heic") == "image/heic"
    assert (
        receipt_storage.content_type_for_path("receipt-scans/u/x.bin") == "application/octet-stream"
    )
