import { listInvestmentAccounts } from "@/lib/api/investments";
import { ConnectPathPicker } from "@/components/investments/ConnectPathPicker";

export const dynamic = "force-dynamic";

export default async function ConnectPage() {
  const accounts = await listInvestmentAccounts();
  return <ConnectPathPicker accounts={accounts} />;
}
