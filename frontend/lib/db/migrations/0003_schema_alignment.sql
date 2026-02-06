-- Schema alignment migration
--
-- Historically, some tables/columns were created implicitly by the backend (SQLAlchemy `create_all`).
-- The production container stack relies on Drizzle migrations instead, so this migration ensures
-- the database schema matches `frontend/lib/db/schema.ts` for both fresh installs and upgrades.

-- ============================================================================
-- New tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS "api_keys" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"name" varchar(255) NOT NULL,
	"key_hash" varchar(64) NOT NULL,
	"key_prefix" varchar(12) NOT NULL,
	"last_used_at" timestamp,
	"expires_at" timestamp,
	"created_at" timestamp DEFAULT now()
);
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "api_keys" ADD CONSTRAINT "api_keys_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_api_keys_user" ON "api_keys" USING btree ("user_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_api_keys_hash" ON "api_keys" USING btree ("key_hash");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "company_logos" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"domain" varchar(255),
	"company_name" varchar(255),
	"logo_url" text,
	"status" varchar(20) DEFAULT 'found' NOT NULL,
	"last_checked_at" timestamp DEFAULT now(),
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now(),
	CONSTRAINT "company_logos_domain_unique" UNIQUE("domain")
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_company_logos_domain" ON "company_logos" USING btree ("domain");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_company_logos_name" ON "company_logos" USING btree ("company_name");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "recurring_transactions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"name" varchar(255) NOT NULL,
	"merchant" varchar(255),
	"amount" numeric(15, 2) NOT NULL,
	"currency" char(3) DEFAULT 'EUR',
	"category_id" uuid,
	"logo_id" uuid,
	"importance" integer DEFAULT 3 NOT NULL,
	"frequency" varchar(20) NOT NULL,
	"is_active" boolean DEFAULT true,
	"description" text,
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now()
);
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "recurring_transactions" ADD CONSTRAINT "recurring_transactions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "recurring_transactions" ADD CONSTRAINT "recurring_transactions_category_id_categories_id_fk" FOREIGN KEY ("category_id") REFERENCES "public"."categories"("id") ON DELETE no action ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "recurring_transactions" ADD CONSTRAINT "recurring_transactions_logo_id_company_logos_id_fk" FOREIGN KEY ("logo_id") REFERENCES "public"."company_logos"("id") ON DELETE set null ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_recurring_transactions_user" ON "recurring_transactions" USING btree ("user_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_recurring_transactions_category" ON "recurring_transactions" USING btree ("category_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_recurring_transactions_active" ON "recurring_transactions" USING btree ("is_active");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "exchange_rates" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"date" timestamp NOT NULL,
	"base_currency" char(3) NOT NULL,
	"target_currency" char(3) NOT NULL,
	"rate" numeric(18, 8) NOT NULL,
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now(),
	CONSTRAINT "exchange_rates_date_base_target" UNIQUE("date","base_currency","target_currency")
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_exchange_rates_date" ON "exchange_rates" USING btree ("date");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_exchange_rates_base" ON "exchange_rates" USING btree ("base_currency");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_exchange_rates_target" ON "exchange_rates" USING btree ("target_currency");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "subscription_suggestions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"suggested_name" varchar(255) NOT NULL,
	"suggested_merchant" varchar(255),
	"suggested_amount" numeric(15, 2) NOT NULL,
	"currency" char(3) DEFAULT 'EUR' NOT NULL,
	"detected_frequency" varchar(20) NOT NULL,
	"confidence" integer NOT NULL,
	"matched_transaction_ids" text NOT NULL,
	"status" varchar(20) DEFAULT 'pending' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "subscription_suggestions" ADD CONSTRAINT "subscription_suggestions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_subscription_suggestions_user" ON "subscription_suggestions" USING btree ("user_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_subscription_suggestions_status" ON "subscription_suggestions" USING btree ("status");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "account_balances" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"account_id" uuid NOT NULL,
	"date" timestamp NOT NULL,
	"balance_in_account_currency" numeric(15, 2) NOT NULL,
	"balance_in_functional_currency" numeric(15, 2) NOT NULL,
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now(),
	CONSTRAINT "account_balances_account_date" UNIQUE("account_id","date")
);
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "account_balances" ADD CONSTRAINT "account_balances_account_id_accounts_id_fk" FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_account_balances_account" ON "account_balances" USING btree ("account_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_account_balances_date" ON "account_balances" USING btree ("date");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_account_balances_account_date_desc" ON "account_balances" USING btree ("account_id","date");
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "transaction_links" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"group_id" uuid NOT NULL,
	"transaction_id" uuid NOT NULL,
	"link_role" varchar(20) NOT NULL,
	"created_at" timestamp DEFAULT now(),
	CONSTRAINT "transaction_links_transaction_unique" UNIQUE("transaction_id")
);
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "transaction_links" ADD CONSTRAINT "transaction_links_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "transaction_links" ADD CONSTRAINT "transaction_links_transaction_id_transactions_id_fk" FOREIGN KEY ("transaction_id") REFERENCES "public"."transactions"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transaction_links_user" ON "transaction_links" USING btree ("user_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transaction_links_group" ON "transaction_links" USING btree ("group_id");
--> statement-breakpoint

-- ============================================================================
-- Existing tables: add missing columns + indexes
-- ============================================================================

ALTER TABLE "accounts"
	ADD COLUMN IF NOT EXISTS "bank_connection_id" uuid,
	ADD COLUMN IF NOT EXISTS "starting_balance" numeric(15, 2) DEFAULT '0',
	ADD COLUMN IF NOT EXISTS "functional_balance" numeric(15, 2);
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "accounts" ADD CONSTRAINT "accounts_bank_connection_id_bank_connections_id_fk" FOREIGN KEY ("bank_connection_id") REFERENCES "public"."bank_connections"("id") ON DELETE set null ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint

ALTER TABLE "categories"
	ADD COLUMN IF NOT EXISTS "hide_from_selection" boolean DEFAULT false;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_categories_user_type" ON "categories" USING btree ("user_id","category_type");
--> statement-breakpoint

ALTER TABLE "transactions"
	ADD COLUMN IF NOT EXISTS "functional_amount" numeric(15, 2),
	ADD COLUMN IF NOT EXISTS "recurring_transaction_id" uuid,
	ADD COLUMN IF NOT EXISTS "include_in_analytics" boolean NOT NULL DEFAULT true;
--> statement-breakpoint
DO $$ BEGIN
	ALTER TABLE "transactions" ADD CONSTRAINT "transactions_recurring_transaction_id_recurring_transactions_id_fk" FOREIGN KEY ("recurring_transaction_id") REFERENCES "public"."recurring_transactions"("id") ON DELETE set null ON UPDATE no action;
EXCEPTION
	WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transactions_recurring" ON "transactions" USING btree ("recurring_transaction_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transactions_user_category_system" ON "transactions" USING btree ("user_id","category_system_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transactions_user_type_date" ON "transactions" USING btree ("user_id","transaction_type","booked_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_transactions_merchant" ON "transactions" USING btree ("merchant");
--> statement-breakpoint

ALTER TABLE "bank_connections"
	ADD COLUMN IF NOT EXISTS "provider" varchar(50),
	ADD COLUMN IF NOT EXISTS "sync_status" varchar(50),
	ADD COLUMN IF NOT EXISTS "last_synced_at" timestamp,
	ADD COLUMN IF NOT EXISTS "error_message" text,
	ADD COLUMN IF NOT EXISTS "organization_id" varchar(255),
	ADD COLUMN IF NOT EXISTS "access_token" text,
	ADD COLUMN IF NOT EXISTS "refresh_token" text,
	ADD COLUMN IF NOT EXISTS "access_token_expires_at" timestamp;
--> statement-breakpoint

ALTER TABLE "csv_imports"
	ADD COLUMN IF NOT EXISTS "celery_task_id" varchar(255),
	ADD COLUMN IF NOT EXISTS "progress_count" integer DEFAULT 0,
	ADD COLUMN IF NOT EXISTS "selected_indices" jsonb;

