import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/lib/auth-helpers";
import { signedFetch } from "@/lib/internal/sign";

export async function POST(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;

  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  const path = `/internal/routines/${id}/test-run`;
  const r = await signedFetch(`${backend}${path}`, {
    method: "POST",
    userId,
    path,
    body: "{}",
    headers: { "content-type": "application/json" },
  });
  if (!r.ok) {
    return NextResponse.json({ error: await r.text() }, { status: r.status });
  }
  const j = await r.json();
  return NextResponse.json(j);
}
