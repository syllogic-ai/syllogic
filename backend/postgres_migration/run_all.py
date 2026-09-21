"""
Run all idempotent one-off schema migrations in postgres_migration/ in order.

Drizzle (frontend/) owns the core schema; these scripts cover backend-only
additions (tables/columns SQLAlchemy models expect that Drizzle doesn't
manage). Each one is CREATE ... IF NOT EXISTS / ADD COLUMN IF NOT EXISTS, so
re-running this is always safe.

Data backfills (backfill_encrypted_fields.py, run_encryption_upgrade.py) and
destructive/seed scripts (reset_database.py, seed_data.py, seed_demo_data.py)
are intentionally excluded — those need explicit invocation, not automatic
runs on every build.

Usage (from backend/):
    python postgres_migration/run_all.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from postgres_migration import (
    add_account_alias_patterns,
    add_broker_trades_fees,
    add_mcp_idempotency_keys,
    add_merchant_aliases_table,
    add_receipt_scans,
    add_receipt_ingestion_columns,
    add_transaction_logo_id,
)

MIGRATIONS = [
    add_account_alias_patterns,
    add_broker_trades_fees,
    add_receipt_scans,
    add_receipt_ingestion_columns,
    add_transaction_logo_id,
    add_merchant_aliases_table,
    add_mcp_idempotency_keys,
]


def main() -> int:
    for module in MIGRATIONS:
        rc = module.main()
        if rc:
            print(f"FAILED: {module.__name__} exited with {rc}")
            return rc
    print(f"OK: {len(MIGRATIONS)} backend schema migration(s) applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
