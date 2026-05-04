import { listInvestmentAccounts } from "@/lib/api/investments";
import { Header } from "@/components/layout/header";
import { ConnectPathPicker } from "@/components/investments/ConnectPathPicker";

export const dynamic = "force-dynamic";

export default async function ConnectPage() {
  const accounts = await listInvestmentAccounts();
  return (
    <>
      <Header title="Connect investments" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <ConnectPathPicker accounts={accounts} />
      </div>
    </>
  );
}
