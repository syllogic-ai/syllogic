ALTER TABLE "accounts" ADD COLUMN IF NOT EXISTS "logo_id" uuid;
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "accounts" ADD CONSTRAINT "accounts_logo_id_company_logos_id_fk" FOREIGN KEY ("logo_id") REFERENCES "public"."company_logos"("id") ON DELETE set null ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_accounts_logo_id" ON "accounts" USING btree ("logo_id");
