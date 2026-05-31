-- Hand-authored; applied via scripts/migrate.js (.manual.sql runner).
-- Removes the Routines and Investment Plans features. Idempotent: safe to
-- run every deploy. CASCADE also drops dependent indexes and FKs.
DROP TABLE IF EXISTS routine_runs CASCADE;
--> statement-breakpoint
DROP TABLE IF EXISTS routines CASCADE;
--> statement-breakpoint
DROP TABLE IF EXISTS investment_plan_runs CASCADE;
--> statement-breakpoint
DROP TABLE IF EXISTS investment_plans CASCADE;
