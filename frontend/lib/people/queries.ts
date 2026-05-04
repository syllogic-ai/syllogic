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
