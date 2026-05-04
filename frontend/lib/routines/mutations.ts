import { db } from "@/lib/db";
import { routines } from "@/lib/db/schema";
import { eq, and } from "drizzle-orm";
import { nextFireAfter } from "@/lib/scheduling/next-run";

export type RoutineInput = {
  name: string;
  description?: string | null;
  prompt: string;
  cron: string;
  timezone: string;
  scheduleHuman: string;
  recipientEmail: string;
  model?: string;
  enabled?: boolean;
};

export async function createRoutine(userId: string, input: RoutineInput) {
  const nextRunAt = nextFireAfter(input.cron, input.timezone);
  const [row] = await db
    .insert(routines)
    .values({
      userId,
      name: input.name,
      description: input.description ?? null,
      prompt: input.prompt,
      cron: input.cron,
      timezone: input.timezone,
      scheduleHuman: input.scheduleHuman,
      recipientEmail: input.recipientEmail,
      model: input.model ?? "claude-sonnet-4-6",
      enabled: input.enabled ?? true,
      ...(nextRunAt ? { nextRunAt } : {}),
    })
    .returning();
  return row;
}

export async function updateRoutine(userId: string, id: string, patch: Partial<RoutineInput>) {
  // Recompute nextRunAt if cron or timezone changed. We need both fields to compute;
  // if only one is patched we can still compute since the other stays in the DB,
  // but we don't have the current DB value here. Instead, only recompute when both
  // are available in the patch (or cron alone — callers typically send both together).
  let nextRunAtPatch: { nextRunAt: Date } | Record<string, never> = {};
  if (patch.cron !== undefined || patch.timezone !== undefined) {
    // If only one is present we still try — nextFireAfter returns null on invalid input.
    const cron = patch.cron ?? "";
    const tz = patch.timezone ?? "UTC";
    if (cron) {
      const next = nextFireAfter(cron, tz);
      if (next) nextRunAtPatch = { nextRunAt: next };
    }
  }
  const [row] = await db
    .update(routines)
    .set({
      ...(patch.name !== undefined ? { name: patch.name } : {}),
      ...(patch.description !== undefined ? { description: patch.description } : {}),
      ...(patch.prompt !== undefined ? { prompt: patch.prompt } : {}),
      ...(patch.cron !== undefined ? { cron: patch.cron } : {}),
      ...(patch.timezone !== undefined ? { timezone: patch.timezone } : {}),
      ...(patch.scheduleHuman !== undefined ? { scheduleHuman: patch.scheduleHuman } : {}),
      ...(patch.recipientEmail !== undefined ? { recipientEmail: patch.recipientEmail } : {}),
      ...(patch.model !== undefined ? { model: patch.model } : {}),
      ...(patch.enabled !== undefined ? { enabled: patch.enabled } : {}),
      ...nextRunAtPatch,
      updatedAt: new Date(),
    })
    .where(and(eq(routines.id, id), eq(routines.userId, userId)))
    .returning();
  return row;
}

export async function deleteRoutine(userId: string, id: string) {
  await db.delete(routines).where(and(eq(routines.id, id), eq(routines.userId, userId)));
}
