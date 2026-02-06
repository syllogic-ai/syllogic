-- Add trigram indexes for fast ILIKE text search
-- Run this once against your PostgreSQL database

-- Enable the pg_trgm extension (required for trigram indexes)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Add GIN trigram indexes for transaction search fields
-- These dramatically speed up ILIKE '%query%' searches

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_description_trgm
ON transactions USING gin (description gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_transactions_merchant_trgm
ON transactions USING gin (merchant gin_trgm_ops);

-- Verify indexes were created
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'transactions'
AND indexname LIKE '%trgm%';
