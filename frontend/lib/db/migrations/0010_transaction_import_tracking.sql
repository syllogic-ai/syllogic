ALTER TABLE "transactions" ADD COLUMN "import_id" uuid;--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "transactions" ADD CONSTRAINT "transactions_import_id_csv_imports_id_fk" FOREIGN KEY ("import_id") REFERENCES "public"."csv_imports"("id") ON DELETE set null ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transactions_import" ON "transactions" USING btree ("import_id");--> statement-breakpoint
ALTER TABLE "account_balances" ADD COLUMN "is_anchored" boolean DEFAULT false NOT NULL;
