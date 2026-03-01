import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

type RateLimitBucket = {
  count: number;
  resetAtMs: number;
};

const rateLimitBuckets = new Map<string, RateLimitBucket>();

const parseEnvInt = (name: string, fallback: number): number => {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value) || value <= 0) return fallback;
  return value;
};

const envBool = (name: string, fallback = false): boolean => {
  const raw = process.env[name];
  if (!raw) return fallback;
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
};

const AUTH_RATE_LIMIT_ENABLED = envBool("AUTH_RATE_LIMIT_ENABLED", true);
const AUTH_RATE_LIMIT_WINDOW_MS = parseEnvInt("AUTH_RATE_LIMIT_WINDOW_MS", 60_000);
const AUTH_RATE_LIMIT_MAX_ATTEMPTS = parseEnvInt("AUTH_RATE_LIMIT_MAX_ATTEMPTS_PER_WINDOW", 30);
const DEMO_AUTH_RATE_LIMIT_MAX_ATTEMPTS = parseEnvInt("DEMO_AUTH_RATE_LIMIT_MAX_ATTEMPTS_PER_WINDOW", 10);
const DEMO_AUTH_RATE_LIMIT_GLOBAL_MAX_ATTEMPTS = parseEnvInt(
  "DEMO_AUTH_RATE_LIMIT_GLOBAL_MAX_ATTEMPTS_PER_WINDOW",
  120
);

const demoUserEmail = (
  process.env.DEMO_SHARED_USER_EMAIL ||
  process.env.NEXT_PUBLIC_DEMO_EMAIL ||
  ""
).trim().toLowerCase();

const cleanupExpiredBuckets = (nowMs: number) => {
  if (rateLimitBuckets.size < 5_000) return;
  for (const [key, bucket] of rateLimitBuckets) {
    if (bucket.resetAtMs <= nowMs) {
      rateLimitBuckets.delete(key);
    }
  }
};

const consumeRateLimit = (
  key: string,
  limit: number,
  windowMs: number,
  nowMs: number
): { allowed: true } | { allowed: false; retryAfterSeconds: number } => {
  const current = rateLimitBuckets.get(key);
  if (!current || current.resetAtMs <= nowMs) {
    rateLimitBuckets.set(key, { count: 1, resetAtMs: nowMs + windowMs });
    return { allowed: true };
  }

  if (current.count >= limit) {
    const retryAfterSeconds = Math.max(
      1,
      Math.ceil((current.resetAtMs - nowMs) / 1000)
    );
    return { allowed: false, retryAfterSeconds };
  }

  current.count += 1;
  return { allowed: true };
};

const getClientIdentifier = (req: NextRequest): string => {
  const xff = req.headers.get("x-forwarded-for");
  if (xff) {
    const candidate = xff.split(",")[0]?.trim();
    if (candidate) return candidate;
  }
  const cf = req.headers.get("cf-connecting-ip")?.trim();
  if (cf) return cf;
  const real = req.headers.get("x-real-ip")?.trim();
  if (real) return real;
  return "unknown";
};

const isEmailSignInRequest = (req: NextRequest): boolean =>
  req.nextUrl.pathname.endsWith("/sign-in/email");

const extractEmailFromRequest = async (req: NextRequest): Promise<string | null> => {
  const contentType = req.headers.get("content-type") || "";
  try {
    if (contentType.includes("application/json")) {
      const json = await req.clone().json() as Record<string, unknown>;
      const email = json?.email;
      if (typeof email === "string" && email.trim()) {
        return email.trim().toLowerCase();
      }
      return null;
    }

    if (contentType.includes("application/x-www-form-urlencoded")) {
      const raw = await req.clone().text();
      const params = new URLSearchParams(raw);
      const email = params.get("email")?.trim();
      return email ? email.toLowerCase() : null;
    }
  } catch {
    return null;
  }
  return null;
};

const tooManyRequests = (retryAfterSeconds: number, message: string) =>
  NextResponse.json(
    { error: message, retryAfterSeconds },
    {
      status: 429,
      headers: {
        "Retry-After": String(retryAfterSeconds),
      },
    }
  );

async function resolveHandlers() {
  const [{ auth }, { toNextJsHandler }] = await Promise.all([
    import("@/lib/auth"),
    import("better-auth/next-js"),
  ]);
  return toNextJsHandler(auth);
}

let handlersPromise: ReturnType<typeof resolveHandlers> | null = null;

async function getHandlers() {
  if (!handlersPromise) {
    handlersPromise = resolveHandlers();
  }
  return handlersPromise;
}

export async function GET(req: NextRequest) {
  const handlers = await getHandlers();
  return handlers.GET(req);
}

export async function POST(req: NextRequest) {
  if (AUTH_RATE_LIMIT_ENABLED && isEmailSignInRequest(req)) {
    const nowMs = Date.now();
    cleanupExpiredBuckets(nowMs);

    const client = getClientIdentifier(req);
    const genericAttempt = consumeRateLimit(
      `auth:signin:ip:${client}`,
      AUTH_RATE_LIMIT_MAX_ATTEMPTS,
      AUTH_RATE_LIMIT_WINDOW_MS,
      nowMs
    );
    if (!genericAttempt.allowed) {
      return tooManyRequests(
        genericAttempt.retryAfterSeconds,
        "Too many sign-in attempts. Please try again shortly."
      );
    }

    const attemptedEmail = await extractEmailFromRequest(req);
    if (demoUserEmail && attemptedEmail === demoUserEmail) {
      const demoIpAttempt = consumeRateLimit(
        `auth:signin:demo:ip:${client}`,
        DEMO_AUTH_RATE_LIMIT_MAX_ATTEMPTS,
        AUTH_RATE_LIMIT_WINDOW_MS,
        nowMs
      );
      if (!demoIpAttempt.allowed) {
        return tooManyRequests(
          demoIpAttempt.retryAfterSeconds,
          "Too many demo login attempts from this network. Please try again shortly."
        );
      }

      const demoGlobalAttempt = consumeRateLimit(
        "auth:signin:demo:global",
        DEMO_AUTH_RATE_LIMIT_GLOBAL_MAX_ATTEMPTS,
        AUTH_RATE_LIMIT_WINDOW_MS,
        nowMs
      );
      if (!demoGlobalAttempt.allowed) {
        return tooManyRequests(
          demoGlobalAttempt.retryAfterSeconds,
          "Demo login is temporarily busy. Please try again shortly."
        );
      }
    }
  }

  const handlers = await getHandlers();
  return handlers.POST(req);
}
