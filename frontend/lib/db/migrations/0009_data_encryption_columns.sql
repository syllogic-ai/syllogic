-- Phase 2 encryption columns (dual-read/dual-write rollout).

ALTER TABLE "accounts"
	ADD COLUMN IF NOT EXISTS "external_id_ciphertext" text,
	ADD COLUMN IF NOT EXISTS "external_id_hash" varchar(64);
--> statement-breakpoint

CREATE INDEX IF NOT EXISTS "idx_accounts_external_id_hash"
	ON "accounts" USING btree ("external_id_hash");
--> statement-breakpoint

-- Keep uniqueness for non-null blind-index values while allowing legacy null rows.
CREATE UNIQUE INDEX IF NOT EXISTS "accounts_user_provider_external_id_hash_uq"
	ON "accounts" USING btree ("user_id", "provider", "external_id_hash")
	WHERE "external_id_hash" IS NOT NULL;
--> statement-breakpoint

ALTER TABLE "csv_imports"
	ADD COLUMN IF NOT EXISTS "file_path_ciphertext" text;

