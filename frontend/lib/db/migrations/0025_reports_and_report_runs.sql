CREATE TABLE "reports" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"name" varchar(255) NOT NULL,
	"account_ids" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"transaction_mode" varchar(20) DEFAULT 'RECENT' NOT NULL,
	"transaction_count" integer DEFAULT 10 NOT NULL,
	"transaction_direction" varchar(20) DEFAULT 'ALL' NOT NULL,
	"frequency" varchar(20) NOT NULL,
	"send_time" time DEFAULT '08:00:00' NOT NULL,
	"send_day_of_week" integer,
	"send_day_of_month" integer,
	"timezone" varchar(64) DEFAULT 'UTC' NOT NULL,
	"recipient_emails" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"next_run_at" timestamp,
	"created_at" timestamp DEFAULT now(),
	"updated_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "report_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"report_id" uuid NOT NULL,
	"scheduled_for" timestamp,
	"is_test" boolean DEFAULT false NOT NULL,
	"started_at" timestamp,
	"finished_at" timestamp,
	"status" varchar(20) DEFAULT 'SCHEDULED' NOT NULL,
	"error_message" text,
	"recipient_emails" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"created_at" timestamp DEFAULT now()
);
--> statement-breakpoint
ALTER TABLE "reports" ADD CONSTRAINT "reports_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "report_runs" ADD CONSTRAINT "report_runs_report_id_reports_id_fk" FOREIGN KEY ("report_id") REFERENCES "public"."reports"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
CREATE INDEX "idx_reports_user" ON "reports" USING btree ("user_id");
--> statement-breakpoint
CREATE INDEX "idx_reports_next_run_at" ON "reports" USING btree ("next_run_at");
--> statement-breakpoint
CREATE INDEX "idx_report_runs_report" ON "report_runs" USING btree ("report_id");
--> statement-breakpoint
CREATE INDEX "idx_report_runs_status" ON "report_runs" USING btree ("status");
