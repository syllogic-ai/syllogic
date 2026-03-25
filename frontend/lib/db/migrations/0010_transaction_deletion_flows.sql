-- Migration: Transaction Deletion Flows (SYL-22)
-- Adds csv_import_id to transactions and balance_is_anchored to accounts

-- Link transactions back to their source CSV import
ALTER TABLE transactions ADD COLUMN csv_import_id uuid REFERENCES csv_imports(id) ON DELETE SET NULL;
CREATE INDEX idx_transactions_csv_import ON transactions(csv_import_id);

-- Track whether an account's starting balance is anchored from known bank data
ALTER TABLE accounts ADD COLUMN balance_is_anchored boolean DEFAULT false;
