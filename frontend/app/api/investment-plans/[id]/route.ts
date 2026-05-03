import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { getPlan, updatePlan, deletePlan } from "@/lib/investment-plans";
import { slotConfigSchema } from "@/lib/investment-plans/schema";

const patchSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  description: z.string().nullable().optional(),
  totalMonthly: z.number().positive().optional(),
  currency: z.string().length(3).optional(),
  slots: z.array(slotConfigSchema).min(1).optional(),
  cron: z.string().min(1).max(100).optional(),
  timezone: z.string().min(1).max(64).optional(),
  scheduleHuman: z.string().min(1).optional(),
  recipientEmail: z.string().email().nullable().optional(),
  model: z.string().optional(),
  enabled: z.boolean().optional(),
});

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  const row = await getPlan(userId, id);
  if (!row) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json({ plan: row });
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  const patch = patchSchema.parse(await req.json());
  try {
    const row = await updatePlan(userId, id, patch);
    if (!row) return NextResponse.json({ error: "not found" }, { status: 404 });
    return NextResponse.json({ plan: row });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
}

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  await deletePlan(userId, id);
  return NextResponse.json({ ok: true });
}
