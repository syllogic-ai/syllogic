import { redirect } from "next/navigation";
import { listInvestmentAccounts } from "@/lib/api/investments";
import { Header } from "@/components/layout/header";
import { ConnectPathPicker } from "@/components/investments/ConnectPathPicker";
import { getCurrentUserProfile } from "@/lib/actions/settings";
import { isDemoRestrictedUserEmail } from "@/lib/demo-access";

export const dynamic = "force-dynamic";

export default async function ConnectPage() {
  const user = await getCurrentUserProfile();
  if (!user) redirect("/login");
  if (isDemoRestrictedUserEmail(user.email)) redirect("/investments");

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
