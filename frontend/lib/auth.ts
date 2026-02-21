import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { admin } from "better-auth/plugins";
import { db } from "@/lib/db";
import * as schema from "@/lib/db/schema";

const toValidOrigin = (value?: string | null): string | undefined => {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;

  const candidate =
    trimmed.startsWith("http://") || trimmed.startsWith("https://")
      ? trimmed
      : `https://${trimmed}`;

  try {
    return new URL(candidate).origin;
  } catch {
    return undefined;
  }
};

const resolvedBaseURL = [
  process.env.APP_URL,
  process.env.BETTER_AUTH_URL,
  process.env.NEXT_PUBLIC_BETTER_AUTH_URL,
  process.env.RENDER_EXTERNAL_URL,
  process.env.RAILWAY_STATIC_URL,
  process.env.RAILWAY_PUBLIC_DOMAIN,
]
  .map((value) => toValidOrigin(value))
  .find((value): value is string => Boolean(value));

export const auth = betterAuth({
  baseURL: resolvedBaseURL,
  database: drizzleAdapter(db, {
    provider: "pg",
    schema: {
      user: schema.users,
      session: schema.sessions,
      account: schema.authAccounts,
      verification: schema.verificationTokens,
    },
  }),
  plugins: [admin()],
  emailAndPassword: {
    enabled: true,
    requireEmailVerification: false,
  },
  session: {
    expiresIn: 60 * 60 * 24, // 24 hours - appropriate for financial app security
    updateAge: 60 * 60, // 1 hour
    cookieCache: {
      enabled: false,
      maxAge: 5 * 60, // 5 minutes
    },
  },
  trustedOrigins: (() => {
    const csvOrigins = (process.env.BETTER_AUTH_TRUSTED_ORIGINS || "")
      .split(",")
      .map((value) => toValidOrigin(value))
      .filter((value): value is string => Boolean(value));

    const baseOrigins = [
      process.env.APP_URL,
      process.env.BETTER_AUTH_URL,
      process.env.NEXT_PUBLIC_BETTER_AUTH_URL,
      process.env.RENDER_EXTERNAL_URL,
      process.env.RAILWAY_PUBLIC_DOMAIN,
      process.env.RAILWAY_STATIC_URL,
    ]
      .map((value) => toValidOrigin(value))
      .filter((value): value is string => Boolean(value));

    if (process.env.NODE_ENV === "production") {
      return Array.from(new Set([...baseOrigins, ...csvOrigins]));
    }

    return Array.from(
      new Set([
        ...baseOrigins,
        ...csvOrigins,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "https://localhost:8443",
        "https://127.0.0.1:8443",
      ])
    );
  })(),
});

export type Session = typeof auth.$Infer.Session;
