-- Counterparty IBAN fields + internal_transfer_id placeholder on transactions
-- (hand-authored; applied via `pnpm db:push`). FK on internal_transfer_id
-- is added in migration 0017 once `internal_transfers` table exists.

ALTER TABLE "transactions"
	ADD COLUMN IF NOT EXISTS "counterparty_iban_ciphertext" text,
	ADD COLUMN IF NOT EXISTS "counterparty_iban_hash" varchar(64),
	ADD COLUMN IF NOT EXISTS "internal_transfer_id" uuid;
--> statement-breakpoint

CREATE INDEX IF NOT EXISTS "idx_transactions_user_counterparty_iban"
	ON "transactions" USING btree ("user_id", "counterparty_iban_hash");
