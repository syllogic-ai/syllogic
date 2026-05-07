-- Categorization accuracy upgrade (Workstream: smarter AI categorization)
-- Adds:
--   1. pgvector extension (for semantic vendor/description matching)
--   2. categories.embedding — embedding of category keywords/description used as anchor
--   3. transactions.categorization_confidence — 0-100 confidence persisted per row
--   4. transactions.categorization_method — 'override' | 'deterministic' | 'embedding' | 'llm' | 'none'
--   5. transactions.embedding — embedding of merchant+description, reused across retries
--
-- Hand-authored; applied via `pnpm db:push`.

CREATE EXTENSION IF NOT EXISTS vector;
--> statement-breakpoint

ALTER TABLE "categories"
	ADD COLUMN IF NOT EXISTS "embedding" vector(1536);
--> statement-breakpoint

ALTER TABLE "transactions"
	ADD COLUMN IF NOT EXISTS "categorization_confidence" numeric(5, 2),
	ADD COLUMN IF NOT EXISTS "categorization_method" varchar(20),
	ADD COLUMN IF NOT EXISTS "embedding" vector(1536);
--> statement-breakpoint

-- Cosine-distance ANN index for category anchors (small cardinality, low cost).
CREATE INDEX IF NOT EXISTS "idx_categories_embedding_cosine"
	ON "categories" USING hnsw ("embedding" vector_cosine_ops);
--> statement-breakpoint

CREATE INDEX IF NOT EXISTS "idx_transactions_categorization_method"
	ON "transactions" ("categorization_method");
