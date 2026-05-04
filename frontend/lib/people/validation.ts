import { z } from "zod";

export const ownerInputSchema = z.object({
  personId: z.string().uuid(),
  share: z
    .union([z.number(), z.string().transform((s) => Number(s)), z.null()])
    .refine((v) => v === null || (typeof v === "number" && !Number.isNaN(v)), {
      message: "share must be a number or null",
    }),
});

export type OwnerInput = z.infer<typeof ownerInputSchema>;

const SHARE_TOLERANCE = 0.0001;

export function validateOwners(owners: OwnerInput[]): void {
  if (owners.length === 0) {
    throw new Error("at least one owner is required");
  }

  const ids = new Set<string>();
  for (const o of owners) {
    if (ids.has(o.personId)) throw new Error(`duplicate owner: ${o.personId}`);
    ids.add(o.personId);
  }

  const allNull = owners.every((o) => o.share === null);
  const allSet = owners.every((o) => o.share !== null);
  if (!allNull && !allSet) {
    throw new Error(
      "all owners must either share equally or specify shares"
    );
  }

  if (allSet) {
    for (const o of owners) {
      const s = o.share as number;
      if (s <= 0 || s > 1) {
        throw new Error(`share must be in (0, 1]; got ${s}`);
      }
    }
    const sum = owners.reduce((acc, o) => acc + (o.share as number), 0);
    if (Math.abs(sum - 1) > SHARE_TOLERANCE) {
      throw new Error(`shares must sum to 1; got ${sum}`);
    }
  }
}
