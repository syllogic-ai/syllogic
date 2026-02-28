"""
One-command encrypted field upgrade for existing databases.

Usage:
  cd backend
  python postgres_migration/run_encryption_upgrade.py --batch-size 500
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import func, or_

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import Account, CsvImport
from app.security.data_encryption import (
    is_data_encryption_enabled,
    reset_encryption_config_cache,
)
from postgres_migration.backfill_encrypted_fields import backfill


def validate_encryption_configuration() -> None:
    current_key = os.getenv("DATA_ENCRYPTION_KEY_CURRENT", "").strip()
    key_id = os.getenv("DATA_ENCRYPTION_KEY_ID", "").strip()

    if not current_key:
        raise RuntimeError("DATA_ENCRYPTION_KEY_CURRENT is required.")
    if not key_id:
        raise RuntimeError("DATA_ENCRYPTION_KEY_ID is required.")

    reset_encryption_config_cache()
    try:
        enabled = is_data_encryption_enabled()
    except Exception as exc:
        raise RuntimeError(f"Invalid data encryption configuration: {exc}") from exc

    if not enabled:
        raise RuntimeError("Data encryption is not enabled after configuration validation.")


def collect_coverage() -> dict[str, int]:
    db = SessionLocal()
    try:
        accounts_total = db.query(func.count(Account.id)).scalar() or 0
        external_id_plaintext_present = (
            db.query(func.count(Account.id))
            .filter(Account.external_id.isnot(None))
            .scalar()
            or 0
        )
        external_id_ciphertext_present = (
            db.query(func.count(Account.id))
            .filter(Account.external_id_ciphertext.isnot(None))
            .scalar()
            or 0
        )
        external_id_hash_present = (
            db.query(func.count(Account.id))
            .filter(Account.external_id_hash.isnot(None))
            .scalar()
            or 0
        )
        accounts_missing_encryption = (
            db.query(func.count(Account.id))
            .filter(Account.external_id.isnot(None))
            .filter(
                or_(
                    Account.external_id_ciphertext.is_(None),
                    Account.external_id_hash.is_(None),
                )
            )
            .scalar()
            or 0
        )

        csv_total = db.query(func.count(CsvImport.id)).scalar() or 0
        file_path_plaintext_present = (
            db.query(func.count(CsvImport.id))
            .filter(CsvImport.file_path.isnot(None))
            .scalar()
            or 0
        )
        file_path_ciphertext_present = (
            db.query(func.count(CsvImport.id))
            .filter(CsvImport.file_path_ciphertext.isnot(None))
            .scalar()
            or 0
        )
        csv_missing_encryption = (
            db.query(func.count(CsvImport.id))
            .filter(CsvImport.file_path.isnot(None))
            .filter(CsvImport.file_path_ciphertext.is_(None))
            .scalar()
            or 0
        )

        return {
            "accounts_total": int(accounts_total),
            "external_id_plaintext_present": int(external_id_plaintext_present),
            "external_id_ciphertext_present": int(external_id_ciphertext_present),
            "external_id_hash_present": int(external_id_hash_present),
            "accounts_missing_encryption": int(accounts_missing_encryption),
            "csv_total": int(csv_total),
            "file_path_plaintext_present": int(file_path_plaintext_present),
            "file_path_ciphertext_present": int(file_path_ciphertext_present),
            "csv_missing_encryption": int(csv_missing_encryption),
        }
    finally:
        db.close()


def coverage_is_complete(coverage: dict[str, int], require_plaintext_cleared: bool) -> bool:
    if coverage["accounts_missing_encryption"] > 0:
        return False
    if coverage["csv_missing_encryption"] > 0:
        return False

    if require_plaintext_cleared:
        if coverage["external_id_plaintext_present"] > 0:
            return False
        if coverage["file_path_plaintext_present"] > 0:
            return False

    return True


def run_upgrade(batch_size: int, dry_run: bool, clear_plaintext: bool) -> tuple[dict[str, int], dict[str, int]]:
    validate_encryption_configuration()

    backfill_result = backfill(
        batch_size=batch_size,
        dry_run=dry_run,
        clear_plaintext=clear_plaintext,
    )
    coverage = collect_coverage()
    return backfill_result, coverage


def _print_summary(backfill_result: dict[str, int], coverage: dict[str, int]) -> None:
    print("Backfill result:")
    for key in sorted(backfill_result):
        print(f"  {key}: {backfill_result[key]}")

    print("Coverage summary:")
    for key in (
        "accounts_total",
        "external_id_plaintext_present",
        "external_id_ciphertext_present",
        "external_id_hash_present",
        "accounts_missing_encryption",
        "csv_total",
        "file_path_plaintext_present",
        "file_path_ciphertext_present",
        "csv_missing_encryption",
    ):
        print(f"  {key}: {coverage[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--clear-plaintext",
        action="store_true",
        help="Also clear plaintext columns after ciphertext/hash backfill.",
    )
    args = parser.parse_args(argv)

    if args.batch_size <= 0:
        print("Batch size must be greater than 0.", file=sys.stderr)
        return 2

    backfill_result, coverage = run_upgrade(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        clear_plaintext=args.clear_plaintext,
    )
    _print_summary(backfill_result, coverage)

    if not coverage_is_complete(coverage, require_plaintext_cleared=args.clear_plaintext):
        print(
            "Encryption upgrade is incomplete. "
            "Re-run the command until missing counters are zero.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print("Dry-run completed with full coverage.")
    else:
        print("Encryption upgrade completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
