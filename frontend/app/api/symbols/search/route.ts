import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { signedFetch } from "@/lib/internal/sign";

const bodySchema = z.object({ query: z.string().min(1).max(64) });

export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { query } = bodySchema.parse(await req.json());

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
