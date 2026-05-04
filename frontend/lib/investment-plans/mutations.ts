import { db } from "@/lib/db";
import { investmentPlans, investmentPlanRuns } from "@/lib/db/schema";
import { eq, and, sql } from "drizzle-orm";
import type { SlotConfig } from "./schema";
import { validateSlots } from "./schema";
import { nextFireAfter } from "@/lib/scheduling/next-run";

export type PlanInput = {
  name: string;
  description?: string | null;
  totalMonthly: number;
  currency: string;
  slots: SlotConfig[];
  cron: string;
  timezone: string;
  scheduleHuman: string;
  recipientEmail?: string | null;
  model?: string;
  enabled?: boolean;
};

export async function createPlan(userId: string, input: PlanInput) {
  validateSlots(input.slots, input.totalMonthly);
  const nextRunAt = nextFireAfter(input.cron, input.timezone);
  const [row] = await db.insert(investmentPlans).values({
    userId,
    name: input.name,
    description: input.description ?? null,
    totalMonthly: String(input.totalMonthly),
    currency: input.currency,
    slots: input.slots,
    cron: input.cron,
    timezone: input.timezone,
    scheduleHuman: input.scheduleHuman,
    recipientEmail: input.recipientEmail ?? null,
    model: input.model ?? "claude-sonnet-4-6",
    enabled: input.enabled ?? true,
    ...(nextRunAt ? { nextRunAt } : {}),
  }).returning();
  return row;
}

export async function updatePlan(userId: string, id: string, patch: Partial<PlanInput>) {
  if (patch.slots !== undefined || patch.totalMonthly !== undefined) {
    // Need to validate against the merged final state.
    let nextSlots: SlotConfig[] | undefined = patch.slots;
    let nextTotal: number | undefined = patch.totalMonthly;
    if (nextSlots === undefined || nextTotal === undefined) {
      const [current] = await db.select().from(investmentPlans)
        .where(and(eq(investmentPlans.id, id), eq(investmentPlans.userId, userId))).limit(1);
      if (!current) return undefined;
      if (nextSlots === undefined) nextSlots = (current.slots as SlotConfig[]) ?? [];
      if (nextTotal === undefined) nextTotal = Number(current.totalMonthly);
    }
    validateSlots(nextSlots, nextTotal);
  }
  let nextRunAtPatch: { nextRunAt: Date } | Record<string, never> = {};
  if (patch.cron !== undefined || patch.timezone !== undefined) {
    const cron = patch.cron ?? "";
    const tz = patch.timezone ?? "UTC";
    if (cron) {
      const next = nextFireAfter(cron, tz);
      if (next) nextRunAtPatch = { nextRunAt: next };
    }
  }
  const [row] = await db.update(investmentPlans)
    .set({
      ...(patch.name !== undefined ? { name: patch.name } : {}),
      ...(patch.description !== undefined ? { description: patch.description } : {}),
      ...(patch.totalMonthly !== undefined ? { totalMonthly: String(patch.totalMonthly) } : {}),
      ...(patch.currency !== undefined ? { currency: patch.currency } : {}),
      ...(patch.slots !== undefined ? { slots: patch.slots } : {}),
      ...(patch.cron !== undefined ? { cron: patch.cron } : {}),
      ...(patch.timezone !== undefined ? { timezone: patch.timezone } : {}),
      ...(patch.scheduleHuman !== undefined ? { scheduleHuman: patch.scheduleHuman } : {}),
      ...(patch.recipientEmail !== undefined ? { recipientEmail: patch.recipientEmail } : {}),
      ...(patch.model !== undefined ? { model: patch.model } : {}),
      ...(patch.enabled !== undefined ? { enabled: patch.enabled } : {}),
      ...nextRunAtPatch,
      updatedAt: new Date(),
    })
    .where(and(eq(investmentPlans.id, id), eq(investmentPlans.userId, userId)))
    .returning();
  return row;
}

export async function deletePlan(userId: string, id: string) {
  await db.delete(investmentPlans).where(and(eq(investmentPlans.id, id), eq(investmentPlans.userId, userId)));
}

export type ExecutionMark = { executedAt: string | null; note?: string };

export async function setExecutionMark(
  userId: string, runId: string, slotId: string, mark: ExecutionMark
) {
  if (mark.executedAt === null) {
    // Delete the key atomically.
    await db.update(investmentPlanRuns)
      .set({ executionMarks: sql`${investmentPlanRuns.executionMarks} - ${slotId}` })
      .where(and(eq(investmentPlanRuns.id, runId), eq(investmentPlanRuns.userId, userId)));
  } else {
    // Set the key atomically. jsonb_set takes path as text[]; the new value as jsonb.
    const value = JSON.stringify({ executedAt: mark.executedAt, ...(mark.note ? { note: mark.note } : {}) });
    await db.update(investmentPlanRuns)
      .set({
        executionMarks: sql`jsonb_set(${investmentPlanRuns.executionMarks}, ARRAY[${slotId}], ${value}::jsonb, true)`,
      })
      .where(and(eq(investmentPlanRuns.id, runId), eq(investmentPlanRuns.userId, userId)));
  }
}
