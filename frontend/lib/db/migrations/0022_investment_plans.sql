-- Investment Plans tables

CREATE TABLE IF NOT EXISTS "investment_plans" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "user_id" text NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
  "name" varchar(255) NOT NULL,
  "description" text,
  "total_monthly" numeric(15, 2) NOT NULL,
  "currency" char(3) DEFAULT 'EUR' NOT NULL,
  "slots" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "cron" varchar(100) NOT NULL,
  "timezone" varchar(64) DEFAULT 'UTC' NOT NULL,
  "schedule_human" text NOT NULL,
  "recipient_email" varchar(320),
  "model" varchar(100) DEFAULT 'claude-sonnet-4-6' NOT NULL,
  "enabled" boolean DEFAULT true NOT NULL,
  "next_run_at" timestamp,
  "last_run_at" timestamp,
  "created_at" timestamp DEFAULT now() NOT NULL,
  "updated_at" timestamp DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "investment_plan_runs" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "plan_id" uuid NOT NULL REFERENCES "investment_plans"("id") ON DELETE CASCADE,
  "user_id" text NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
  "status" varchar(20) DEFAULT 'queued' NOT NULL,
  "plan_snapshot" jsonb NOT NULL,
  "model_snapshot" varchar(100) NOT NULL,
  "output" jsonb,
  "transcript" jsonb,
  "email_message_id" varchar(255),
  "error_message" text,
  "cost_cents" integer,
  "execution_marks" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "started_at" timestamp,
  "completed_at" timestamp,
  "created_at" timestamp DEFAULT now() NOT NULL
);

CREATE INDEX IF NOT EXISTS "idx_investment_plans_user" ON "investment_plans" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_investment_plans_due" ON "investment_plans" ("enabled", "next_run_at");
CREATE INDEX IF NOT EXISTS "idx_investment_plan_runs_plan" ON "investment_plan_runs" ("plan_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_investment_plan_runs_user" ON "investment_plan_runs" ("user_id", "created_at");
