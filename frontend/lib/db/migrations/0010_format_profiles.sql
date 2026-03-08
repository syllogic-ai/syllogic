CREATE TABLE IF NOT EXISTS "format_profiles" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"fingerprint" varchar(64) NOT NULL,
	"script" text NOT NULL,
	"label" varchar(255),
	"created_at" timestamp DEFAULT now(),
	CONSTRAINT "format_profiles_user_fingerprint" UNIQUE("user_id","fingerprint")
);
--> statement-breakpoint
DO $$ BEGIN
 ALTER TABLE "format_profiles" ADD CONSTRAINT "format_profiles_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
EXCEPTION
 WHEN duplicate_object THEN null;
END $$;
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_format_profiles_user" ON "format_profiles" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "idx_format_profiles_fingerprint" ON "format_profiles" USING btree ("fingerprint");
