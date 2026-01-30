-- Migration: Fix balance adjustment sign issue
-- Date: 2026-01-30
-- Description: Fix balance adjustment transactions that were stored with wrong sign.
--              Debits should be negative, but they were stored as positive.

-- Step 1: Fix the specific balance adjustment transaction for ABN AMRO account
-- This transaction was a debit of 1532.78 but stored as positive instead of negative
UPDATE transactions
SET amount = -1532.78,
    updated_at = NOW()
WHERE id = 'e2b15ffb-2662-4349-89b9-ee22f5301b50'
  AND amount = 1532.78
  AND transaction_type = 'debit';

-- Step 2: Recalculate functional_balance for ABN AMRO account
-- Formula: functional_balance = starting_balance + SUM(transactions.amount)
UPDATE accounts
SET functional_balance = (
    SELECT starting_balance + COALESCE(SUM(t.amount), 0)
    FROM transactions t
    WHERE t.account_id = accounts.id
),
    updated_at = NOW()
WHERE id = '869eb9f0-152e-4d6e-9de0-71b41c195af6';

-- Step 3: Generic fix for any other balance adjustment transactions that have the same issue
-- (debit transactions with positive amounts in "Balance adjustment" category)
-- Only run this if you want to fix ALL such transactions, not just the specific one

-- First, let's identify the balancing category ID
-- UPDATE transactions
-- SET amount = -ABS(amount),
--     updated_at = NOW()
-- WHERE description = 'Balance adjustment'
--   AND transaction_type = 'debit'
--   AND amount > 0;

-- Verification query (run after migration):
-- SELECT id, description, amount, transaction_type, booked_at
-- FROM transactions
-- WHERE description ILIKE '%Balance%' OR description ILIKE '%adjustment%'
-- ORDER BY booked_at DESC;

-- Check account balance:
-- SELECT id, name, starting_balance, functional_balance,
--        (SELECT SUM(amount) FROM transactions WHERE account_id = accounts.id) as tx_sum
-- FROM accounts
-- WHERE id = '869eb9f0-152e-4d6e-9de0-71b41c195af6';
