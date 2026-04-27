"""
One-off migration: add broker_trades.fees column.

Usage (from backend/):
    python postgres_migration/add_broker_trades_fees.py

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
ALTER TABLE broker_trades
  ADD COLUMN IF NOT EXISTS fees NUMERIC(28, 8) NOT NULL DEFAULT 0;
"""


def main() -> int:
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(SQL))
    print("OK: broker_trades.fees present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
