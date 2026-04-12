CREATE TABLE IF NOT EXISTS "bank_connections" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"provider" varchar(50) DEFAULT 'enable_banking' NOT NULL,
	"session_id" varchar(255) NOT NULL,
	"aspsp_name" varchar(255) NOT NULL,
	"aspsp_country" char(2) NOT NULL,
	"consent_expires_at" timestamp,
	"consent_notified_at" timestamp,
	"status" varchar(20) DEFAULT 'active' NOT NULL,
	"last_synced_at" timestamp,
	"last_sync_error" text,
	"sync_cursor" jsonb,
	"raw_session_data" jsonb,
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now(),
	CONSTRAINT "bank_connections_user_session" UNIQUE("user_id","session_id")
);
--> statement-breakpoint
ALTER TABLE "accounts" ADD COLUMN "bank_connection_id" uuid;
--> statement-breakpoint
ALTER TABLE "bank_connections" ADD CONSTRAINT "bank_connections_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "accounts" ADD CONSTRAINT "accounts_bank_connection_id_bank_connections_id_fk" FOREIGN KEY ("bank_connection_id") REFERENCES "public"."bank_connections"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_bank_connections_user" ON "bank_connections" USING btree ("user_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_bank_connections_status" ON "bank_connections" USING btree ("status");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_bank_connections_consent_expires" ON "bank_connections" USING btree ("consent_expires_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_accounts_bank_connection" ON "accounts" USING btree ("bank_connection_id");
