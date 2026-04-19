-- Align verification_tokens table with better-auth's expected schema.
-- better-auth's verification model reads/writes a `value` column; our table
-- historically exposed the same column as `token` with a unique constraint,
-- which broke oauth-provider's state storage (OAuth state, consent flow).
-- Rename the column to `value` and drop the unique index.

ALTER TABLE "verification_tokens" DROP CONSTRAINT IF EXISTS "verification_tokens_token_unique";
ALTER TABLE "verification_tokens" RENAME COLUMN "token" TO "value";
