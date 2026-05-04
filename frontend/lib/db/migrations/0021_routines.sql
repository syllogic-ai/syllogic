-- Routines & Digests tables

CREATE TABLE IF NOT EXISTS "routines" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "user_id" text NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
  "name" varchar(255) NOT NULL,
  "description" text,
  "prompt" text NOT NULL,
  "cron" varchar(100) NOT NULL,
  "timezone" varchar(64) DEFAULT 'UTC' NOT NULL,
  "schedule_human" text NOT NULL,
  "recipient_email" varchar(320) NOT NULL,
  "model" varchar(100) DEFAULT 'claude-sonnet-4-6' NOT NULL,
  "enabled" boolean DEFAULT true NOT NULL,
  "next_run_at" timestamp,
  "last_run_at" timestamp,
  "created_at" timestamp DEFAULT now() NOT NULL,
  "updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "routine_runs" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "routine_id" uuid NOT NULL REFERENCES "routines"("id") ON DELETE CASCADE,
  "user_id" text NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
  "status" varchar(20) DEFAULT 'queued' NOT NULL,
  "prompt_snapshot" text NOT NULL,
  "model_snapshot" varchar(100) NOT NULL,
  "output" jsonb,
  "transcript" jsonb,
  "email_message_id" varchar(255),
  "error_message" text,
  "cost_cents" integer,
  "started_at" timestamp,
  "completed_at" timestamp,
  "created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_routines_user" ON "routines" ("user_id");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_routines_due" ON "routines" ("enabled", "next_run_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_routine_runs_routine" ON "routine_runs" ("routine_id", "created_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_routine_runs_user" ON "routine_runs" ("user_id", "created_at");
