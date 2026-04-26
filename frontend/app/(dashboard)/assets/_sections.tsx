import { getAccounts } from "@/lib/actions/accounts";
import { getProperties } from "@/lib/actions/properties";
import { getVehicles } from "@/lib/actions/vehicles";
import { AssetManagement } from "./asset-management";

export async function AssetsSection() {
  const [accounts, properties, vehicles] = await Promise.all([
    getAccounts(),
    getProperties(),
    getVehicles(),
  ]);

  return (
    <AssetManagement
      initialAccounts={accounts}
      initialProperties={properties}
      initialVehicles={vehicles}
    />
  );
}
