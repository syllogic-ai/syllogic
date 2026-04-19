-- OAuth 2.1 provider tables for @better-auth/oauth-provider plugin.
-- Adds: oauth_client, oauth_access_token, oauth_refresh_token, oauth_consent.

CREATE TABLE IF NOT EXISTS "oauth_client" (
  "id" text PRIMARY KEY NOT NULL,
  "client_id" text NOT NULL,
  "client_secret" text,
  "disabled" boolean DEFAULT false,
  "skip_consent" boolean,
  "enable_end_session" boolean,
  "subject_type" text,
  "scopes" text[],
  "user_id" text,
  "created_at" timestamp,
  "updated_at" timestamp,
  "name" text,
  "uri" text,
  "icon" text,
  "contacts" text[],
  "tos" text,
  "policy" text,
  "software_id" text,
  "software_version" text,
  "software_statement" text,
  "redirect_uris" text[] NOT NULL,
  "post_logout_redirect_uris" text[],
  "token_endpoint_auth_method" text,
  "grant_types" text[],
  "response_types" text[],
  "public" boolean,
  "type" text,
  "require_pkce" boolean,
  "reference_id" text,
  "metadata" jsonb,
  CONSTRAINT "oauth_client_client_id_unique" UNIQUE("client_id")
);
--> statement-breakpoint
ALTER TABLE "oauth_client"
  ADD CONSTRAINT "oauth_client_user_id_users_id_fk"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE;
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "oauth_access_token" (
  "id" text PRIMARY KEY NOT NULL,
  "token" text,
  "client_id" text NOT NULL,
  "session_id" text,
  "user_id" text,
  "reference_id" text,
  "refresh_id" text,
  "expires_at" timestamp,
  "created_at" timestamp,
  "scopes" text[] NOT NULL,
  CONSTRAINT "oauth_access_token_token_unique" UNIQUE("token")
);
--> statement-breakpoint
ALTER TABLE "oauth_access_token"
  ADD CONSTRAINT "oauth_access_token_client_id_oauth_client_client_id_fk"
  FOREIGN KEY ("client_id") REFERENCES "oauth_client"("client_id") ON DELETE CASCADE;
--> statement-breakpoint
ALTER TABLE "oauth_access_token"
  ADD CONSTRAINT "oauth_access_token_session_id_sessions_id_fk"
  FOREIGN KEY ("session_id") REFERENCES "sessions"("id") ON DELETE SET NULL;
--> statement-breakpoint
ALTER TABLE "oauth_access_token"
  ADD CONSTRAINT "oauth_access_token_user_id_users_id_fk"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE;
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "oauth_refresh_token" (
  "id" text PRIMARY KEY NOT NULL,
  "token" text NOT NULL,
  "client_id" text NOT NULL,
  "session_id" text,
  "user_id" text NOT NULL,
  "reference_id" text,
  "expires_at" timestamp,
  "created_at" timestamp,
  "revoked" timestamp,
  "auth_time" timestamp,
  "scopes" text[] NOT NULL
);
--> statement-breakpoint
ALTER TABLE "oauth_refresh_token"
  ADD CONSTRAINT "oauth_refresh_token_client_id_oauth_client_client_id_fk"
  FOREIGN KEY ("client_id") REFERENCES "oauth_client"("client_id") ON DELETE CASCADE;
--> statement-breakpoint
ALTER TABLE "oauth_refresh_token"
  ADD CONSTRAINT "oauth_refresh_token_session_id_sessions_id_fk"
  FOREIGN KEY ("session_id") REFERENCES "sessions"("id") ON DELETE SET NULL;
--> statement-breakpoint
ALTER TABLE "oauth_refresh_token"
  ADD CONSTRAINT "oauth_refresh_token_user_id_users_id_fk"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE;
--> statement-breakpoint

CREATE TABLE IF NOT EXISTS "oauth_consent" (
  "id" text PRIMARY KEY NOT NULL,
  "client_id" text NOT NULL,
  "user_id" text,
  "reference_id" text,
  "scopes" text[] NOT NULL,
  "created_at" timestamp,
  "updated_at" timestamp
);
--> statement-breakpoint
ALTER TABLE "oauth_consent"
  ADD CONSTRAINT "oauth_consent_client_id_oauth_client_client_id_fk"
  FOREIGN KEY ("client_id") REFERENCES "oauth_client"("client_id") ON DELETE CASCADE;
--> statement-breakpoint
ALTER TABLE "oauth_consent"
  ADD CONSTRAINT "oauth_consent_user_id_users_id_fk"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE;
