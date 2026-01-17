import { Header } from "@/components/layout/header";
import { getAccounts } from "@/lib/actions/accounts";
import { AccountManagement } from "./account-management";

export default async function AssetsPage() {
  const accounts = await getAccounts();

  return (
    <>
      <Header title="Assets" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <AccountManagement initialAccounts={accounts} />
      </div>
    </>
  );
}
