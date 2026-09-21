"""
One-off migration: receipt ingestion columns on receipt_scans, plus the new
receipt_line_items table.

See docs/specs/receipt-ingestion-implementation.md Phase 2. Additive only --
`receipt_total` and `raw_ocr_text` are kept for one more release; nothing here
drops a column.

Usage (from backend/):
    python postgres_migration/add_receipt_ingestion_columns.py

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
ALTER TABLE receipt_scans
    ADD COLUMN IF NOT EXISTS currency               VARCHAR(3),
    ADD COLUMN IF NOT EXISTS printed_total          NUMERIC(15, 2),
    ADD COLUMN IF NOT EXISTS printed_discount_total NUMERIC(15, 2),
    ADD COLUMN IF NOT EXISTS merchant_legal_name    VARCHAR(255),
    ADD COLUMN IF NOT EXISTS merchant_address       TEXT,
    ADD COLUMN IF NOT EXISTS receipt_no             VARCHAR(64),
    ADD COLUMN IF NOT EXISTS fiscal_code            VARCHAR(64),
    ADD COLUMN IF NOT EXISTS vat_id                 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS payment_method         VARCHAR(16),
    ADD COLUMN IF NOT EXISTS card_last4             VARCHAR(4),
    ADD COLUMN IF NOT EXISTS file_sha256            CHAR(64),
    ADD COLUMN IF NOT EXISTS validation_errors      JSONB,
    ADD COLUMN IF NOT EXISTS extraction_model       VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_receipt_scans_sha256
    ON receipt_scans (user_id, file_sha256)
    WHERE file_sha256 IS NOT NULL;

CREATE TABLE IF NOT EXISTS receipt_line_items (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_scan_id       UUID NOT NULL REFERENCES receipt_scans(id) ON DELETE CASCADE,
    line_ref              VARCHAR(8) NOT NULL,
    position              INTEGER NOT NULL,
    raw_text              TEXT,
    name                  TEXT,
    quantity              NUMERIC(12, 3),
    gross_amount          NUMERIC(15, 2),
    discount_amount       NUMERIC(15, 2) DEFAULT 0,
    net_amount            NUMERIC(15, 2),
    kind                  VARCHAR(16) NOT NULL DEFAULT 'item',
    parent_line_ref       VARCHAR(8),
    category_id           UUID REFERENCES categories(id),
    category_confidence   VARCHAR(8),
    category_reason       TEXT,
    user_edited           BOOLEAN NOT NULL DEFAULT false,
    booked_transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
    created_at            TIMESTAMP DEFAULT now(),
    updated_at            TIMESTAMP DEFAULT now(),
    CONSTRAINT receipt_line_items_scan_ref_uq UNIQUE (receipt_scan_id, line_ref)
);

CREATE INDEX IF NOT EXISTS idx_receipt_line_items_scan
    ON receipt_line_items (receipt_scan_id);
CREATE INDEX IF NOT EXISTS idx_receipt_line_items_txn
    ON receipt_line_items (booked_transaction_id);
"""


def main() -> int:
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(SQL))
    print("OK: receipt ingestion columns and receipt_line_items table present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
