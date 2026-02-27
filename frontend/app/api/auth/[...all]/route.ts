import type { NextRequest } from "next/server";

async function resolveHandlers() {
  const [{ auth }, { toNextJsHandler }] = await Promise.all([
    import("@/lib/auth"),
    import("better-auth/next-js"),
  ]);
  return toNextJsHandler(auth);
}

export async function GET(req: NextRequest) {
  const handlers = await resolveHandlers();
  return handlers.GET(req);
}

export async function POST(req: NextRequest) {
  const handlers = await resolveHandlers();
  return handlers.POST(req);
}
