import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getOwners, setOwners, type EntityType } from "@/lib/people";
import { requireAuth } from "@/lib/auth-helpers";
import { db } from "@/lib/db";
import { accounts, properties, vehicles } from "@/lib/db/schema";
import { eq, and } from "drizzle-orm";

const ENTITY_TYPES = ["account", "property", "vehicle"] as const;

async function userOwnsEntity(userId: string, entityType: EntityType, entityId: string): Promise<boolean> {
  const table = entityType === "account" ? accounts : entityType === "property" ? properties : vehicles;
  const [row] = await db.select({ id: table.id }).from(table)
    .where(and(eq(table.id, entityId), eq(table.userId, userId))).limit(1);
  return !!row;
}

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ entityType: string; entityId: string }> }
) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { entityType, entityId } = await ctx.params;
  if (!ENTITY_TYPES.includes(entityType as EntityType)) {
    return NextResponse.json({ error: "invalid entityType" }, { status: 400 });
  }
  if (!(await userOwnsEntity(userId, entityType as EntityType, entityId))) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  const owners = await getOwners(entityType as EntityType, entityId);
  return NextResponse.json({ owners });
}

const putSchema = z.object({
  owners: z
    .array(
      z.object({
        personId: z.string().uuid(),
        share: z.number().nullable(),
      })
    )
    .min(1),
});

export async function PUT(
  req: NextRequest,
  ctx: { params: Promise<{ entityType: string; entityId: string }> }
) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { entityType, entityId } = await ctx.params;
  if (!ENTITY_TYPES.includes(entityType as EntityType)) {
    return NextResponse.json({ error: "invalid entityType" }, { status: 400 });
  }
  if (!(await userOwnsEntity(userId, entityType as EntityType, entityId))) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const parsedBody = putSchema.safeParse(rawBody);
  if (!parsedBody.success) {
    return NextResponse.json({ error: parsedBody.error.message }, { status: 400 });
  }
  const body = parsedBody.data;
  try {
    await setOwners({
      userId,
      entityType: entityType as EntityType,
      entityId,
      owners: body.owners,
    });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 400 });
  }
}
