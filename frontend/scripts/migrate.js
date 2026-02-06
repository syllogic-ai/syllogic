/* eslint-disable no-console */

/**
 * Production-safe DB migration runner for Drizzle SQL migrations.
 *
 * This is intentionally plain Node.js (no ts-node, no drizzle-kit) so it can run
 * inside the production frontend Docker image.
 *
 * Usage:
 *   DATABASE_URL=postgresql://... node scripts/migrate.js
 */

const fs = require("fs");
const path = require("path");

function isPgRelationExistsError(err) {
  const code = err?.cause?.code || err?.code;
  return code === "42P07"; // relation already exists
}

async function baselineExistingSchema(sql, migrationsFolder) {
  // Drizzle uses schema "drizzle" and table "__drizzle_migrations" by default.
  await sql.unsafe('CREATE SCHEMA IF NOT EXISTS "drizzle"');
  await sql.unsafe(
    'CREATE TABLE IF NOT EXISTS "drizzle"."__drizzle_migrations" (id SERIAL PRIMARY KEY, hash text NOT NULL, created_at bigint)'
  );

  const rows = await sql`select count(*)::int as count from "drizzle"."__drizzle_migrations"`;
  const count = Number(rows?.[0]?.count ?? 0);
  if (count > 0) {
    console.log("[migrate] Migrations table already has entries; not baselining.");
    return false;
  }

  // Read migrations using Drizzle's own reader (journal-based).
  // If the DB already has tables but no migration records, we assume it was
  // initialized via a prior push/create_all and baseline to the current journal.
  // This makes the migration job idempotent for existing installs.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { readMigrationFiles } = require("drizzle-orm/migrator");
  const migrations = readMigrationFiles({ migrationsFolder });

  if (!Array.isArray(migrations) || migrations.length === 0) {
    console.log("[migrate] No migrations found; nothing to baseline.");
    return true;
  }

  for (const m of migrations) {
    await sql`insert into "drizzle"."__drizzle_migrations" ("hash", "created_at") values (${m.hash}, ${m.folderMillis})`;
  }

  console.log(`[migrate] Baseline complete (${migrations.length} migration(s) marked as applied).`);
  return true;
}

async function main() {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    console.error("[migrate] DATABASE_URL is required");
    process.exit(1);
  }

  const migrationsFolder = path.join(
    process.cwd(),
    "lib",
    "db",
    "migrations"
  );

  if (!fs.existsSync(migrationsFolder)) {
    console.error(`[migrate] Migrations folder not found: ${migrationsFolder}`);
    process.exit(1);
  }

  // Use dynamic imports to work in both CJS/ESM environments.
  const postgresMod = await import("postgres");
  const postgres = postgresMod.default;

  const drizzleMod = await import("drizzle-orm/postgres-js");
  const { drizzle } = drizzleMod;

  const migratorMod = await import("drizzle-orm/postgres-js/migrator");
  const { migrate } = migratorMod;

  const sslRequired = /sslmode=require/i.test(databaseUrl);

  const sql = postgres(databaseUrl, {
    max: 1, // keep it minimal; this runs as a one-shot job
    connection: {
      application_name: "personal-finance-app-migrator",
    },
    ...(sslRequired ? { ssl: "require" } : {}),
  });

  try {
    const db = drizzle(sql);
    console.log(`[migrate] Running migrations from: ${migrationsFolder}`);
    try {
      await migrate(db, { migrationsFolder });
      console.log("[migrate] Migrations complete");
    } catch (err) {
      // If this DB already has the schema but doesn't have Drizzle migration tracking yet,
      // the initial migration may fail on "relation already exists". In that case, baseline.
      if (isPgRelationExistsError(err)) {
        console.warn("[migrate] Detected existing schema without migration tracking. Baseline mode...");
        const baselined = await baselineExistingSchema(sql, migrationsFolder);
        if (baselined) {
          return;
        }
      }

      throw err;
    }
  } finally {
    await sql.end({ timeout: 5 });
  }
}

main().catch((err) => {
  console.error("[migrate] Failed:", err);
  process.exit(1);
});
