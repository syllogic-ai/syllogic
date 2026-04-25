-- Add alias_patterns JSONB column to accounts table.
-- Used by the AI categorizer to detect internal transfers via account aliases.
-- Hand-authored; applied via scripts/migrate.js (.manual.sql runner).

ALTER TABLE "accounts"
  ADD COLUMN IF NOT EXISTS "alias_patterns" jsonb NOT NULL DEFAULT '[]'::jsonb;
