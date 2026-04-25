"""
One-off migration: add accounts.alias_patterns JSONB column.

Usage (from backend/):
    python postgres_migration/add_account_alias_patterns.py

Idempotent: safe to re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text

from app.database import db_url


SQL = """
ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS alias_patterns JSONB NOT NULL DEFAULT '[]'::jsonb;
"""


def main() -> int:
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(SQL))
    print("OK: accounts.alias_patterns present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
