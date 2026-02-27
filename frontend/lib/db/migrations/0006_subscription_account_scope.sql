ALTER TABLE "recurring_transactions"
	ADD COLUMN IF NOT EXISTS "account_id" uuid;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1
		FROM pg_constraint
		WHERE conname = 'recurring_transactions_account_id_accounts_id_fk'
	) THEN
		ALTER TABLE "recurring_transactions"
			ADD CONSTRAINT "recurring_transactions_account_id_accounts_id_fk"
			FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE set null ON UPDATE no action;
	END IF;
END $$;

CREATE INDEX IF NOT EXISTS "idx_recurring_transactions_account" ON "recurring_transactions" USING btree ("account_id");

-- Backfill account attribution when linked transactions are unambiguously on one account.
WITH single_account_subscriptions AS (
	SELECT
		t.recurring_transaction_id AS recurring_id,
		MIN(t.account_id::text)::uuid AS account_id
	FROM "transactions" t
	WHERE t.recurring_transaction_id IS NOT NULL
	GROUP BY t.recurring_transaction_id
	HAVING COUNT(DISTINCT t.account_id) = 1
)
UPDATE "recurring_transactions" rt
SET account_id = sas.account_id
FROM single_account_subscriptions sas
WHERE rt.id = sas.recurring_id
	AND rt.account_id IS NULL;
