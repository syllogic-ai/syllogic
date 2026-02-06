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

function getPgErrorCode(err) {
  return err?.cause?.code || err?.code;
}

function isPgDuplicateSchemaError(err) {
  const code = getPgErrorCode(err);
  // In some rare/racy situations Postgres can surface a duplicate error even with IF NOT EXISTS.
  // Treat both "duplicate_schema" and "unique_violation" as safe to ignore for schema creation.
  return code === "42P06" || code === "23505";
}

function isPgDuplicateTypeErrorForMigrationsTable(err) {
  const code = getPgErrorCode(err);
  if (code !== "23505") return false;
  const constraint = err?.cause?.constraint_name || err?.constraint_name;
  return constraint === "pg_type_typname_nsp_index";
}

async function ensureDrizzleMigrationsTracking(sql) {
  // Drizzle uses schema "drizzle" and table "__drizzle_migrations" by default.
  try {
    await sql.unsafe('CREATE SCHEMA IF NOT EXISTS "drizzle"');
  } catch (err) {
    if (!isPgDuplicateSchemaError(err)) throw err;
  }

  try {
    await sql.unsafe(
      'CREATE TABLE IF NOT EXISTS "drizzle"."__drizzle_migrations" (id SERIAL PRIMARY KEY, hash text NOT NULL, created_at bigint)'
    );
  } catch (err) {
    // If a previous attempt partially created the row type, Postgres can error even with IF NOT EXISTS.
    // Repair by dropping the stray type/table and retrying.
    if (!isPgDuplicateTypeErrorForMigrationsTable(err)) throw err;

    console.warn(
      "[migrate] Detected a broken __drizzle_migrations row type. Repairing tracking table..."
    );
    await sql.unsafe('DROP TABLE IF EXISTS "drizzle"."__drizzle_migrations"');
    await sql.unsafe('DROP TYPE IF EXISTS "drizzle"."__drizzle_migrations"');
    await sql.unsafe(
      'CREATE TABLE IF NOT EXISTS "drizzle"."__drizzle_migrations" (id SERIAL PRIMARY KEY, hash text NOT NULL, created_at bigint)'
    );
  }
}

async function baselineExistingSchema(sql, migrationsFolder) {
  await ensureDrizzleMigrationsTracking(sql);
  // Ensure our migration SQL (which uses unqualified table names) applies to the public schema.
  await sql.unsafe('SET search_path TO public');

  const rows = await sql`select count(*)::int as count from "drizzle"."__drizzle_migrations"`;
  const count = Number(rows?.[0]?.count ?? 0);
  if (count > 0) {
    console.log("[migrate] Migrations table already has entries; not baselining.");
    return false;
  }

  // Read migrations using Drizzle's own reader (journal-based).
  //
  // IMPORTANT:
  // We only baseline the *first* migration (usually the initial schema create).
  // If we marked *all* migrations as applied, we'd skip newer ALTER/patch
  // migrations and drift the schema. After baselining the first entry, the
  // migrator can run the remaining migrations normally.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { readMigrationFiles } = require("drizzle-orm/migrator");
  const migrations = readMigrationFiles({ migrationsFolder });

  if (!Array.isArray(migrations) || migrations.length === 0) {
    console.log("[migrate] No migrations found; nothing to baseline.");
    return true;
  }

  const first = migrations[0];
  await sql`insert into "drizzle"."__drizzle_migrations" ("hash", "created_at") values (${first.hash}, ${first.folderMillis})`;

  console.log("[migrate] Baseline complete (initial migration marked as applied).");
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
    await ensureDrizzleMigrationsTracking(sql);
    // Ensure our migration SQL (which uses unqualified table names) applies to the public schema.
    await sql.unsafe('SET search_path TO public');
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
          // Now that the baseline is recorded, apply the remaining migrations.
          await migrate(db, { migrationsFolder });
          console.log("[migrate] Migrations complete (after baseline)");
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
