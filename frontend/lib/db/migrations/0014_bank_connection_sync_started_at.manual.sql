-- Hotfix: 0014 was recorded in the Drizzle journal but never applied to
-- production (baselining on an existing schema marked it as applied without
-- running the ALTER). Celery's `sync_all_bank_connections` and
-- `check_consent_expiry` crash on every run with
-- `column bank_connections.sync_started_at does not exist`.
--
-- Re-apply idempotently via the manual-migration channel so it runs on every
-- deploy regardless of the Drizzle tracking state.

ALTER TABLE "bank_connections"
	ADD COLUMN IF NOT EXISTS "sync_started_at" timestamp;
