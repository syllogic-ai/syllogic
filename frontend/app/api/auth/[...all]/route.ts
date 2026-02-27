import type { NextRequest } from "next/server";

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
  const handlers = await getHandlers();
  return handlers.POST(req);
}
