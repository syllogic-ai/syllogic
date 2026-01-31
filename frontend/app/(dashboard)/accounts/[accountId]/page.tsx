import { notFound } from "next/navigation";
import { AccountDetail } from "./account-detail";
import { getAccountById, getAccountBalanceHistory } from "@/lib/actions/accounts";
import { getTransactionsForAccount } from "@/lib/actions/transactions";
import { getUserCategories } from "@/lib/actions/categories";

interface AccountPageProps {
  params: Promise<{ accountId: string }>;
}

export default async function AccountPage({ params }: AccountPageProps) {
  const { accountId } = await params;

  // First fetch account to verify it exists and user has access
  const account = await getAccountById(accountId);

  if (!account) {
    notFound();
  }

  // Then fetch remaining data in parallel
  const [balanceHistory, transactions, categories] = await Promise.all([
    getAccountBalanceHistory(accountId, 90),
    getTransactionsForAccount(accountId),
    getUserCategories(),
  ]);

  return (
    <div className="flex flex-col gap-4 p-4">
      <AccountDetail
        account={account}
        balanceHistory={balanceHistory}
        initialTransactions={transactions}
        categories={categories}
      />
    </div>
  );
}
