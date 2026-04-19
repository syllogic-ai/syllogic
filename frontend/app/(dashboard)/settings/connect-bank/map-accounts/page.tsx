import { Suspense } from "react";
import { redirect } from "next/navigation";
import { Header } from "@/components/layout/header";
import { getCurrentUserProfile } from "@/lib/actions/settings";
import { isDemoRestrictedUserEmail } from "@/lib/demo-access";
import { getConnectionForMapping, getLinkableAccounts, getSuggestedMappings, type SuggestedMapping } from "@/lib/actions/bank-connections";
import { AccountMappingWizard } from "@/components/settings/account-mapping-wizard";
import { RiLoader4Line } from "@remixicon/react";

interface MapAccountsPageProps {
  searchParams: Promise<{ connectionId?: string }>;
}

export default async function MapAccountsPage({ searchParams }: MapAccountsPageProps) {
  const user = await getCurrentUserProfile();
  if (!user) redirect("/login");
  if (isDemoRestrictedUserEmail(user.email)) redirect("/settings");

  const resolvedParams = await searchParams;
  const connectionId = resolvedParams.connectionId;

  if (!connectionId) {
    redirect("/settings/connect-bank");
  }

  const [connection, linkableAccounts, suggestedMappings] = await Promise.all([
    getConnectionForMapping(connectionId),
    getLinkableAccounts(),
    getSuggestedMappings(connectionId),
  ]);

  if (!connection) {
    redirect("/settings?tab=bank-connections");
  }

  // Extract bank accounts from raw session data
  const rawAccounts = (connection.rawSessionData as any)?.accounts || [];
  const bankAccounts = rawAccounts.map((a: any) => ({
    uid: a.uid || a.id || "",
    name: a.account_name || a.name || "Bank Account",
    iban: a.iban || a.account_id?.iban || "",
    currency: (a.currency || "EUR").toUpperCase(),
    accountType: a.account_type || "checking",
  }));

  return (
    <>
      <Header title="Map Bank Accounts" />
      <div className="flex flex-1 flex-col p-4 pt-0">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-12">
              <RiLoader4Line className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          }
        >
          <AccountMappingWizard
            connectionId={connectionId}
            aspspName={connection.aspspName}
            bankAccounts={bankAccounts}
            linkableAccounts={linkableAccounts}
            suggestedMappings={suggestedMappings}
          />
        </Suspense>
      </div>
    </>
  );
}
