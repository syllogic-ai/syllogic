import { db } from "@/lib/db";
import {
  people,
  accountOwners,
  propertyOwners,
  vehicleOwners,
} from "@/lib/db/schema";
import { eq, and, inArray } from "drizzle-orm";
import { validateOwners, type OwnerInput } from "./validation";
import type { EntityType } from "./queries";

export async function createPerson(input: {
  userId: string;
  name: string;
  color?: string;
  avatarPath?: string | null;
}) {
  const [row] = await db
    .insert(people)
    .values({
      userId: input.userId,
      name: input.name,
      color: input.color,
      avatarPath: input.avatarPath ?? null,
      kind: "member",
    })
    .returning();
  return row;
}

export async function updatePerson(input: {
  userId: string;
  id: string;
  name?: string;
  color?: string;
  avatarPath?: string | null; // pass undefined to leave unchanged, null to clear
}) {
  const [row] = await db
    .update(people)
    .set({
      ...(input.name !== undefined ? { name: input.name } : {}),
      ...(input.color !== undefined ? { color: input.color } : {}),
      ...(input.avatarPath !== undefined ? { avatarPath: input.avatarPath } : {}),
      updatedAt: new Date(),
    })
    .where(and(eq(people.id, input.id), eq(people.userId, input.userId)))
    .returning();
  return row;
}

export async function deletePerson(input: { userId: string; id: string }) {
  // Block delete if this person is the sole owner of any entity.
  const blockers: { entityType: EntityType; entityId: string }[] = [];

  for (const [entityType, table, idCol] of [
    ["account", accountOwners, accountOwners.accountId],
    ["property", propertyOwners, propertyOwners.propertyId],
    ["vehicle", vehicleOwners, vehicleOwners.vehicleId],
  ] as const) {
    const ownedRows = await db
      .select({ id: idCol })
      .from(table)
      .where(eq(table.personId, input.id));
    for (const row of ownedRows) {
      const peers = await db
        .select({ pid: table.personId, share: table.share })
        .from(table)
        .where(eq(idCol, row.id));
      if (peers.length === 1) {
        // Sole owner — cannot delete.
        blockers.push({ entityType, entityId: row.id });
        continue;
      }
      // If all owners have explicit shares, removing this person would leave the
      // remaining shares not summing to 1 — block the delete.
      const explicit = peers.filter((r) => r.share !== null);
      if (explicit.length === peers.length) {
        blockers.push({ entityType, entityId: row.id });
      }
    }
  }

  if (blockers.length > 0) {
    const err = new Error("person is sole owner or holds an explicit share that would leave others unbalanced");
    (err as any).blockers = blockers;
    (err as any).code = "SOLE_OWNER";
    throw err;
  }

  const [target] = await db
    .select({ kind: people.kind })
    .from(people)
    .where(and(eq(people.id, input.id), eq(people.userId, input.userId)));
  if (!target) throw new Error("person not found");
  if (target.kind === "self") throw new Error("cannot delete the self person");

  await db.delete(people).where(eq(people.id, input.id));
}

export async function setOwners(input: {
  userId: string;
  entityType: EntityType;
  entityId: string;
  owners: OwnerInput[];
}) {
  validateOwners(input.owners);

  // Verify all listed personIds belong to this user.
  const ownedPeople = await db
    .select({ id: people.id })
    .from(people)
    .where(
      and(
        eq(people.userId, input.userId),
        inArray(
          people.id,
          input.owners.map((o) => o.personId)
        )
      )
    );
  if (ownedPeople.length !== input.owners.length) {
    throw new Error("one or more personIds do not belong to this user");
  }

  const table =
    input.entityType === "account"
      ? accountOwners
      : input.entityType === "property"
        ? propertyOwners
        : vehicleOwners;
  const idCol =
    input.entityType === "account"
      ? accountOwners.accountId
      : input.entityType === "property"
        ? propertyOwners.propertyId
        : vehicleOwners.vehicleId;
  const idField =
    input.entityType === "account"
      ? "accountId"
      : input.entityType === "property"
        ? "propertyId"
        : "vehicleId";

  await db.transaction(async (tx) => {
    await tx.delete(table).where(eq(idCol, input.entityId));
    await tx.insert(table).values(
      input.owners.map((o) => ({
        [idField]: input.entityId,
        personId: o.personId,
        share: o.share === null ? null : String(o.share),
      })) as any
    );
  });
}
