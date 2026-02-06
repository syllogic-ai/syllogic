-- BetterAuth admin plugin required fields.
--
-- The admin plugin expects these fields to exist in the Drizzle schema:
-- - users: role, banned, ban_reason, ban_expires
-- - sessions: impersonated_by

ALTER TABLE "users"
  ADD COLUMN IF NOT EXISTS "role" text DEFAULT 'user',
  ADD COLUMN IF NOT EXISTS "banned" boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS "ban_reason" text,
  ADD COLUMN IF NOT EXISTS "ban_expires" timestamp;

ALTER TABLE "sessions"
  ADD COLUMN IF NOT EXISTS "impersonated_by" text;

