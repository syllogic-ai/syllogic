import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { inArray, and, eq } from "drizzle-orm";
import { getOwnersForEntities, type EntityType } from "@/lib/people";
import { requireAuth } from "@/lib/auth-helpers";
import { db } from "@/lib/db";
import { accounts, properties, vehicles } from "@/lib/db/schema";

const bodySchema = z.object({
  account: z.array(z.string().uuid()).optional().default([]),
  property: z.array(z.string().uuid()).optional().default([]),
  vehicle: z.array(z.string().uuid()).optional().default([]),
});

async function filterOwnedIds(
  userId: string,
  entityType: EntityType,
  ids: string[]
): Promise<string[]> {
  if (ids.length === 0) return [];
  const table =
    entityType === "account" ? accounts : entityType === "property" ? properties : vehicles;
  const rows = await db
    .select({ id: table.id })
    .from(table)
    .where(and(eq(table.userId, userId), inArray(table.id, ids)));
  return rows.map((r) => r.id);
}

/**
 * Batch owner lookup. Pass any combination of entity ids per type and get back
 * a map of entityId -> owners. Used by <OwnerBadges> to coalesce N parallel
 * mounts on a list page into a single round trip.
 */
export async function POST(req: NextRequest) {
  const userId = await requireAuth();
  if (!userId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const parsed = bodySchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  const { account, property, vehicle } = parsed.data;

  // Authorization: only return rows for entities the user owns.
  const [accountIds, propertyIds, vehicleIds] = await Promise.all([
    filterOwnedIds(userId, "account", account),
    filterOwnedIds(userId, "property", property),
    filterOwnedIds(userId, "vehicle", vehicle),
  ]);

  const [accountMap, propertyMap, vehicleMap] = await Promise.all([
    getOwnersForEntities("account", accountIds),
    getOwnersForEntities("property", propertyIds),
    getOwnersForEntities("vehicle", vehicleIds),
  ]);

  const toObj = (m: Map<string, { personId: string; share: number | null }[]>) => {
    const o: Record<string, { personId: string; share: number | null }[]> = {};
    for (const [k, v] of m) o[k] = v;
    return o;
  };

  return NextResponse.json({
    account: toObj(accountMap),
    property: toObj(propertyMap),
    vehicle: toObj(vehicleMap),
  });
}
