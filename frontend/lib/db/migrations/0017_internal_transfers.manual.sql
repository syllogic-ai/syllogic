-- Internal transfers table (hand-authored; applied via `pnpm db:push`).
-- Links a source transaction on a synced account to a mirror transaction
-- on a manually-registered pocket account, matched by counterparty IBAN.

CREATE TABLE IF NOT EXISTS "internal_transfers" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
	"user_id" text NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
	"source_txn_id" uuid NOT NULL UNIQUE REFERENCES "transactions"("id") ON DELETE CASCADE,
	"mirror_txn_id" uuid UNIQUE REFERENCES "transactions"("id") ON DELETE SET NULL,
	"source_account_id" uuid NOT NULL REFERENCES "accounts"("id") ON DELETE CASCADE,
	"pocket_account_id" uuid NOT NULL REFERENCES "accounts"("id") ON DELETE CASCADE,
	"amount" numeric(15, 2) NOT NULL,
	"currency" char(3) NOT NULL,
	"detected_at" timestamp DEFAULT now(),
	"created_at" timestamp DEFAULT now()
);
--> statement-breakpoint

CREATE INDEX IF NOT EXISTS "idx_internal_transfers_user"
	ON "internal_transfers" USING btree ("user_id");
--> statement-breakpoint

CREATE INDEX IF NOT EXISTS "idx_internal_transfers_pocket"
	ON "internal_transfers" USING btree ("pocket_account_id");
--> statement-breakpoint

-- Now that internal_transfers exists, wire the FK on transactions.internal_transfer_id
-- (column was added as a bare uuid in 0016).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'transactions_internal_transfer_id_internal_transfers_id_fk'
  ) THEN
    ALTER TABLE "transactions"
      ADD CONSTRAINT "transactions_internal_transfer_id_internal_transfers_id_fk"
      FOREIGN KEY ("internal_transfer_id") REFERENCES "internal_transfers"("id")
      ON DELETE SET NULL;
  END IF;
END $$;
