import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireAuth } from "@/lib/auth-helpers";
import { listPlans, createPlan } from "@/lib/investment-plans";
import { slotConfigSchema } from "@/lib/investment-plans/schema";

const createSchema = z.object({
  name: z.string().min(1).max(255),
  description: z.string().nullable().optional(),
  totalMonthly: z.number().positive(),
  currency: z.string().length(3),
  slots: z.array(slotConfigSchema).min(1),
  cron: z.string().min(1).max(100),
  timezone: z.string().min(1).max(64),
  scheduleHuman: z.string().min(1),
  recipientEmail: z.string().email().nullable().optional(),
  model: z.string().optional(),
  enabled: z.boolean().optional(),
});

export async function GET() {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const rows = await listPlans(userId);
  return NextResponse.json({ plans: rows });
}

export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const input = createSchema.parse(await req.json());
  try {
    const row = await createPlan(userId, input);
    return NextResponse.json({ plan: row }, { status: 201 });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
}
