-- Normalize transaction amount signs and add guard constraint.
-- Intended: debit = negative, credit = positive.
-- Run on the app database (finance_db) with sufficient privileges.

-- 1) Fix any inconsistent records (safe, idempotent)
UPDATE transactions
SET amount = -ABS(amount)
WHERE transaction_type = 'debit' AND amount > 0;

UPDATE transactions
SET amount = ABS(amount)
WHERE transaction_type = 'credit' AND amount < 0;

-- 2) Add a guard constraint to prevent future mismatches
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'transactions'::regclass
      AND contype = 'c'
      AND conname = 'transactions_amount_sign_check'
  ) THEN
    ALTER TABLE transactions
      ADD CONSTRAINT transactions_amount_sign_check
      CHECK (
        (transaction_type = 'debit' AND amount <= 0)
        OR (transaction_type = 'credit' AND amount >= 0)
        OR transaction_type IS NULL
      );
  END IF;
END $$;
