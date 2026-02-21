import { createAuthClient } from "better-auth/react";

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

const defaultBaseUrl =
  typeof window !== "undefined"
    ? window.location.origin
    : [
        process.env.APP_URL,
        process.env.NEXT_PUBLIC_BETTER_AUTH_URL,
        process.env.BETTER_AUTH_URL,
        process.env.RAILWAY_STATIC_URL,
        process.env.RAILWAY_PUBLIC_DOMAIN,
      ]
        .map((value) => toValidOrigin(value))
        .find((value): value is string => Boolean(value)) ||
      "http://localhost:3000";

export const authClient = createAuthClient({
  baseURL: defaultBaseUrl,
});

export const {
  signIn,
  signOut,
  signUp,
  useSession,
  getSession,
} = authClient;
