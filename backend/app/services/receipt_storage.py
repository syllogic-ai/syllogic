"""
Backend storage boundary for receipt photos.

The backend is the single writer for receipt blobs (see
docs/specs/receipt-ingestion.md Part 4.2 and
docs/specs/receipt-ingestion-implementation.md 1.2): the frontend server
action streams the raw upload straight through, and this module is the only
thing that touches disk. It deliberately mirrors
frontend/features/receipt-scan/server/receipt-file.storage.ts -- same
`receipt-scans/{user_id}/{uuid}.{ext}` layout, same content-type allowlist, and
the same rule that a client-supplied filename never reaches the path -- so a
future object-store implementation can drop in on either side without callers
changing (frontend/lib/storage/index.ts:24 already stubs `r2` as "not
implemented yet"; this module does not implement it either).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.security.data_encryption import encrypt_value

# Mirrors EXTENSION_BY_CONTENT_TYPE in
# frontend/features/receipt-scan/server/receipt-file.storage.ts:13 -- keep
# both allowlists in sync.
EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "image/webp": "webp",
}

# Reverse of the above, for serving a stored file back with a sane
# Content-Type when all we have on hand is its extension.
CONTENT_TYPE_BY_EXTENSION: dict[str, str] = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "heic": "image/heic",
    "webp": "image/webp",
}

DEFAULT_STORAGE_ROOT = "uploads"


def _storage_root() -> Path:
    raw = os.getenv("LOCAL_STORAGE_PATH", "").strip() or DEFAULT_STORAGE_ROOT
    return Path(raw).resolve()


def _resolve(file_path: str) -> Path:
    """Resolves a stored relative path against the storage root, refusing to
    step outside it. Mirrors the equivalent guard in
    frontend/lib/storage/local.ts's `getFullPath`."""
    if not file_path or os.path.isabs(file_path):
        raise ValueError("Storage path must be a non-empty relative path")

    root = _storage_root()
    full_path = (root / file_path).resolve()
    if full_path == root or root not in full_path.parents:
        raise ValueError("Storage path escapes the configured storage root")
    return full_path


@dataclass(frozen=True)
class StoredReceipt:
    file_path: str
    file_path_ciphertext: str | None
    sha256: str


def put(user_id: str, data: bytes, content_type: str) -> StoredReceipt:
    """Writes a receipt photo and returns its path (plus ciphertext and
    digest). The extension comes only from `EXTENSION_BY_CONTENT_TYPE`; a
    client-supplied filename never reaches the path."""
    extension = EXTENSION_BY_CONTENT_TYPE.get(content_type, "jpg")
    file_path = f"receipt-scans/{user_id}/{uuid4()}.{extension}"

    full_path = _resolve(file_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(data)

    digest = hashlib.sha256(data).hexdigest()
    return StoredReceipt(
        file_path=file_path,
        file_path_ciphertext=encrypt_value(file_path),
        sha256=digest,
    )


def get(file_path: str) -> bytes:
    return _resolve(file_path).read_bytes()


def delete(file_path: str) -> None:
    try:
        _resolve(file_path).unlink()
    except FileNotFoundError:
        pass


def content_type_for_path(file_path: str) -> str:
    extension = Path(file_path).suffix.lstrip(".").lower()
    return CONTENT_TYPE_BY_EXTENSION.get(extension, "application/octet-stream")
