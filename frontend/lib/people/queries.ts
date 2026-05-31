import { db } from "@/lib/db";
import {
  people,
  accountOwners,
  propertyOwners,
  vehicleOwners,
  users,
} from "@/lib/db/schema";
import { eq, and, inArray } from "drizzle-orm";

export type EntityType = "account" | "property" | "vehicle";

export async function getPeople(userId: string) {
  return db
    .select()
    .from(people)
    .where(eq(people.userId, userId))
    .orderBy(people.kind, people.createdAt);
}

export async function getSelfPersonId(userId: string): Promise<string> {
  // Try fetch first
  const [existing] = await db
    .select({ id: people.id })
    .from(people)
    .where(and(eq(people.userId, userId), eq(people.kind, "self")))
    .limit(1);
  if (existing) return existing.id;

  // Auto-create. The partial unique index prevents duplicates if two requests race.
  const [user] = await db.select({ name: users.name }).from(users).where(eq(users.id, userId)).limit(1);
  const displayName = (user?.name && user.name.trim()) || "You";
  try {
    const [created] = await db.insert(people).values({
      userId, name: displayName, kind: "self",
    }).returning();
    return created.id;
  } catch {
    // Race: another request created it concurrently. Fetch again.
    const [retry] = await db
      .select({ id: people.id })
      .from(people)
      .where(and(eq(people.userId, userId), eq(people.kind, "self")))
      .limit(1);
    if (!retry) throw new Error(`failed to ensure self person for ${userId}`);
    return retry.id;
  }
}

export async function getOwners(entityType: EntityType, entityId: string) {
  const table =
    entityType === "account"
      ? accountOwners
      : entityType === "property"
        ? propertyOwners
        : vehicleOwners;
  const idCol =
    entityType === "account"
      ? accountOwners.accountId
      : entityType === "property"
        ? propertyOwners.propertyId
        : vehicleOwners.vehicleId;
  const rows = await db.select().from(table).where(eq(idCol, entityId));
  return rows.map((r) => ({
    personId: r.personId,
    share: r.share === null ? null : Number(r.share),
  }));
}

/**
 * Batched lookup: returns a Map of entityId -> owners[] for all `entityIds`.
 * Used by server components to avoid an N-request fetch waterfall on list pages.
 */
export async function getOwnersForEntities(
  entityType: EntityType,
  entityIds: string[]
): Promise<Map<string, { personId: string; share: number | null }[]>> {
  const out = new Map<string, { personId: string; share: number | null }[]>();
  if (entityIds.length === 0) return out;

  const push = (eid: string, personId: string, share: string | null) => {
    const list = out.get(eid) ?? [];
    list.push({ personId, share: share === null ? null : Number(share) });
    out.set(eid, list);
  };

  if (entityType === "account") {
    const rows = await db
      .select()
      .from(accountOwners)
      .where(inArray(accountOwners.accountId, entityIds));
    for (const r of rows) push(r.accountId, r.personId, r.share);
  } else if (entityType === "property") {
    const rows = await db
      .select()
      .from(propertyOwners)
      .where(inArray(propertyOwners.propertyId, entityIds));
    for (const r of rows) push(r.propertyId, r.personId, r.share);
  } else {
    const rows = await db
      .select()
      .from(vehicleOwners)
      .where(inArray(vehicleOwners.vehicleId, entityIds));
    for (const r of rows) push(r.vehicleId, r.personId, r.share);
  }
  return out;
}

/** Returns the set of entity ids of `entityType` owned by ANY of `personIds`. */
export async function listEntityIdsForPeople(
  entityType: EntityType,
  personIds: string[]
): Promise<string[]> {
  if (personIds.length === 0) return [];
  const table =
    entityType === "account"
      ? accountOwners
      : entityType === "property"
        ? propertyOwners
        : vehicleOwners;
  const idCol =
    entityType === "account"
      ? accountOwners.accountId
      : entityType === "property"
        ? propertyOwners.propertyId
        : vehicleOwners.vehicleId;
  const rows = await db
    .select({ id: idCol })
    .from(table)
    .where(inArray(table.personId, personIds));
  return Array.from(new Set(rows.map((r) => r.id)));
}
