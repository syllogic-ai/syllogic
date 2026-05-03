import { createHmac, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

const MAX_AGE_SECONDS = 60;

function constantTimeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  return timingSafeEqual(Buffer.from(a, "hex"), Buffer.from(b, "hex"));
}

export function verifyInternalRequest(
  req: NextRequest,
  path: string,
): { ok: true; userId: string } | { ok: false; reason: string } {
  const userId = req.headers.get("x-syllogic-user-id")?.trim();
  const ts = req.headers.get("x-syllogic-timestamp")?.trim();
  const sig = req.headers.get("x-syllogic-signature")?.trim();
  if (!userId || !ts || !sig) return { ok: false, reason: "missing headers" };
  const tsNum = Number(ts);
  if (!Number.isFinite(tsNum)) return { ok: false, reason: "bad timestamp" };
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - tsNum) > MAX_AGE_SECONDS) return { ok: false, reason: "expired" };

  const secret = process.env.INTERNAL_AUTH_SECRET;
  if (!secret) return { ok: false, reason: "secret not configured" };
  const expected = createHmac("sha256", secret)
    .update([req.method.toUpperCase(), path, userId, ts].join("\n"))
    .digest("hex");
  if (!constantTimeEqualHex(expected, sig)) return { ok: false, reason: "bad signature" };
  return { ok: true, userId };
}

export function unauthorizedInternal(reason: string) {
  return NextResponse.json({ error: `internal auth: ${reason}` }, { status: 401 });
}
