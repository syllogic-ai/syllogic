-- Add provider_symbol to holdings. backend/app/models.py's Holding model has
-- defined this column since the investments feature shipped, but no
-- committed migration ever added it — a fresh database built purely from
-- these migrations is missing it, breaking GET /investments/holdings
-- (discovered while locally verifying the mobile MVP's portfolio screen).
-- Hand-authored; applied via scripts/migrate.js (.manual.sql runner).

ALTER TABLE "holdings"
  ADD COLUMN IF NOT EXISTS "provider_symbol" varchar(64);
