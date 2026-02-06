import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL;

if (!connectionString) {
  throw new Error("DATABASE_URL environment variable is not set");
}

const sslRequired = /sslmode=require/i.test(connectionString) || /ssl=true/i.test(connectionString);

// Configure connection pooling to prevent "too many clients" errors
// In Next.js serverless functions, we need to limit connections and reuse them
const client = postgres(connectionString, {
  // Connection pool settings
  max: 10, // Maximum number of connections in the pool (default is 10)
  idle_timeout: 20, // Close idle connections after 20 seconds
  max_lifetime: 60 * 30, // Close connections after 30 minutes
  
  // Connection settings
  connection: {
    application_name: "personal-finance-app-frontend",
  },
  
  // Error handling
  onnotice: (notice) => {
    // Log PostgreSQL notices (warnings, info) in development
    if (process.env.NODE_ENV === "development") {
      console.log("[PostgreSQL Notice]", notice);
    }
  },
  
  // Transform to handle bigint and other types
  transform: {
    undefined: null,
  },

  ...(sslRequired ? { ssl: "require" } : {}),
});

// Gracefully close connections on process exit
if (typeof process !== "undefined") {
  const shutdown = async () => {
    await client.end();
  };
  
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

export const db = drizzle(client, { schema });

// Export schema for convenience
export * from "./schema";
