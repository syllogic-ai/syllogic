import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { signedFetch } from "@/lib/internal/sign";

const bodySchema = z.object({ query: z.string().min(1).max(64) });

export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const parsedBody = bodySchema.safeParse(body);
  if (!parsedBody.success) {
    return NextResponse.json({ error: parsedBody.error.message }, { status: 400 });
  }
  const { query } = parsedBody.data;

  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  const path = "/internal/symbols/search";
  const r = await signedFetch(`${backend}${path}`, {
    method: "POST", userId, path,
    body: JSON.stringify({ query }),
    headers: { "content-type": "application/json" },
  });
  if (!r.ok) return NextResponse.json({ error: await r.text() }, { status: r.status });
  const results = await r.json();
  return NextResponse.json({ results });
}
