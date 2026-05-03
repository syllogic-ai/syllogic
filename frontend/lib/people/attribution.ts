export type Owner = { personId: string; share: number | null };

export function resolveShares(owners: Owner[]): Record<string, number> {
  if (owners.length === 0) return {};
  const allNull = owners.every((o) => o.share === null);
  if (allNull) {
    const equal = 1 / owners.length;
    return Object.fromEntries(owners.map((o) => [o.personId, equal]));
  }
  return Object.fromEntries(owners.map((o) => [o.personId, o.share as number]));
}

/**
 * Returns the amount attributable to `personId` given an ownership list.
 * `personId === null` means "whole household" — returns the full amount.
 */
export function attributeAmount(
  amount: number,
  owners: Owner[],
  personId: string | null
): number {
  if (personId === null) return amount;
  const shares = resolveShares(owners);
  const share = shares[personId] ?? 0;
  return amount * share;
}
