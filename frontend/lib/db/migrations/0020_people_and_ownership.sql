-- People & Household Ownership tables

CREATE TABLE IF NOT EXISTS "people" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "user_id" text NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
  "name" varchar(255) NOT NULL,
  "kind" varchar(20) DEFAULT 'member' NOT NULL,
  "color" varchar(7),
  "avatar_path" text,
  "created_at" timestamp DEFAULT now() NOT NULL,
  "updated_at" timestamp DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "account_owners" (
  "account_id" uuid NOT NULL REFERENCES "accounts"("id") ON DELETE CASCADE,
  "person_id" uuid NOT NULL REFERENCES "people"("id") ON DELETE CASCADE,
  "share" numeric(5, 4),
  "created_at" timestamp DEFAULT now() NOT NULL,
  CONSTRAINT "account_owners_pkey" PRIMARY KEY ("account_id", "person_id")
);

CREATE TABLE IF NOT EXISTS "property_owners" (
  "property_id" uuid NOT NULL REFERENCES "properties"("id") ON DELETE CASCADE,
  "person_id" uuid NOT NULL REFERENCES "people"("id") ON DELETE CASCADE,
  "share" numeric(5, 4),
  "created_at" timestamp DEFAULT now() NOT NULL,
  CONSTRAINT "property_owners_pkey" PRIMARY KEY ("property_id", "person_id")
);

CREATE TABLE IF NOT EXISTS "vehicle_owners" (
  "vehicle_id" uuid NOT NULL REFERENCES "vehicles"("id") ON DELETE CASCADE,
  "person_id" uuid NOT NULL REFERENCES "people"("id") ON DELETE CASCADE,
  "share" numeric(5, 4),
  "created_at" timestamp DEFAULT now() NOT NULL,
  CONSTRAINT "vehicle_owners_pkey" PRIMARY KEY ("vehicle_id", "person_id")
);

CREATE INDEX IF NOT EXISTS "idx_people_user" ON "people" ("user_id");
CREATE UNIQUE INDEX IF NOT EXISTS "people_user_self_uq" ON "people" ("user_id") WHERE "kind" = 'self';
CREATE INDEX IF NOT EXISTS "idx_account_owners_person" ON "account_owners" ("person_id");
CREATE INDEX IF NOT EXISTS "idx_property_owners_person" ON "property_owners" ("person_id");
CREATE INDEX IF NOT EXISTS "idx_vehicle_owners_person" ON "vehicle_owners" ("person_id");
