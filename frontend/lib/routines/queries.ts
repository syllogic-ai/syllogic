import { db } from "@/lib/db";
import { routines, routineRuns } from "@/lib/db/schema";
import { eq, desc, and } from "drizzle-orm";

export async function listRoutines(userId: string) {
  return db
    .select()
    .from(routines)
    .where(eq(routines.userId, userId))
    .orderBy(desc(routines.createdAt));
}

export async function getRoutine(userId: string, id: string) {
  const [row] = await db
    .select()
    .from(routines)
    .where(and(eq(routines.userId, userId), eq(routines.id, id)))
    .limit(1);
  return row ?? null;
}

export async function listRuns(userId: string, routineId: string, limit = 50) {
  return db
    .select()
    .from(routineRuns)
    .where(and(eq(routineRuns.userId, userId), eq(routineRuns.routineId, routineId)))
    .orderBy(desc(routineRuns.createdAt))
    .limit(limit);
}

export async function getRun(userId: string, runId: string) {
  const [row] = await db
    .select()
    .from(routineRuns)
    .where(and(eq(routineRuns.userId, userId), eq(routineRuns.id, runId)))
    .limit(1);
  return row ?? null;
}
