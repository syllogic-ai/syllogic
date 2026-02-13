ALTER TABLE "accounts" DROP CONSTRAINT IF EXISTS "accounts_bank_connection_id_bank_connections_id_fk";
ALTER TABLE "accounts" DROP COLUMN IF EXISTS "bank_connection_id";
DROP TABLE IF EXISTS "bank_connections";
