ALTER TABLE "receipt_scans"
	ADD COLUMN IF NOT EXISTS "currency" varchar(3),
	ADD COLUMN IF NOT EXISTS "printed_total" numeric(15, 2),
	ADD COLUMN IF NOT EXISTS "printed_discount_total" numeric(15, 2),
	ADD COLUMN IF NOT EXISTS "merchant_legal_name" varchar(255),
	ADD COLUMN IF NOT EXISTS "merchant_address" text,
	ADD COLUMN IF NOT EXISTS "receipt_no" varchar(64),
	ADD COLUMN IF NOT EXISTS "fiscal_code" varchar(64),
	ADD COLUMN IF NOT EXISTS "vat_id" varchar(64),
	ADD COLUMN IF NOT EXISTS "payment_method" varchar(16),
	ADD COLUMN IF NOT EXISTS "card_last4" varchar(4),
	ADD COLUMN IF NOT EXISTS "file_sha256" char(64),
	ADD COLUMN IF NOT EXISTS "validation_errors" jsonb,
	ADD COLUMN IF NOT EXISTS "extraction_model" varchar(128);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_receipt_scans_sha256" ON "receipt_scans" ("user_id", "file_sha256") WHERE "file_sha256" IS NOT NULL;
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "receipt_line_items" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"receipt_scan_id" uuid NOT NULL REFERENCES "receipt_scans"("id") ON DELETE CASCADE,
	"line_ref" varchar(8) NOT NULL,
	"position" integer NOT NULL,
	"raw_text" text,
	"name" text,
	"quantity" numeric(12, 3),
	"gross_amount" numeric(15, 2),
	"discount_amount" numeric(15, 2) DEFAULT 0,
	"net_amount" numeric(15, 2),
	"kind" varchar(16) DEFAULT 'item' NOT NULL,
	"parent_line_ref" varchar(8),
	"category_id" uuid REFERENCES "categories"("id"),
	"category_confidence" varchar(8),
	"category_reason" text,
	"user_edited" boolean DEFAULT false NOT NULL,
	"booked_transaction_id" uuid REFERENCES "transactions"("id") ON DELETE SET NULL,
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now(),
	CONSTRAINT "receipt_line_items_scan_ref_uq" UNIQUE("receipt_scan_id", "line_ref")
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_receipt_line_items_scan" ON "receipt_line_items" ("receipt_scan_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_receipt_line_items_txn" ON "receipt_line_items" ("booked_transaction_id");
