-- Pocket account IBAN fields (hand-authored; applied via `pnpm db:push`).
-- Idempotent guards match the 0009 precedent so re-application is safe.

ALTER TABLE "accounts"
	ADD COLUMN IF NOT EXISTS "iban_ciphertext" text,
	ADD COLUMN IF NOT EXISTS "iban_hash" varchar(64);
--> statement-breakpoint

CREATE INDEX IF NOT EXISTS "idx_accounts_user_iban_hash"
	ON "accounts" USING btree ("user_id", "iban_hash");
--> statement-breakpoint

-- Prevent two concurrent create-pocket requests from racing and inserting
-- duplicate manual IBANs for the same user. The partial unique index is
-- scoped to manual-provider rows with a non-null hash so it never blocks a
-- pocket from coexisting with a synced-bank account that has the same IBAN.
CREATE UNIQUE INDEX IF NOT EXISTS "accounts_user_iban_hash_manual_uq"
	ON "accounts" USING btree ("user_id", "iban_hash")
	WHERE "provider" = 'manual' AND "iban_hash" IS NOT NULL;
