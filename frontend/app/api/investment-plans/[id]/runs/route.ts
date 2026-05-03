import { NextRequest, NextResponse } from "next/server";
import { requireAuth } from "@/lib/auth-helpers";
import { listPlanRuns } from "@/lib/investment-plans";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  const runs = await listPlanRuns(userId, id);
  return NextResponse.json({ runs });
}
