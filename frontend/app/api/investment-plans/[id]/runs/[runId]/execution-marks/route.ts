import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { setExecutionMark } from "@/lib/investment-plans";

const bodySchema = z.object({
  slotId: z.string().min(1),
  executedAt: z.string().nullable(),
  note: z.string().optional(),
});

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string; runId: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { runId } = await ctx.params;
  const body = bodySchema.parse(await req.json());
  await setExecutionMark(userId, runId, body.slotId, { executedAt: body.executedAt, note: body.note });
  return NextResponse.json({ ok: true });
}
