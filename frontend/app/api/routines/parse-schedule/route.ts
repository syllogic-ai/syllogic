import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { parseScheduleResponseSchema } from "@/lib/routines/schema";
import { signedFetch } from "@/lib/internal/sign";

const bodySchema = z.object({ text: z.string().min(1).max(500) });

export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { text } = bodySchema.parse(await req.json());

  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  const path = "/internal/routines/parse-schedule";
  const r = await signedFetch(`${backend}${path}`, {
    method: "POST",
    userId,
    path,
    body: JSON.stringify({ text }),
    headers: { "content-type": "application/json" },
  });
  if (!r.ok) {
    const detail = await r.text();
    return NextResponse.json({ error: detail }, { status: r.status });
  }
  const payload = parseScheduleResponseSchema.parse(await r.json());
  return NextResponse.json(payload);
}
