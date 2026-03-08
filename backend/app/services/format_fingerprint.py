"""
Format fingerprinting for bank file imports.

Computes a SHA-256 fingerprint from sorted column headers so that
files with the same column structure (regardless of column order or
file type) produce identical fingerprints.
"""
import hashlib
from typing import List


def compute_fingerprint(column_headers: List[str]) -> str:
    sorted_headers = sorted(column_headers)
    joined = "|".join(sorted_headers)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
