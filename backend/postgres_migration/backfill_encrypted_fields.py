"""
Backfill encrypted columns for accounts.external_id and csv_imports.file_path.

Usage:
  cd backend
  python postgres_migration/backfill_encrypted_fields.py --batch-size 500
"""
from __future__ import annotations

import argparse

from app.database import SessionLocal
from app.models import Account, CsvImport
from app.security.data_encryption import blind_index, encrypt_value, is_data_encryption_enabled


def backfill(batch_size: int, dry_run: bool, clear_plaintext: bool) -> dict[str, int]:
    if not is_data_encryption_enabled():
        raise RuntimeError(
            "DATA_ENCRYPTION_KEY_CURRENT is required for backfill. "
            "Set DATA_ENCRYPTION_KEY_CURRENT and DATA_ENCRYPTION_KEY_ID first."
        )

    db = SessionLocal()
    updated_accounts = 0
    updated_csv_imports = 0
    try:
        while True:
            accounts = (
                db.query(Account)
                .filter(
                    Account.external_id.isnot(None),
                    (Account.external_id_ciphertext.is_(None) | Account.external_id_hash.is_(None)),
                )
                .limit(batch_size)
                .all()
            )
            if not accounts:
                break

            for account in accounts:
                account.external_id_ciphertext = encrypt_value(account.external_id)
                account.external_id_hash = blind_index(account.external_id)
                if clear_plaintext:
                    account.external_id = None
                updated_accounts += 1

            if dry_run:
                db.rollback()
                break
            db.commit()

        while True:
            imports = (
                db.query(CsvImport)
                .filter(
                    CsvImport.file_path.isnot(None),
                    CsvImport.file_path_ciphertext.is_(None),
                )
                .limit(batch_size)
                .all()
            )
            if not imports:
                break

            for csv_import in imports:
                csv_import.file_path_ciphertext = encrypt_value(csv_import.file_path)
                if clear_plaintext:
                    csv_import.file_path = None
                updated_csv_imports += 1

            if dry_run:
                db.rollback()
                break
            db.commit()

        if dry_run:
            db.rollback()

        return {
            "accounts_updated": updated_accounts,
            "csv_imports_updated": updated_csv_imports,
        }
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--clear-plaintext",
        action="store_true",
        help="Also clear plaintext columns after ciphertext/hash backfill.",
    )
    args = parser.parse_args()

    result = backfill(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        clear_plaintext=args.clear_plaintext,
    )
    print(result)
