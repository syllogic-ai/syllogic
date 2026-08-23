-- Add fees to broker_trades. backend/app/models.py's BrokerTrade model has
-- declared this column since broker trade import shipped, but 0019_investments
-- created the table without it and no later migration added it — the same gap
-- 0025_holdings_provider_symbol.manual.sql closed for holdings. A database
-- built purely from these migrations is missing it entirely, so every ORM
-- query touching broker_trades fails with UndefinedColumn.
-- Hand-authored; applied via scripts/migrate.js (.manual.sql runner).

ALTER TABLE "broker_trades"
  ADD COLUMN IF NOT EXISTS "fees" numeric(28,8) DEFAULT 0 NOT NULL;
