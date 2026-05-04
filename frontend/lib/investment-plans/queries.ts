import { db } from "@/lib/db";
import { investmentPlans, investmentPlanRuns } from "@/lib/db/schema";
import { eq, desc, and } from "drizzle-orm";

export async function listPlans(userId: string) {
  return db.select().from(investmentPlans)
    .where(eq(investmentPlans.userId, userId))
    .orderBy(desc(investmentPlans.createdAt));
}

export async function getPlan(userId: string, id: string) {
  const [row] = await db.select().from(investmentPlans)
    .where(and(eq(investmentPlans.userId, userId), eq(investmentPlans.id, id)))
    .limit(1);
  return row ?? null;
}

export async function listPlanRuns(userId: string, planId: string, limit = 50) {
  return db.select().from(investmentPlanRuns)
    .where(and(eq(investmentPlanRuns.userId, userId), eq(investmentPlanRuns.planId, planId)))
    .orderBy(desc(investmentPlanRuns.createdAt))
    .limit(limit);
}

export async function getPlanRun(userId: string, runId: string) {
  const [row] = await db.select().from(investmentPlanRuns)
    .where(and(eq(investmentPlanRuns.userId, userId), eq(investmentPlanRuns.id, runId)))
    .limit(1);
  return row ?? null;
}
