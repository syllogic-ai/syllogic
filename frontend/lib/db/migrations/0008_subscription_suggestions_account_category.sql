ALTER TABLE "subscription_suggestions"
	ADD COLUMN IF NOT EXISTS "account_id" uuid,
	ADD COLUMN IF NOT EXISTS "suggested_category_id" uuid;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1
		FROM pg_constraint
		WHERE conname = 'subscription_suggestions_account_id_accounts_id_fk'
	) THEN
		ALTER TABLE "subscription_suggestions"
			ADD CONSTRAINT "subscription_suggestions_account_id_accounts_id_fk"
			FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE set null ON UPDATE no action;
	END IF;
END $$;

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1
		FROM pg_constraint
		WHERE conname = 'subscription_suggestions_suggested_category_id_categories_id_fk'
	) THEN
		ALTER TABLE "subscription_suggestions"
			ADD CONSTRAINT "subscription_suggestions_suggested_category_id_categories_id_fk"
			FOREIGN KEY ("suggested_category_id") REFERENCES "public"."categories"("id") ON DELETE set null ON UPDATE no action;
	END IF;
END $$;

CREATE INDEX IF NOT EXISTS "idx_subscription_suggestions_account" ON "subscription_suggestions" USING btree ("account_id");
CREATE INDEX IF NOT EXISTS "idx_subscription_suggestions_category" ON "subscription_suggestions" USING btree ("suggested_category_id");
