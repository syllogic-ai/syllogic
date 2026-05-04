import { getAccounts } from "@/lib/actions/accounts";
import { getProperties } from "@/lib/actions/properties";
import { getVehicles } from "@/lib/actions/vehicles";
import { getPeople } from "@/lib/people";
import { avatarUrl } from "@/lib/people/avatars";
import { requireAuth } from "@/lib/auth-helpers";
import { AssetManagement } from "./asset-management";

export async function AssetsSection() {
  const userId = await requireAuth();

  const [accounts, properties, vehicles, peopleRows] = await Promise.all([
    getAccounts(),
    getProperties(),
    getVehicles(),
    userId ? getPeople(userId) : Promise.resolve([]),
  ]);

  const people = peopleRows.map((p) => ({
    id: p.id,
    name: p.name,
    kind: p.kind,
    color: p.color,
    avatarUrl: avatarUrl(p.avatarPath),
  }));

  return (
    <AssetManagement
      initialAccounts={accounts}
      initialProperties={properties}
      initialVehicles={vehicles}
      initialPeople={people}
    />
  );
}
